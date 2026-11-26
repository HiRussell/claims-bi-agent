"""The single SQL entry point. The agent's run_sql tool and the run_sql.py command both call execute_sql,
so both go through the same guard and the same connection setup."""
import datetime as dt
import decimal
import json
import math
import threading

import duckdb

import claims_db
from contract import db_path
from sql_guard import GuardError, check_sql

MAX_ROWS = 10_000              # row cap
MAX_CELL_CHARS = 2_000         # longer text cells are cut
MAX_LIST_ITEMS = 200           # longer list cells are cut
MAX_RESULT_CHARS = 2_000_000   # budget for the whole result (JSON characters)
QUERY_TIMEOUT_S = 20           # per-statement time cap

# Errors of these kinds only quote the statement itself and schema names, so the full text is safe and useful
# (the model uses it to correct its SQL). Every other kind (conversion, out of range, invalid input, ...) can
# quote a data value, so only the kind is reported.
_ERRORS_WITHOUT_DATA = tuple(getattr(duckdb, n) for n in (
    "ParserException", "BinderException", "CatalogException", "SyntaxException") if hasattr(duckdb, n))

_con = None


def connection() -> duckdb.DuckDBPyConnection:
    """One guarded connection per process, built from CLAIMS_DB (see claims_db.connect)."""
    global _con
    if _con is None:
        _con = claims_db.connect(db_path())
    return _con


class _Shaper:
    """Makes DuckDB values JSON-friendly and bounded: decimals become numbers, dates become ISO text, NaN
    becomes null, over-long text and lists are cut. `cut` records whether anything was shortened."""

    def __init__(self):
        self.cut = False

    def plain(self, v):
        if isinstance(v, decimal.Decimal):
            v = float(v)
        if isinstance(v, float):
            return v if math.isfinite(v) else None
        if isinstance(v, (dt.date, dt.datetime, dt.time)):
            return v.isoformat()
        if v is None or isinstance(v, (bool, int)):
            return v
        if isinstance(v, (list, tuple)):
            if len(v) > MAX_LIST_ITEMS:
                self.cut = True
            return [self.plain(x) for x in v[:MAX_LIST_ITEMS]]
        if isinstance(v, dict):
            return {str(k): self.plain(x) for k, x in list(v.items())[:MAX_LIST_ITEMS]}
        text = v if isinstance(v, str) else str(v)
        if len(text) > MAX_CELL_CHARS:
            self.cut = True
            return text[:MAX_CELL_CHARS] + " ...[cut]"
        return text


def execute_sql(sql: str) -> dict:
    """Run one statement through the safety layer.

    Returns {"columns": [...], "rows": [[...], ...]} (plus "truncated": true if a row, cell or size cap cut
    the result). Raises GuardError when the statement is refused, or an Exception with a short message when
    it fails; messages never quote data values.
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
    shaper, rows, size, truncated = _Shaper(), [], 0, False
    try:
        cur = con.execute(statement)
        columns = [d[0] for d in cur.description] if cur.description else []
        while not truncated:                        # read in small batches so a huge result is never held whole
            batch = cur.fetchmany(500)
            if not batch:
                break
            for raw in batch:
                if len(rows) >= MAX_ROWS or size > MAX_RESULT_CHARS:
                    truncated = True
                    break
                row = [shaper.plain(v) for v in raw]
                size += len(json.dumps(row, default=str))
                rows.append(row)
    except duckdb.Error as e:
        if timed_out.is_set():
            raise RuntimeError(f"Query cancelled: it ran longer than {QUERY_TIMEOUT_S} seconds.") from None
        raise RuntimeError(f"SQL error: {_short(e)}") from None
    finally:
        timer.cancel()

    if any(c.lower() == "diagnosis_note" for c in columns):     # belt and braces; cannot happen by construction
        raise GuardError("Refused: diagnosis_note is a sensitive column and cannot be returned.")
    result = {"columns": columns, "rows": rows}
    if truncated or shaper.cut:
        result["truncated"] = True
    return result


def _short(e: Exception) -> str:
    if isinstance(e, _ERRORS_WITHOUT_DATA):
        return " ".join(str(e).split())[:400]
    kind = type(e).__name__.replace("Exception", "") or "Execution"
    return (f"{kind} error. The details are withheld because they can quote data values. "
            "Check the types involved; use TRY_CAST where a cast can fail.")
