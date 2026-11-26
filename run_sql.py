"""Contract command 2:  python run_sql.py --sql "SELECT count(*) FROM claim"   (prints one JSON object)"""
import argparse

from contract import to_json
from sql_tool import execute_sql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True)
    a = ap.parse_args()
    try:
        res = execute_sql(a.sql)
        out = {"ok": True, "columns": res["columns"], "rows": res["rows"]}
        if res.get("truncated"):                    # a row, cell or size cap cut the result
            out["truncated"] = True
    except Exception as e:
        out = {"ok": False, "error": str(e)[:300]}
    print(to_json(out))


if __name__ == "__main__":
    main()
