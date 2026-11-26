"""Contract command 1:  python run_agent.py --question "..." --as-of 2026-11-30   (prints one JSON object)"""
import argparse, traceback

from agent import answer_question
from contract import log, to_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--as-of", required=True)
    a = ap.parse_args()
    try:
        result = answer_question(a.question, a.as_of)
    except Exception:                           # always emit valid JSON; the traceback goes to stderr only
        log(traceback.format_exc())
        result = {"status": "unanswerable", "answer": "The agent hit an internal error. No figure is reported.",
                  "tables": [], "sql": [], "assumptions": []}
    print(to_json(result))


if __name__ == "__main__":
    main()
