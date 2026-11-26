"""The single SQL entry point. The agent's run_sql tool and the run_sql.py command both call execute_sql,
so both go through the same guard and the same connection setup."""
import datetime as dt
import decimal
import math
import threading

import duckdb

import claims_db
from contract import db_path
from sql_guard import GuardError, check_sql

MAX_ROWS = 10_000          # result-size cap
QUERY_TIMEOUT_S = 20       # per-statement time cap

_con = None


def connection() -> duckdb.DuckDBPyConnection:
    """One guarded connection per process, built from CLAIMS_DB (see claims_db.connect)."""
    global _con
    if _con is None:
        _con = claims_db.connect(db_path())
    return _con


def _plain(v):
    """Make a DuckDB value JSON-friendly: decimals become numbers, dates become ISO text, NaN becomes null."""
    if isinstance(v, decimal.Decimal):
        v = float(v)
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return str(v)


def execute_sql(sql: str) -> dict:
    """Run one statement through the safety layer.

    Returns {"columns": [...], "rows": [[...], ...]} (plus "truncated": true if the row cap was hit).
    Raises GuardError when the statement is refused, or an Exception with a short message when it fails.
    """
    statement = check_sql(sql)                      # layer 1: parser allow-list (sqlglot)
    con = connection()
    try:                                            # layer 2: DuckDB's own parser must agree it is one SELECT
        parsed = con.extract_statements(statement)
    except duckdb.Error as e:
        raise RuntimeError(f"SQL error: {_short(e)}") from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.SELECT:
        raise GuardError("Refused: only a single SELECT statement is allowed (this database is read-only).")

    timed_out = threading.Event()

    def _interrupt():
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(QUERY_TIMEOUT_S, _interrupt)
    timer.start()
    try:
        cur = con.execute(statement)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(MAX_ROWS + 1)
    except duckdb.Error as e:
        if timed_out.is_set():
            raise RuntimeError(f"Query cancelled: it ran longer than {QUERY_TIMEOUT_S} seconds.") from None
        raise RuntimeError(f"SQL error: {_short(e)}") from None
    finally:
        timer.cancel()

    if any(c.lower() == "diagnosis_note" for c in columns):     # belt and braces; cannot happen by construction
        raise GuardError("Refused: diagnosis_note is a sensitive column and cannot be returned.")
    result = {"columns": columns, "rows": [[_plain(v) for v in row] for row in fetched[:MAX_ROWS]]}
    if len(fetched) > MAX_ROWS:
        result["truncated"] = True
    return result


def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:400]
