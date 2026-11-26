# Claims BI agent

A small BI agent that answers natural-language questions over the claims DuckDB database and returns the
figures together with the SQL that produced them. Design notes are in [DESIGN.md](DESIGN.md).

## Setup (about 2 minutes)

Requires Python 3.10 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in LLM_API_KEY (the other values are preset for OpenAI gpt-6-luna)
```

The agent talks to the OpenAI Responses API or to any OpenAI-compatible chat-completions endpoint that
supports tool calling. Configuration
is read from environment variables (a `.env` file in the repository root is loaded if present; real
environment variables take precedence):

| Variable | Meaning |
|---|---|
| `LLM_BASE_URL` | Endpoint base URL, for example `https://api.openai.com/v1` or `http://localhost:11434/v1` |
| `LLM_API_KEY` | API key (leave empty for a local server without authentication) |
| `LLM_MODEL` | Model name, for example `gpt-6-luna` |
| `LLM_API_STYLE` | `responses` (OpenAI Responses API) or `chat` (chat completions, the default; works with any OpenAI-compatible server) |
| `LLM_REASONING_EFFORT` | Optional reasoning effort for reasoning models (`none`, `low`, `medium`, `high`); empty = model default |
| `LLM_TEMPERATURE` | Optional sampling temperature; empty = model default |
| `CLAIMS_DB` | Path to the DuckDB file (set by the grader) |
| `TRACE_FILE` | JSONL file that receives one line per tool call and per tool result |

To use a local open-weight model, serve it behind an OpenAI-compatible endpoint (for example
`ollama serve`, vLLM or LM Studio), set `LLM_API_STYLE=chat`, and point `LLM_BASE_URL` / `LLM_MODEL` at it.

## Run

```bash
export CLAIMS_DB=/path/to/claims.duckdb
python run_agent.py --question "How many approved claims were there last month?" --as-of 2026-11-30
python run_sql.py --sql "SELECT count(*) AS n FROM claim"
python check_contract.py --db /path/to/claims.duckdb
```

`run_agent.py` prints one JSON object on stdout; logs go to stderr. Both commands call the same
`sql_tool.execute_sql`, so `run_sql.py` exercises the real guard and the real connection setup.

## Tests and evaluation

```bash
python -m unittest discover -s tests -v               # offline: no model, no network, tiny hand-checkable database
python eval/run_eval.py --db /path/to/claims.duckdb   # runs the agent on every case; needs the model (about 4 minutes)
```

- `eval/cases.json` lists the 44 questions with the as-of date and the expected status: 34 that have a
  figure and 10 where the right reply is `declined`, `unanswerable` or `clarify`.
- `eval/expected/*.sql` holds the hand-written expected SQL, one file per question. It runs on the raw
  tables through a plain read-only DuckDB connection and does not use the agent's views, guard or tools.
- Three cases (`"db": "fixture"`) run on a second, tiny database built from `tests/fixture.sql`: different
  data, a different as-of date, answers that can be checked by hand.
- The runner calls the agent through the `agent_cmd` in `submission.json`, prints PASS / FAIL per question,
  and writes `eval_summary.json` (`{"questions": N, "passed": K}`) and `eval/last_run.json` (the agent's
  full output, the expected rows and the failure reason for every case). No model is used as a judge.
- `python eval/run_eval.py --db ... --only q01,h08` runs a subset and leaves `eval_summary.json` untouched.

## Layout

| File | Role |
|---|---|
| `run_agent.py`, `run_sql.py` | The two contract commands |
| `agent.py` | The tool loop, the three tools, date windows, the live catalogue |
| `business_rules.md` | Business rules given to the model on every call |
| `sql_tool.py` | `execute_sql`: guard, then run with a time and row cap |
| `sql_guard.py` | Parser-level allow-list (single SELECT, known relations and functions, no `diagnosis_note`) |
| `claims_db.py` | Connection setup and the semantic-layer views |
| `llm.py` | Minimal model client: Responses API and chat completions (standard library) |
| `eval/` | Cases, expected SQL, runner, results of the last full run |
| `tests/` | Offline tests and the fixture database |
