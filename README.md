# Claims BI agent

A small BI agent that answers natural-language questions over the claims DuckDB database and returns the
figures together with the SQL that produced them. Design notes are in [DESIGN.md](DESIGN.md).

## Setup (about 2 minutes)

Tested with Python 3.12 and 3.14.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in LLM_API_KEY
```

**Only an API key is needed.** Every other setting has a default (OpenAI, `gpt-6-luna`, Responses API,
reasoning effort `low`), and the key is read from `LLM_API_KEY` or, failing that, `OPENAI_API_KEY`. Settings
come from environment variables; a `.env` file in the repository root is loaded if present, and real
environment variables take precedence.

| Variable | Meaning | Default |
|---|---|---|
| `LLM_API_KEY` | API key (`OPENAI_API_KEY` is read as a fallback; not needed for a local server) | none |
| `LLM_BASE_URL` | Endpoint base URL (`OPENAI_BASE_URL` as a fallback) | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model name | `gpt-6-luna` |
| `LLM_API_STYLE` | `responses` (OpenAI Responses API) or `chat` (chat completions, any OpenAI-compatible server) | `responses` for api.openai.com, otherwise `chat` |
| `LLM_REASONING_EFFORT` | Reasoning effort for reasoning models (`none`, `low`, `medium`, `high`); set it empty for the model's own default | on OpenAI: `low` (`none` with `chat`, where tools require it) |
| `LLM_TEMPERATURE` | Sampling temperature | the model's default |
| `CLAIMS_DB` | Path to the DuckDB file (set by the grader) | `claims.duckdb` |
| `TRACE_FILE` | JSONL file that receives one line per tool call and per tool result | no trace |

To use a local open-weight model, serve it behind an OpenAI-compatible endpoint (for example
`ollama serve`, vLLM or LM Studio) and set `LLM_BASE_URL` and `LLM_MODEL`.

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
python eval/run_eval.py --db /path/to/claims.duckdb   # runs the agent on every case; needs the model (about 9 minutes)
```

- `eval/cases.json` lists the 98 questions with the as-of date and the expected status: 83 that have a
  figure and 15 where the right reply is `declined`, `unanswerable` or `clarify`. Ids starting with `s`,
  `r`, `k`, `m`, `y`, `g`, `p`, `z`, `n` are the stress set written to find where the agent breaks.
- `eval/expected/*.sql` holds the hand-written expected SQL, one file per question. It runs on the raw
  tables through a plain read-only DuckDB connection and does not use the agent's views, guard or tools.
- Three cases (`"db": "fixture"`) run on a second, tiny database built from `tests/fixture.sql`: different
  data, a different as-of date, answers that can be checked by hand.
- The runner calls the agent through the `agent_cmd` in `submission.json`, prints PASS / FAIL per question,
  and writes `eval_summary.json` (`{"questions": N, "passed": K}`) and `eval/last_run.json` (the agent's
  full output, the expected rows and the failure reason for every case). No model is used as a judge.
- The reported run passes 96 of 98. Which questions fail changes from run to run (five full runs, 96 or 97
  each time, never the same misses); `eval/last_run.json` has the failing answers and DESIGN.md the history.
- The expected SQL contains literal dates and ids for the provided database and its reference date
  (2026-11-30); it is not meant to be run against another database.
- What the judge does not check: the wording of the answer, whether the stated assumptions are the right
  ones, and (except for rankings, which carry a `max_rows` cap) rows beyond the expected ones.
- `python eval/run_eval.py --db ... --only q01,h08` runs a subset and leaves `eval_summary.json` untouched.

## Layout

| File | Role |
|---|---|
| `run_agent.py`, `run_sql.py` | The two contract commands |
| `agent.py` | The tool loop, the three tools, date windows, the live catalogue |
| `business_rules.md` | Business rules given to the model on every call |
| `sql_tool.py` | `execute_sql`: guard, then run with time, row and size caps; errors never quote data |
| `sql_guard.py` | Parser-level guard (single SELECT, allow-listed relations, no `diagnosis_note`, no invisible characters) |
| `claims_db.py` | Connection setup and the semantic-layer views |
| `llm.py` | Minimal model client: Responses API and chat completions (standard library) |
| `eval/` | Cases, expected SQL, runner, results of the last full run |
| `tests/` | Offline tests and the fixture database |
