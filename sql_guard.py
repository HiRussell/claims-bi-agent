"""SQL safety guard: one read-only SELECT over an allow-list of relations, never the sensitive column.

The guard is a parser-level check (sqlglot AST), not a prompt instruction. Statements, relations and
functions unknown to the parser are refused unless they are on an allow-list. It is the SECOND line of
defence, not the first: a parser can disagree with the engine about what a statement means, so the
guarantees that matter do not rest on it. See claims_db.py: the sensitive column is never loaded, the source
file is detached, and external access is switched off inside the database.
"""
import logging
import unicodedata

import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)     # keep parser chatter off stderr

SENSITIVE_COLUMNS = {"diagnosis_note"}
MAX_SQL_CHARS = 20_000

# Relations a query may read. Raw tables keep their raw grain; the *_dim / claim_latest / claim_icd
# relations are the cleaned semantic layer (claims_db.py).
ALLOWED_RELATIONS = {
    "claim", "provider", "doctor", "claim_diagnosis", "claim_drug", "ref_icd", "drug", "lookup",
    "claim_latest", "claim_icd", "provider_dim", "doctor_dim", "drug_dim", "lookup_clean",
}

# Table-producing functions that only generate values and touch nothing outside the query.
SAFE_TABLE_FUNCTIONS = (exp.GenerateSeries, exp.Unnest)

# Functions sqlglot has no dedicated class for arrive as exp.Anonymous: allow only these names.
SAFE_ANONYMOUS_FUNCTIONS = {
    "strftime", "strptime", "date_part", "datepart", "date_diff", "datediff", "date_add", "date_sub",
    "date_trunc", "datetrunc", "last_day", "make_date", "monthname", "dayname", "yearweek", "isoyear",
    "year", "month", "day", "quarter", "week", "weekofyear", "dayofweek", "dayofyear", "isodow", "epoch",
    "round", "round_even", "trunc", "ceil", "ceiling", "floor", "abs", "sign", "sqrt", "power", "pow", "ln",
    "log", "log10", "log2", "exp", "greatest", "least", "isfinite", "isnan", "isinf", "even", "divide",
    "fdiv", "mod", "coalesce", "nullif", "ifnull", "if", "try_cast", "typeof",
    "lower", "upper", "trim", "ltrim", "rtrim", "lpad", "rpad", "length", "len", "strlen", "substr",
    "substring", "left", "right", "replace", "concat", "concat_ws", "contains", "starts_with", "ends_with",
    "prefix", "suffix", "regexp_replace", "regexp_extract", "regexp_matches", "regexp_full_match",
    "split_part", "string_split", "str_split", "format", "printf", "initcap", "reverse", "repeat", "instr",
    "position", "strpos", "ascii", "chr", "md5",
    "count", "count_if", "countif", "sum", "avg", "mean", "min", "max", "median", "mode", "stddev",
    "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop", "quantile", "quantile_cont",
    "quantile_disc", "approx_quantile", "approx_count_distinct", "any_value", "first", "last", "arg_max",
    "arg_min", "argmax", "argmin", "max_by", "min_by", "bool_and", "bool_or", "string_agg", "listagg",
    "group_concat", "list", "array_agg", "list_distinct", "list_sort", "array_length", "list_contains",
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile", "lag", "lead", "first_value",
    "last_value", "nth_value", "range", "generate_series", "unnest",
    "age", "entropy", "histogram", "element_at", "list_aggregate",
}

# Typed sqlglot functions that reach outside the query (files, environment, settings).
_DENIED_FUNC_CLASSES = tuple(
    getattr(exp, n) for n in ("ReadCSV", "ReadParquet", "ReadJSON", "CurrentUser", "CurrentSchema",
                              "CurrentCatalog", "SessionUser") if hasattr(exp, n)
)

# Statement / clause node types that write, change state or inspect the engine.
_DENIED_NODE_CLASSES = tuple(
    getattr(exp, n) for n in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
        "Copy", "Command", "Set", "Pragma", "Attach", "Detach", "Use", "Into", "Describe", "Summarize",
        "Show", "Transaction", "Commit", "Rollback", "Grant", "Revoke", "Analyze", "Export", "Install",
        "LoadData", "Pivot", "Lock", "Comment",
    ) if hasattr(exp, n)
)


class GuardError(Exception):
    """The statement is not allowed. The message is safe to show to a user or a model."""


def check_sql(sql: str) -> str:
    """Return the statement to execute, or raise GuardError explaining why it is refused."""
    if not isinstance(sql, str) or not sql.strip():
        raise GuardError("Refused: empty SQL.")
    if len(sql) > MAX_SQL_CHARS:
        raise GuardError("Refused: SQL statement is too long.")
    _reject_unsafe_characters(sql)
    text = sql.strip().rstrip(";").strip()
    try:
        parsed = [s for s in sqlglot.parse(text, read="duckdb") if s is not None]
    except Exception:
        raise GuardError("Refused: the SQL could not be parsed as a DuckDB SELECT statement.") from None
    if len(parsed) != 1:
        raise GuardError("Refused: exactly one statement is allowed.")
    root = parsed[0]
    if isinstance(root, exp.Pivot):
        raise GuardError(_PIVOT_HINT)
    if not isinstance(root, (exp.Select, exp.SetOperation)):
        raise GuardError("Refused: only SELECT statements are allowed (this database is read-only).")

    cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    for node in root.walk():
        if isinstance(node, exp.Pivot):
            raise GuardError(_PIVOT_HINT)
        if isinstance(node, _DENIED_NODE_CLASSES):
            raise GuardError(
                f"Refused: {type(node).__name__.upper()} is not allowed; only plain SELECT statements can run.")
        if isinstance(node, exp.Identifier) and node.name.lower() in SENSITIVE_COLUMNS:
            raise GuardError("Refused: diagnosis_note is a sensitive column and cannot be queried.")
        if isinstance(node, exp.Table):
            _check_table(node, cte_names)
        if isinstance(node, exp.Func):
            _check_function(node)
    return text


_PIVOT_HINT = ("Refused: PIVOT / UNPIVOT is not supported here. Use conditional aggregation instead, "
               "for example sum(x) FILTER (WHERE col = 'a') AS a.")

# Characters the two parsers disagree on. DuckDB reads zero-width and exotic space characters as white space,
# sqlglot reads them as part of a name, so "a<ZWSP>FROM<ZWSP>t" would be checked as one harmless column name
# and then executed as "a FROM t". Any such character is refused before parsing.
_UNSAFE_CATEGORIES = {"Cc", "Cf", "Zs", "Zl", "Zp", "Co", "Cs", "Cn"}


def _reject_unsafe_characters(sql: str) -> None:
    for ch in sql:
        if ch in " \t\n\r":
            continue
        if unicodedata.category(ch) in _UNSAFE_CATEGORIES:
            raise GuardError(f"Refused: the SQL contains an invisible or non-standard space character "
                             f"(U+{ord(ch):04X}). Use plain spaces.")


def _check_table(t: exp.Table, cte_names: set) -> None:
    if not isinstance(t.this, exp.Identifier):
        if isinstance(t.this, SAFE_TABLE_FUNCTIONS):
            return
        raise GuardError("Refused: table functions (for example reading files) are not allowed.")
    if t.catalog or t.db:
        raise GuardError(
            f"Refused: schema-qualified relation '{t.sql(dialect='duckdb')}' is not allowed; use bare table names.")
    name = t.name.lower()
    if name not in ALLOWED_RELATIONS and name not in cte_names:
        raise GuardError(
            f"Refused: unknown relation '{t.name}'. Allowed relations: {', '.join(sorted(ALLOWED_RELATIONS))}.")


def _check_function(f: exp.Func) -> None:
    if isinstance(f, exp.Anonymous):
        if f.name.lower() not in SAFE_ANONYMOUS_FUNCTIONS:
            raise GuardError(f"Refused: function '{f.name}' is not on the allow-list.")
    elif isinstance(f, _DENIED_FUNC_CLASSES):
        raise GuardError(f"Refused: function '{f.sql_name().lower()}' is not allowed.")
