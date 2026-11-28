# Design note

## Tools, and why these three

One loop: the model picks the next tool every turn until it calls `final_answer`.

| Tool | What it does | Why |
|---|---|---|
| `get_catalogue` | Relations, columns, coded values and data-quality facts **measured on the current database**. | Nothing about the data is in the prompt, so a second database is described correctly. |
| `run_sql` | Runs one guarded SELECT, returns rows and a `query_id`. | The only way to obtain a figure. |
| `final_answer` | Status, answer text, assumptions, `query_id`s. | `tables` and `sql` are **copied by code from the queries that ran**. No query or no assumptions: sent back. |

## How the agent learns the business rules

1. **Rules that never depend on the question live in SQL views**, where the model cannot forget them:
   `claim_latest` (one row per claim: latest version, status flags, SGD amounts, `'Unknown'`), `claim_icd`
   (one row per claim and diagnosis), `provider_dim` and `doctor_dim` (duplicates merged).
2. **Rules that depend on the question live in one file, `business_rules.md`,** in the system prompt on
   every call. A file, not retrieval: it is short, and retrieval only adds a way to miss a rule. Date
   windows are computed in code from `--as-of`.

## What stops a wrong-but-plausible answer

| Trap found in the data | Plausible wrong answer | What prevents it |
|---|---|---|
| 82,549 rows for 60,000 claims (edits are appended) | Q1 = 1,837 instead of 1,775 | `claim_latest`: the version is picked before any status filter |
| 371 claims with a visit date after as-of (up to 2099) | Inflated all-time totals | Catalogue reports the count; rule `visit_date <= as-of` |
| Amounts in SGD, MYR, IDR; Vietnamese providers bill in SGD | Summing `claim_amt` across currencies; country inferred from currency | `claim_amt_sgd` (amount / rate); country from the provider |
| 22,388 claims with provider id 0 / 90xx and doctor id `''` / `'0'` | An inner join drops 37 % of claims | Left joins, `'Unknown'` group kept |
| 12 providers and 1 doctor entered twice | "412 providers"; one clinic on two rows of a top 10 | Merged only when the other attributes match; namesake doctors stay apart |
| `lookup` rows repeated; `provider.type` is `1`, the code is `'001'` | Doubled counts, or no match | `lookup_clean`, numeric code key |
| 4,048 repeated claim-diagnosis pairs; 1,350 rows with unknown ICD ids | Double counting, dropped claims | `claim_icd`; count distinct claims, groups overlap |
| Timestamps are at 02:00; amounts repeat per diagnosis after a join | A day lost (1,222 vs 1,240); 5.16 M instead of 3.53 M | Rules: compare the day; one row per claim first |

## Safety

Three layers, strongest first, none in the prompt; `run_sql.py` and the agent share `execute_sql`.
(1) **The sensitive text is never loaded**: each call copies the tables from `CLAIMS_DB` (read-only)
into a private in-memory database without `diagnosis_note`, then detaches it.
(2) **Engine settings**: external access off, memory capped, configuration locked. (3) **Parser guard**
(sqlglot AST): one SELECT, allow-listed relations, no `diagnosis_note`; DuckDB's parser must agree.

A red-team pass by a second AI session got past layer 3 once (zero-width characters); layers 1 and 2
held. That gap is closed; results are capped (10,000 rows, 2 MB, 20 s). In production I would enforce
this in the database: read-only role, governed views, timeout.

## Evaluation: what was measured, and what it does not show

98 questions: 83 with a figure, 15 where the right reply is declined / unanswerable / clarify. Expected
answers are hand-written SQL on the raw tables. First-contact results, in order:

- 34 questions, **33 of 34**; one rule and 14 questions later, 48 of 48 (too easy).
- So **42 questions meant to break it** were added: **35 of 42.** Two misses were the questions' fault; the
  rest were real (a share across claim versions: 18.20 % instead of 27.86 %). In response quarter windows are
  computed in code, rules were added and six questions reworded; eight fresh questions written before
  those changes: 8 of 8.
- All 98, five full runs: `medium` 96, 97, 97; `low` 96, 97, with different misses every time. Reported
  run (`eval_summary.json`, at `low`): **96 of 98.**

**This is an upper bound.** Questions, semantic layer and expected SQL have one author and one reading of
the open points below; a different reading by the data owner would not show here.

## What I would ask the data owner, and what I assumed

- **Versions loaded after the as-of date** (624 rows, 1-2 December): the latest version wins; ignoring them
  changes Q1 from 1,775 to 1,766.
- **Duplicates**: 12 providers and the two "Locum Doctor" rows are double entry; doctors with an identical
  name are different people.
- **"Rejected"** = `rejected_on` set on the latest version (4,280 such claims are also approved). **"In MYR"** = the claims billed in MYR. **Diagnosis** = one ICD code.

## With another week

Questions written by someone else on a realistic second database, each run several times; views for
version history; the allow-list taken from the engine's plan.

---

## Models and AI usage

**Model that powers the agent:** OpenAI `gpt-6-luna`, the small low-cost tier, at reasoning effort `low`:
deliberately the weakest setting, because the brief says a cheap model should be enough and the semantic
layer is meant to carry the hard parts. `medium` was measured too: it costs about the same (input tokens
dominate), is about a second slower per question and scored the same on the full set, but its misses were
judgement calls where `low` makes logic errors on multi-step questions; `high` ran past the time limit.
`LLM_REASONING_EFFORT=medium` is the one-line switch. A full 98-question run at `low` uses about 1.4 million
input and 25 thousand output tokens (roughly USD 0.15 at list price), 3 to 10 seconds per question, 5 on
average.

**How it is used:** one tool-calling loop over the OpenAI Responses API (stateless, `store: false`; the
model's reasoning items are replayed between steps). The Responses API is used because, for this model,
chat completions allows function tools only with reasoning switched off. Default sampling settings, at most
14 steps and 100 seconds per question. Every setting has a default, so an API key alone is enough. The
client also speaks plain chat completions (`LLM_API_STYLE=chat`) so a local open-weight model can be
substituted; that path was spot-checked on four questions with reasoning off (4 of 4). The system prompt is
the protocol, the date windows for the given as-of date, and `business_rules.md`. No few-shot examples of
the public questions, no cached answers. No model is used as a judge: the evaluation compares the agent's
tables with the results of hand-written SQL in code.

**AI coding assistants:** the implementation was written by AI coding assistants, from my ideas and under my
direction. ChatGPT / Codex: reading the brief, the first read-only exploration of the CSV files and the
design discussion. Claude Code: re-profiling the data, the code, the tests, the evaluation questions with
their expected SQL, the draft of this note, and two independent review sessions (a data audit and a red-team
test of the SQL layer). My part: the direction and the decisions, including a cheap model, reporting only
measured results, the independent re-audit, and the stress test that produced the failures reported above.
