"""Checks that your submission follows the contract in section 7 of the brief. Run it from the repository root:

    python check_contract.py --db claims.duckdb

It runs your two commands on a copy of the database and prints PASS / WARN / FAIL for each check.
It does not judge whether your answers are right.
"""
import argparse, json, os, shlex, shutil, subprocess, sys, tempfile

QUESTION = "How many drugs are in the drug table?"
STATUSES = {"answered", "clarify", "declined", "unanswerable"}


def validate(r):
    if not isinstance(r, dict):
        return "output is not a JSON object"
    if r.get("status") not in STATUSES:
        return f"'status' must be one of {sorted(STATUSES)}"
    for k, typ in (("answer", str), ("tables", list), ("sql", list), ("assumptions", list)):
        if not isinstance(r.get(k), typ):
            return f"'{k}' missing or not a {typ.__name__}"
    for t in r["tables"]:
        if not (isinstance(t, dict) and isinstance(t.get("columns"), list) and isinstance(t.get("rows"), list)):
            return "each table needs 'columns' and 'rows' lists"
    return None


def run(cmd, args, env, cwd, timeout=120):
    try:
        p = subprocess.run(shlex.split(cmd) + args, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s (the limit is 2 minutes per question)"
    except OSError as e:
        return None, f"could not start the command ({e}). Check the command line in submission.json."
    try:
        return json.loads(p.stdout), None
    except Exception:
        shown = (f"stdout starts with {p.stdout[:150]!r}" if p.stdout.strip()
                 else f"stdout is empty, stderr ends with {p.stderr.strip()[-200:]!r}")
        return None, f"stdout is not a single JSON object (exit {p.returncode}): {shown}. Only the JSON object may go to stdout; logs belong on stderr."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--as-of", default="2026-11-30")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        sys.exit(f"FAIL  database not found: {a.db} (pass the path to claims.duckdb with --db)")
    results = []

    def check(level, name, detail=""):
        results.append(level)
        print(f"{level:<5} {name}" + (f": {detail}" if detail else ""))

    try:
        sub = json.load(open("submission.json"))
        agent_cmd, sql_cmd = sub["agent_cmd"], sub["sql_cmd"]
        check("PASS", "submission.json has agent_cmd and sql_cmd")
    except Exception as e:
        check("FAIL", "submission.json", f"cannot read agent_cmd / sql_cmd ({e})")
        return sys.exit(1)

    check("PASS" if os.path.exists(".env.example") else "WARN", ".env.example in the repository root")

    work = tempfile.mkdtemp()
    db = os.path.join(work, "claims.duckdb")
    shutil.copy(a.db, db)
    trace = os.path.join(work, "trace.jsonl")
    env = dict(os.environ, CLAIMS_DB=db, TRACE_FILE=trace)

    r, err = run(agent_cmd, ["--question", QUESTION, "--as-of", a.as_of], env, None)
    if err:
        check("FAIL", "agent command prints one JSON object", err)
    else:
        bad = validate(r)
        check("FAIL" if bad else "PASS", "agent output has the required fields", bad or f"status={r['status']}")
        if not bad and r["status"] == "answered":
            ok = any(200 in [c for row in t["rows"] for c in row] for t in r["tables"])
            check("PASS" if ok else "WARN", f"figure for '{QUESTION}' is in tables", "" if ok else "expected the number 200 in a table")
    if os.path.exists(trace) and os.path.getsize(trace) > 0:
        check("PASS", "trace file written")
    else:
        check("WARN", "trace file is empty", "append tool events to TRACE_FILE (section 7.3)")

    r, err = run(sql_cmd, ["--sql", "SELECT count(*) AS n FROM drug"], env, None)
    if err:
        check("FAIL", "sql command prints one JSON object", err)
    elif r.get("ok") is True and r.get("rows") == [[200]]:
        check("PASS", "sql command runs a normal SELECT")
    else:
        check("FAIL", "sql command runs a normal SELECT", f"got {str(r)[:150]}")
    if results[-1] == "PASS":
        r, err = run(sql_cmd, ["--sql", "DELETE FROM drug"], env, None)
        check("PASS" if (not err and r.get("ok") is False) else "FAIL", "sql command rejects a write", err or "")
    else:
        check("WARN", "write check skipped", "needs a working SELECT first")
    shutil.rmtree(work, ignore_errors=True)

    print(f"\n{results.count('FAIL')} fail, {results.count('WARN')} warn, {results.count('PASS')} pass")
    sys.exit(1 if "FAIL" in results else 0)


if __name__ == "__main__":
    main()
