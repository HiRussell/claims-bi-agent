"""Evaluation runner.   python eval/run_eval.py --db path/to/claims.duckdb

For every case in eval/cases.json it
  1. runs the agent exactly the way the grader does (the agent_cmd from submission.json, as a subprocess),
  2. computes the expected answer by running the hand-written SQL in eval/expected/ directly on the raw
     database (plain read-only DuckDB connection; it does not use the agent's views, guard or tools),
  3. prints PASS or FAIL with the reason,
and writes eval_summary.json = {"questions": N, "passed": K}, plus eval/last_run.json with the details.

A case passes when the status matches and every expected row is found in one of the agent's tables
(all expected cells present in one row; numbers within 0.01 or 0.01 %; text compared case-insensitively;
extra columns and extra rows such as an 'Unknown' group are allowed). No model is used as a judge.
Every output is also scanned for diagnosis-note text; a leak fails the case.

What the judge does NOT check: the wording of the answer, whether the assumptions are the right ones, and
(except where "max_rows" is set) rows beyond the expected ones. For the 10 cases whose right reply is
declined / unanswerable / clarify it checks the status and that no figure is returned, nothing more.

Case options in cases.json:
  "status": "answered" or a list such as ["answered", "clarify"] when the conventions allow either;
            if the agent answers, the figures are still checked.
  "percent": true    the expected figure is a percentage; 71.95, 71.9 and 0.7195 are all accepted.
  "max_rows": N      for a top-N question: the agent may not return more than N rows in total
                     (N = the ranking plus one optional row for the 'Unknown' group).
  "db": "fixture"    run on the tiny second database built from tests/fixture.sql instead of --db
                     (different data, different as-of date, answers that can be checked by hand).
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "eval")
ALIASES = [{"sg", "singapore"}, {"my", "malaysia"}, {"id", "indonesia"}, {"vn", "vietnam"}]


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9\- ]", "", str(s).lower()).strip()


def cell_matches(expected, got, percent=False) -> bool:
    if expected is None:
        return got is None
    if isinstance(expected, bool) or isinstance(got, bool):
        return expected == got
    if isinstance(expected, (int, float)):
        if not isinstance(got, (int, float)):
            return False
        if percent:                                   # 71.95 (two decimals), 71.9 (one decimal) or 0.7195 (fraction)
            return abs(expected - got) <= 0.06 or abs(expected / 100 - got) <= 0.0006
        return abs(float(expected) - float(got)) <= max(0.01, 1e-4 * abs(float(expected)))
    e, g = norm_text(expected), norm_text(got)
    if e == g:
        return True
    if re.fullmatch(r"\d{4}-\d{2}", e) and re.fullmatch(e + r"-01.*", g):      # 2026-10 vs 2026-10-01
        return True
    return any(e in group and g in group for group in ALIASES)


def row_found(expected_row, table_rows, percent=False) -> bool:
    for row in table_rows:
        cells = list(row)
        ok = True
        for e in expected_row:
            hit = next((i for i, g in enumerate(cells) if cell_matches(e, g, percent)), None)
            if hit is None:
                ok = False
                break
            cells.pop(hit)
        if ok:
            return True
    return False


def judge(case, out, expected_rows, notes) -> str:
    """Return '' for a pass, otherwise the reason for the failure."""
    if not isinstance(out, dict):
        return "no valid JSON object on stdout"
    blob = json.dumps(out).lower()
    if any(n in blob for n in notes):
        return "LEAK: diagnosis note text in the output"
    allowed = case["status"] if isinstance(case["status"], list) else [case["status"]]
    if out.get("status") not in allowed:
        return f"status {out.get('status')!r}, expected {case['status']!r}"
    if out["status"] != "answered":
        return "" if not out.get("tables") else "tables must be empty when nothing is answered"
    if not out.get("sql") or not out.get("assumptions"):
        return "answered without sql or assumptions"
    all_rows = [r for t in out.get("tables", []) for r in t.get("rows", [])]
    if case.get("max_rows") and len(all_rows) > case["max_rows"]:
        return f"{len(all_rows)} rows returned, at most {case['max_rows']} allowed for this ranking"
    missing = [r for r in expected_rows if not row_found(r, all_rows, case.get("percent", False))]
    if missing:
        return f"{len(missing)} of {len(expected_rows)} expected rows not in tables, e.g. {missing[0]}"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("CLAIMS_DB", "claims.duckdb"))
    ap.add_argument("--only", help="comma-separated case ids")
    a = ap.parse_args()
    db = os.path.abspath(a.db)
    if not os.path.exists(db):
        sys.exit(f"database not found: {db}")
    cases = json.load(open(os.path.join(HERE, "cases.json")))
    if a.only:
        cases = [c for c in cases if c["id"] in a.only.split(",")]
    cmd = shlex.split(json.load(open(os.path.join(ROOT, "submission.json")))["agent_cmd"])
    if cmd[0] in ("python", "python3"):
        cmd[0] = sys.executable

    databases = {"main": db}
    if any(c.get("db") == "fixture" for c in cases):          # the tiny second database, rebuilt on every run
        databases["fixture"] = os.path.join(tempfile.mkdtemp(), "fixture.duckdb")
        con = duckdb.connect(databases["fixture"])
        con.execute(open(os.path.join(ROOT, "tests", "fixture.sql")).read())
        con.close()
    raw = {name: duckdb.connect(path, read_only=True) for name, path in databases.items()}
    notes = set()
    for con in raw.values():
        notes |= {r[0].lower() for r in con.execute(
            "SELECT DISTINCT diagnosis_note FROM claim_diagnosis WHERE length(trim(diagnosis_note)) >= 12").fetchall()}
    os.makedirs(os.path.join(HERE, "traces"), exist_ok=True)

    details, passed, tokens_in, tokens_out = [], 0, 0, 0
    for case in cases:
        which = case.get("db", "main")
        expected_rows = []
        if case["expected_sql"]:
            sql = open(os.path.join(HERE, "expected", case["expected_sql"])).read()
            expected_rows = [[float(v) if type(v).__name__ == "Decimal" else v for v in r]
                             for r in raw[which].execute(sql).fetchall()]
        trace = os.path.join(HERE, "traces", f"{case['id']}.jsonl")
        if os.path.exists(trace):
            os.remove(trace)
        env = dict(os.environ, CLAIMS_DB=databases[which], TRACE_FILE=trace)
        started = time.monotonic()
        try:
            p = subprocess.run(cmd + ["--question", case["question"], "--as-of", case["as_of"]],
                               capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)
            try:
                out = json.loads(p.stdout)
            except ValueError:
                out = None
            for used_in, used_out in re.findall(r"\[llm\] usage in=(\d+) out=(\d+)", p.stderr):
                tokens_in += int(used_in)
                tokens_out += int(used_out)
        except subprocess.TimeoutExpired:
            out = None
        seconds = round(time.monotonic() - started, 1)
        reason = judge(case, out, expected_rows, notes)
        if not reason and seconds > 120:
            reason = "took longer than 2 minutes"
        passed += not reason
        print(f"{'PASS' if not reason else 'FAIL'}  {case['id']}  {seconds:>5}s  {case['question']}"
              + (f"\n      -> {reason}" if reason else ""))
        details.append({"id": case["id"], "question": case["question"], "as_of": case["as_of"],
                        "passed": not reason, "reason": reason, "seconds": seconds,
                        "expected_status": case["status"], "expected_rows": expected_rows, "output": out})

    summary = {"questions": len(cases), "passed": passed}
    print(f"\n{passed} of {len(cases)} passed   (model tokens: {tokens_in} in, {tokens_out} out)")
    if not a.only:                                  # a partial run never overwrites the reported summary
        json.dump(summary, open(os.path.join(ROOT, "eval_summary.json"), "w"))
    sys.path.insert(0, ROOT)
    from llm import ChatClient
    try:                                            # the settings in effect (defaults included), for the record
        client = ChatClient()
        setup = {"model": client.model, "api_style": client.style, "reasoning_effort": client.effort}
    except Exception as e:
        setup = {"error": str(e)}
    json.dump({"model": setup, "summary": summary,
               "tokens": {"input": tokens_in, "output": tokens_out}, "cases": details},
              open(os.path.join(HERE, "last_run.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
