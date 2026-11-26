"""The BI agent: one LLM-driven tool loop with three tools (get_catalogue, run_sql, final_answer).

The model decides which tools to call and in what order. Code around it enforces what must not depend on
the model: the SQL guard (sql_tool.execute_sql), the time budget, and the rule that every reported table and
SQL statement is copied from a query that really ran (the model cannot retype numbers into `tables`).
"""
import datetime as dt
import json
import os
import re
import time

import sql_tool
from contract import log, trace

HERE = os.path.dirname(os.path.abspath(__file__))
TOTAL_BUDGET_S = 100            # the contract allows 2 minutes per question; leave a margin
MAX_STEPS = 14
ROWS_SHOWN_TO_MODEL = 60
MAX_TABLE_ROWS = 2000
STATUSES = ("answered", "clarify", "declined", "unanswerable")

TOOLS = [
    {"type": "function", "function": {
        "name": "get_catalogue",
        "description": ("Describe the queryable relations: columns, meanings, the values of coded columns and "
                        "data-quality facts measured on the current database. Call this first."),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": ("Run ONE read-only DuckDB SELECT statement and get its rows back with a query_id. "
                        "Writes, multiple statements, file access and the diagnosis_note column are refused."),
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "A single DuckDB SELECT statement."}},
            "required": ["sql"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "final_answer",
        "description": ("Finish with the reply for the business user. The tables and SQL shown to the user are "
                        "copied verbatim from the queries named in query_ids."),
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "enum": list(STATUSES)},
            "answer": {"type": "string", "description": "The reply a business user reads. For 'clarify', the "
                                                        "question you need answered."},
            "assumptions": {"type": "array", "items": {"type": "string"},
                            "description": "Every rule, default or interpretation the figures rely on."},
            "query_ids": {"type": "array", "items": {"type": "string"},
                          "description": "query_id of each run_sql result that holds reported figures. "
                                         "Required for 'answered'; leave empty otherwise."}},
            "required": ["status", "answer", "assumptions", "query_ids"], "additionalProperties": False}}},
]

PROTOCOL = """You are a BI analyst agent for a health insurer's claims database (DuckDB).
You work only through tools. Every turn you must call a tool; never reply with plain text.

How to work:
1. Call get_catalogue once at the start to learn the relations and the data-quality facts.
2. Decide whether the question can be answered. If it needs data that does not exist, asks for sensitive
   notes, or asks to change data, call final_answer straight away with the right status and no query_ids.
3. Otherwise compute the figures with run_sql. Check a result that looks wrong before you report it.
4. Call final_answer once. The user sees exactly the result tables of the queries in query_ids, so the final
   query (or queries) must return precisely the figures you report: clear column names, amounts rounded with
   round(x, 2), a sensible ORDER BY, and LIMIT for a top-N. Do not list exploratory queries in query_ids.
5. Every number in `answer` must appear in one of those tables (this is checked). Never state a number you
   did not query: a total, a difference or a percentage needs its own column or query.
6. `assumptions` lists every rule or interpretation the figures rely on (approved only, latest version,
   SGD conversion, the exact date window, how Unknown was handled, ...).

DuckDB notes: date literals are DATE '2026-01-31'; use strftime(d, '%Y-%m') for months;
count(*) FILTER (WHERE cond) for conditional counts; integer division needs a cast to DOUBLE."""


# --------------------------------------------------------------------------------------------------------
# Dates: every relative period is derived from the as-of date, never from the system clock.
# --------------------------------------------------------------------------------------------------------
def _shift_months(first_of_month: dt.date, months: int) -> dt.date:
    index = first_of_month.year * 12 + (first_of_month.month - 1) + months
    return dt.date(index // 12, index % 12 + 1, 1)


def date_windows(as_of: dt.date) -> dict:
    month_start = as_of.replace(day=1)
    quarter_start = dt.date(as_of.year, 3 * ((as_of.month - 1) // 3) + 1, 1)
    day = dt.timedelta(days=1)

    def span(start, end):
        return {"from": start.isoformat(), "to": end.isoformat()}

    windows = {
        "today": as_of.isoformat(),
        "current_month_to_date": span(month_start, as_of),
        "last_month": span(_shift_months(month_start, -1), month_start - day),
        "last_quarter": span(_shift_months(quarter_start, -3), quarter_start - day),
        "current_quarter_to_date": span(quarter_start, as_of),
        "year_to_date": span(dt.date(as_of.year, 1, 1), as_of),
        "last_year": span(dt.date(as_of.year - 1, 1, 1), dt.date(as_of.year - 1, 12, 31)),
    }
    for n in (3, 6, 12, 24):
        windows[f"last_{n}_months"] = span(_shift_months(month_start, -n), month_start - day)
    windows["rule_for_last_N_months"] = (
        "the N complete calendar months before the current month; the window always ends on "
        f"{(month_start - day).isoformat()} and starts N months before {month_start.isoformat()}")
    return windows


def system_prompt(as_of: dt.date) -> str:
    with open(os.path.join(HERE, "business_rules.md")) as f:
        rules = f.read()
    return (f"{PROTOCOL}\n\nToday (the as-of date) is {as_of.isoformat()}.\n"
            f"Date windows (inclusive, apply to visit_date):\n{json.dumps(date_windows(as_of), indent=1)}\n\n{rules}")


# --------------------------------------------------------------------------------------------------------
# Catalogue: static column meanings + facts measured on whatever database CLAIMS_DB points to.
# --------------------------------------------------------------------------------------------------------
RELATION_NOTES = {
    "claim_latest": "DEFAULT for claim measures. One row per claim (latest loaded version), SGD amounts, "
                    "status flags, provider / doctor attributes with 'Unknown' for missing attribution.",
    "claim_icd": "One row per (claim, diagnosis), repeats removed. Overlapping groups: a claim can have several "
                 "diagnoses, so count(DISTINCT claim_id) per diagnosis.",
    "provider_dim": "One row per real provider (duplicate provider rows merged), codes decoded. Count providers here.",
    "doctor_dim": "One row per real doctor (a doctor entered twice under different spellings is merged), "
                  "specialty decoded. Different doctors can share a name: always group by doctor_id.",
    "drug_dim": "One row per drug, type decoded.",
    "claim_drug": "Raw drug lines per claim (line-level cost in the claim's local currency).",
    "claim": "RAW claim versions (several rows per claim_id). Only for version / load-history questions.",
    "claim_diagnosis": "Raw claim-to-ICD links (repeated pairs exist). Prefer claim_icd.",
    "provider": "Raw provider table; contains duplicate rows for the same provider. Prefer provider_dim.",
    "doctor": "Raw doctor table; can list one doctor twice. Prefer doctor_dim.",
    "drug": "Raw drug table. Prefer drug_dim.",
    "ref_icd": "Raw ICD reference.",
    "lookup": "Raw code lookup with repeated rows. Do not join it; use the decoded columns instead.",
    "lookup_clean": "De-duplicated lookup (type, code_key, descr).",
}
COLUMN_NOTES = {
    "claim_latest": {
        "visit_date": "date of the visit; all time windows use this",
        "visit_month": "YYYY-MM of visit_date",
        "is_approved": "approved_on set and voided_on not set",
        "is_rejected": "rejected_on set (can overlap with is_approved)",
        "is_voided": "voided_on set (cancelled)",
        "claim_amt": "net amount in LOCAL currency; do not sum across currencies",
        "claim_amt_sgd": "net amount in SGD = claim_amt / currency_rate; NULL if the rate is unusable",
        "grand_total": "gross amount incl. tax, local currency",
        "grand_total_sgd": "gross amount in SGD",
        "currency_rate": "units of local currency per 1 SGD",
        "provider_id": "id of the real provider after merging duplicate provider rows; group providers by this. "
                       "NULL when the claim's provider is not in the provider table",
        "doctor_id": "id of the real doctor after merging duplicate doctor rows; group doctors by this. "
                     "NULL when the claim has no known doctor",
        "doctor_id_raw": "doctor_id as stored on the claim (text; '' and '0' mean no doctor)",
        "provider_id_raw": "provider_id as stored on the claim",
        "country_code": "provider's country (ISO 2 letters) or 'Unknown'",
        "specialty": "doctor's specialty or 'Unknown'",
        "version_count": "how many versions of this claim were loaded",
        "loaded_at": "load time of this (latest) version",
    },
    "provider_dim": {"source_rows": "how many raw provider rows were merged into this provider"},
    "doctor_dim": {"source_rows": "how many raw doctor rows were merged into this doctor"},
    "claim_icd": {"icd_id": "ICD id as stored on the claim", "icd_code": "ICD code, or 'Unknown' when the id is not in ref_icd",
                  "diagnosis": "ICD description or 'Unknown'"},
    "claim_drug": {"cost": "line-level cost, local currency of the claim", "qty": "quantity on the line"},
}
CODED_COLUMNS = ["country_code", "provider_type", "region", "specialty", "visit_type", "currency_code"]


def build_catalogue(as_of: dt.date) -> dict:
    con = sql_tool.connection()
    day = as_of.isoformat()

    def one(sql):
        return con.execute(sql).fetchone()

    relations = []
    for name, note in RELATION_NOTES.items():
        cols = []
        for col_name, col_type, *_ in con.execute(f'DESCRIBE "{name}"').fetchall():
            entry = {"name": col_name, "type": col_type}
            if col_name in COLUMN_NOTES.get(name, {}):
                entry["note"] = COLUMN_NOTES[name][col_name]
            cols.append(entry)
        relations.append({"relation": name, "about": note, "columns": cols})

    values = {c: [r[0] for r in con.execute(
        f'SELECT DISTINCT "{c}" FROM claim_latest ORDER BY 1 LIMIT 40').fetchall()] for c in CODED_COLUMNS}

    raw_rows, claims, multi = one(
        "SELECT sum(n), count(*), count(*) FILTER (WHERE n > 1) FROM (SELECT count(*) n FROM claim GROUP BY claim_id)")
    total, future, no_provider, no_doctor, no_fx, first_visit, last_visit = one(f"""
        SELECT count(*), count(*) FILTER (WHERE visit_date > DATE '{day}'),
               count(*) FILTER (WHERE provider_name = 'Unknown'), count(*) FILTER (WHERE specialty = 'Unknown'),
               count(*) FILTER (WHERE claim_amt_sgd IS NULL),
               min(visit_date) FILTER (WHERE visit_date <= DATE '{day}'),
               max(visit_date) FILTER (WHERE visit_date <= DATE '{day}')
        FROM claim_latest""")
    conflicts = one("""SELECT count(*) FROM (
        SELECT claim_id FROM (
            SELECT DISTINCT * FROM claim QUALIFY loaded_at = max(loaded_at) OVER (PARTITION BY claim_id))
        GROUP BY claim_id HAVING count(*) > 1)""")[0]
    loaded_after = one(f"SELECT count(*) FROM claim_latest WHERE loaded_at >= DATE '{day}' + INTERVAL 1 DAY")[0]
    multi_dx = one("SELECT count(*) FROM (SELECT claim_id FROM claim_icd GROUP BY 1 HAVING count(*) > 1)")[0]
    provider_rows, providers = one("SELECT sum(source_rows), count(*) FROM provider_dim")
    doctor_rows, doctors = one("SELECT sum(source_rows), count(*) FROM doctor_dim")
    lookup_conflicts = one("SELECT count(*) FROM lookup_clean WHERE descr_variants > 1")[0]

    facts = [
        f"claim has {raw_rows} rows for {claims} claims; {multi} claims have more than one version. "
        "claim_latest keeps the latest version of each.",
        f"{future} claims have a visit_date after today ({day}); exclude them with visit_date <= DATE '{day}'.",
        f"Visit dates up to today run from {first_visit} to {last_visit}.",
        f"{no_provider} of {total} claims have no matching provider (provider_name / country_code / "
        "provider_type / region = 'Unknown').",
        f"{no_doctor} of {total} claims have no matching doctor (doctor_name / specialty = 'Unknown').",
        f"{multi_dx} claims have more than one diagnosis.",
    ]
    if provider_rows != providers:
        facts.append(f"provider has {provider_rows} rows but {providers} real providers: {provider_rows - providers} "
                     "rows repeat an existing provider under another id with a re-typed name (same type, country, "
                     "region). provider_dim and claim_latest merge them; say so in assumptions when you count or "
                     "rank providers.")
    if doctor_rows != doctors:
        facts.append(f"doctor has {doctor_rows} rows but {doctors} real doctors: {doctor_rows - doctors} rows repeat "
                     "an existing doctor under another id with the name typed differently (same specialty). "
                     "doctor_dim and claim_latest merge them; say so in assumptions when you count or rank doctors. "
                     "Doctors with an identical name are different people and are NOT merged.")
    if no_fx:
        facts.append(f"WARNING: {no_fx} claims have an unusable currency_rate, so claim_amt_sgd is NULL for them. "
                     "Report how many claims are missing from any SGD total.")
    if conflicts:
        facts.append(f"WARNING: {conflicts} claims have two different versions with the same latest loaded_at; "
                     "claim_latest picks one deterministically. Mention this in assumptions.")
    if loaded_after:
        facts.append(f"{loaded_after} claims have a latest version loaded after today; they are still used "
                     "(latest version wins). Mention this in assumptions if exact counts matter.")
    if lookup_conflicts:
        facts.append(f"WARNING: {lookup_conflicts} lookup codes have conflicting descriptions; the first is used.")
    return {"as_of": day, "relations": relations, "values_of_coded_columns": values, "data_facts": facts}


# --------------------------------------------------------------------------------------------------------
# Figures quoted in the answer text must come from the result tables
# --------------------------------------------------------------------------------------------------------
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(%|k\b|thousand\b|million\b|m\b|billion\b|bn\b)?",
                     re.IGNORECASE)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


def numbers_not_in_tables(answer: str, tables: list, context: str = "") -> list:
    """Numbers written in `answer` that match no cell of `tables`.

    Not counted: dates, months, years, whole numbers up to 31 (days, top-N, counts of rows), and numbers
    that already appear in `context` (the question and the as-of date). A number matches a cell when it is
    that cell rounded to the precision written ("83.6" matches 83.59, "1.3 million" matches 1,317,371.62);
    a percentage also matches the fraction form of the cell.
    """
    cells, quoted = [], set()
    for table in tables:
        for row in table.get("rows", []):
            for v in row:
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    cells.append(float(v))
                elif isinstance(v, str):                 # names such as "Orchid Family Clinic 396" or "X001"
                    quoted.update(float(n) for n in re.findall(r"\d+(?:\.\d+)?", v))
    quoted.update(float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", context))

    def strip_dates(text):
        text = re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b", " ", text)
        return re.sub(r"\b(?:19|20)\d{2}\b", " ", text)

    loose = []
    for m in _NUMBER.finditer(strip_dates(answer)):
        whole, frac, unit = m.group(1).replace(",", ""), m.group(2) or "", (m.group(3) or "").lower()
        value = float(whole + frac)
        scale = _SCALE.get(unit, 1.0)
        if unit in ("", "%") and not frac and value <= 31:
            continue
        if value in quoted:
            continue
        tolerance = 0.5 * 10 ** -(len(frac) - 1 if frac else 0) * scale + 1e-9
        targets = [value * scale] + ([value / 100] if unit == "%" else [])
        tolerances = [tolerance] + ([tolerance / 100] if unit == "%" else [])
        if not any(abs(abs(c) - t) <= tol for c in cells for t, tol in zip(targets, tolerances)):
            loose.append(m.group(0).strip())
    return list(dict.fromkeys(loose))


# --------------------------------------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------------------------------------
def _result(status, answer, tables=None, sql=None, assumptions=None) -> dict:
    return {"status": status, "answer": answer, "tables": tables or [], "sql": sql or [],
            "assumptions": assumptions or []}


def _failure(reason: str) -> dict:
    return _result("unanswerable", f"The agent could not complete this question ({reason}). No figure is reported.")


class Session:
    """State of one question: the queries that actually ran, and the tool implementations."""

    def __init__(self, as_of: dt.date, question: str = ""):
        self.as_of = as_of
        self.question = question
        self.queries = {}          # query_id -> {"sql", "columns", "rows", "truncated"}
        self.final = None
        self.asked_to_fix_numbers = False

    def call(self, name: str, args: dict):
        if name == "get_catalogue":
            return build_catalogue(self.as_of)
        if name == "run_sql":
            return self.run_sql(args.get("sql", ""))
        if name == "final_answer":
            return self.final_answer(args)
        return {"error": f"Unknown tool '{name}'. Tools: get_catalogue, run_sql, final_answer."}

    def run_sql(self, sql: str) -> dict:
        try:
            res = sql_tool.execute_sql(sql)
        except Exception as e:                       # GuardError or SQL error: the model sees the reason
            return {"error": str(e)}
        qid = f"q{len(self.queries) + 1}"
        self.queries[qid] = {"sql": sql.strip().rstrip(";").strip(), **res}
        out = {"query_id": qid, "columns": res["columns"], "rows": res["rows"][:ROWS_SHOWN_TO_MODEL],
               "row_count": len(res["rows"])}
        if len(res["rows"]) > ROWS_SHOWN_TO_MODEL:
            out["note"] = f"Only the first {ROWS_SHOWN_TO_MODEL} rows are shown to you."
        if res.get("truncated"):
            out["note"] = f"Result cut at {sql_tool.MAX_ROWS} rows; aggregate instead of listing rows."
        return out

    def final_answer(self, args: dict) -> dict:
        status = args.get("status")
        answer = args.get("answer")
        assumptions = args.get("assumptions") or []
        query_ids = args.get("query_ids") or []
        if status not in STATUSES:
            return {"error": f"status must be one of {list(STATUSES)}."}
        if not isinstance(answer, str) or not answer.strip():
            return {"error": "answer must be a non-empty string."}
        if not isinstance(assumptions, list) or not isinstance(query_ids, list):
            return {"error": "assumptions and query_ids must be lists."}
        assumptions = [str(a) for a in assumptions if str(a).strip()]
        if status != "answered":
            self.final = _result(status, answer.strip(), assumptions=assumptions)
            return {"ok": True}
        if not query_ids:
            return {"error": "status 'answered' needs query_ids: every reported figure must come from a query "
                             "you ran. Run the query, then call final_answer again."}
        unknown = [q for q in query_ids if q not in self.queries]
        if unknown:
            return {"error": f"Unknown query_ids {unknown}. Available: {list(self.queries)}."}
        if not assumptions:
            return {"error": "List the assumptions the figures rely on (approved only, latest version, SGD, "
                             "date window, Unknown handling, ...), then call final_answer again."}
        too_big = [q for q in query_ids if len(self.queries[q]["rows"]) > MAX_TABLE_ROWS]
        if too_big:
            return {"error": f"Result of {too_big} is too large to report; aggregate it or add a LIMIT."}
        chosen = [self.queries[q] for q in dict.fromkeys(query_ids)]
        tables = [{"columns": q["columns"], "rows": q["rows"]} for q in chosen]
        loose = numbers_not_in_tables(answer, tables, f"{self.question} {self.as_of.isoformat()}")
        if loose and not self.asked_to_fix_numbers:           # one chance to repair, so this can never loop
            self.asked_to_fix_numbers = True
            return {"error": f"These numbers in `answer` are not in the result tables you listed: {loose}. Every "
                             "figure must come from a query. Add it to a query (for example a total, a difference "
                             "or a percentage as an extra column) and list that query, or remove it from the "
                             "text. Then call final_answer again."}
        if loose:                                             # still there: accept, but say so openly
            assumptions.append(f"Figures in the answer text that are not taken from the result tables: "
                               f"{', '.join(loose)}.")
        self.final = _result("answered", answer.strip(), tables=tables,
                             sql=[q["sql"] for q in chosen], assumptions=assumptions)
        return {"ok": True}


def answer_question(question: str, as_of: str, client=None) -> dict:
    try:
        today = dt.date.fromisoformat(as_of)
    except ValueError:
        return _result("clarify", f"The as-of date '{as_of}' is not a valid YYYY-MM-DD date. Which date should I use?")
    started = time.monotonic()
    if client is None:
        from llm import ChatClient, LLMError
        try:
            client = ChatClient()
        except LLMError as e:
            return _failure(str(e))
    session = Session(today, question)
    messages = [{"role": "system", "content": system_prompt(today)},
                {"role": "user", "content": question}]
    nudges = 0
    for step in range(MAX_STEPS):
        remaining = TOTAL_BUDGET_S - (time.monotonic() - started)
        if remaining < 8:
            return _failure("time budget exhausted")
        try:
            message = client.chat(messages, TOOLS, timeout=min(60, remaining - 5))
        except Exception as e:
            log(f"[agent] model error: {e}")
            return _failure("the model call failed")
        calls = message.get("tool_calls") or []
        turn = {"role": "assistant", "content": message.get("content") or ""}
        if calls:
            turn["tool_calls"] = calls
        if "_raw_output" in message:                 # provider items (e.g. reasoning) the client replays next turn
            turn["_raw_output"] = message["_raw_output"]
        messages.append(turn)
        if not calls:
            nudges += 1
            if nudges > 2:
                return _failure("the model stopped calling tools")
            messages.append({"role": "user", "content": "Call a tool. Finish with the final_answer tool."})
            continue
        for call in calls:
            name = (call.get("function") or {}).get("name", "")
            raw = (call.get("function") or {}).get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except ValueError as e:
                args, output = {"_unparsed": str(raw)[:500]}, {"error": f"Tool arguments are not valid JSON: {e}"}
                trace("tool_call", name=name, args=args)
            else:
                trace("tool_call", name=name, args=args)
                output = session.call(name, args)
            trace("tool_result", name=name, content=output)
            log(f"[agent] step {step + 1}: {name} -> {str(output)[:200]}")
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(output)})
        if session.final is not None:
            return session.final
    return _failure("step limit reached")
