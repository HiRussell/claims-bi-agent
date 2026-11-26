"""Small helpers for the submission contract (brief, section 7). Optional: use, change or ignore."""
import datetime as dt, decimal, json, os, sys


def db_path():
    """The grader sets CLAIMS_DB. The fallback is only for running locally."""
    return os.environ.get("CLAIMS_DB", "claims.duckdb")


def to_json(obj):
    """json.dumps for the contract: DuckDB decimals become JSON numbers, dates and times become ISO strings."""
    return json.dumps(obj, default=_plain)


def _plain(x):
    if isinstance(x, decimal.Decimal):
        return float(x)
    if isinstance(x, (dt.date, dt.datetime, dt.time)):
        return x.isoformat()
    return str(x)


def trace(kind, **fields):
    """Append one event to the trace file. kind is "tool_call" or "tool_result".
    Example: trace("tool_call", name="run_sql", args={"sql": sql}); trace("tool_result", name="run_sql", content=rows)
    """
    path = os.environ.get("TRACE_FILE")
    if path:
        with open(path, "a") as f:
            f.write(to_json({"type": kind, **fields}) + "\n")


def log(*args):
    """Print to stderr. stdout is reserved for the single JSON object the contract requires."""
    print(*args, file=sys.stderr)
