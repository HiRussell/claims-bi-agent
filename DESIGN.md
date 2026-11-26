# Design note

## Tools, and why these three

One loop: the model picks the next tool every turn until it calls `final_answer`.

| Tool | What it does | Why |
|---|---|---|
| `get_catalogue` | Relations, column meanings, coded values, and data-quality facts **measured on the database it is pointed at** (versions, future dates, unmatched and duplicate providers, bad FX rates). | Nothing about the data is in the prompt, so a second database is described correctly. |
| `run_sql` | Runs one guarded SELECT, returns rows and a `query_id`. | The only way to obtain a figure. |
| `final_answer` | Status, answer text, assumptions, `query_id`s. | `tables` and `sql` are **copied by code from the queries that ran**. No query, no assumptions, or a number in no table: sent back. |

## How the agent learns the business rules

1. **Rules that never depend on the question live in SQL views**, where the model cannot forget them:
   `claim_latest` (one row per claim: latest version, status flags, `claim_amt_sgd`, provider and doctor
   attributes with `'Unknown'`), `claim_icd` (one row per claim and diagnosis), `provider_dim` and
   `doctor_dim` (duplicates merged).
2. **Rules that depend on the question live in one file, `business_rules.md`,** in the system prompt on
   every call: approved by default, net amount, SGD, windows on `visit_date`, Unknown in rankings, when to
   decline / clarify / say unanswerable. A file, not retrieval: it is short, and retrieval only adds a way
   to miss a rule. Date windows are computed in code from `--as-of`.

## What the data does, and what stops a wrong-but-plausible answer

| Trap found in the data | Plausible wrong answer | What prevents it |
|---|---|---|
| 82,549 rows for 60,000 claims (edits are appended) | Q1 = 1,837 instead of 1,775; filtering approved first keeps 1,215 claims that were later voided | `claim_latest`: the version is picked before any status filter |
| 371 claims with a visit date after as-of (up to 2099) | Inflated all-time totals | Catalogue reports the count; rule `visit_date <= as-of` |
| Amounts in SGD, MYR, IDR; Vietnamese providers bill in SGD | Summing `claim_amt` across currencies; country inferred from currency | `claim_amt_sgd` (rate is local per SGD, so divide); country comes from the provider |
| 22,388 claims with provider id 0 / 90xx and doctor id `''` / `'0'` | An inner join drops 37 % of claims | Left joins, `'Unknown'` group kept |
| 12 providers and 1 doctor entered twice (ids 401-412 lower-cased plus a dot; "Locum Doctor" / "Locum doctor") | "412 providers"; one clinic on two rows of a top 10 | Providers merged when name, type, country, region match; doctors only when one name is typed two ways |
| `lookup` rows repeated; `provider.type` is `1`, the code is `'001'` | Doubled counts, or no match | `lookup_clean`, numeric code key |
| 4,048 repeated claim-diagnosis pairs; 1,350 rows point at 20 ICD ids that do not exist; several diagnoses per claim | Double counting, dropped claims | `claim_icd`; count distinct claims, groups overlap |
| Every timestamp is at 02:00; an amount repeats per diagnosis after a join | A day lost (1,222 vs 1,240); 5.16 M instead of 3.53 M | Rules: compare the day; one row per claim first |

## Safety

Three layers, strongest first, none a prompt instruction. `run_sql.py` and the agent share `execute_sql`.

1. **The sensitive text is never loaded.** Each call copies the eight tables from `CLAIMS_DB` (attached
   read-only) into a private in-memory database without `diagnosis_note`, then detaches the file. A bypass
   could at most touch a throw-away copy.
2. **Engine settings**: external access off, memory capped, configuration locked.
3. **Parser guard** (sqlglot AST): one SELECT, allow-listed relations, no schema-qualified names, table
   functions or file paths, no identifier `diagnosis_note`, unknown functions only from an allow-list;
   DuckDB's own parser must agree.

An independent red-team pass (a second AI session) got past layer 3 once: zero-width characters are white
space to DuckDB and part of a name to sqlglot, which exposed view definitions; layers 1 and 2 kept notes,
writes and files out of reach. Now such characters are refused,
errors do not quote data, and results are capped (10,000 rows, 2,000 characters per cell, 2 MB, 20 seconds).
In production I would enforce this in the database (read-only role, governed views, timeout).

## Evaluation: what was measured, and what it does not show

98 questions: 83 with a figure, 15 where the right reply is declined / unanswerable / clarify. Expected
answers are per-question SQL on the raw tables, written independently of the agent in a different technique
from the views; three use a second, 6-claim database with another as-of date. In order, on first contact:

- 34 questions, **33 of 34**: *"How many unique patients had an approved claim last month?"* got the claim
  count plus a caveat. One rule later ("a claim is not a person"): 5 of 5. Ten unseen questions: 10 of 10;
  an independent reviewer given only the database matched Q1-Q9; 20 paraphrases: 20 of 20.
- That made 48 of 48, which says more about the questions than the agent, so **42 questions meant to break
  it** were added: **35 of 42.** Two misses were the questions' fault. The real ones: wrong logic across
  claim versions (27.86 % reported as 18.20 %), "last 2 quarters" read as six months, `Unknown` dropped from
  a per-country figure, 02:00 on day 3 counted as "more than 3 days".
- The cause was mostly reasoning effort: a repeat at `low` gave 37 with different misses, `medium` 39 (its
  three misses were under-specified questions), `high` ran out of time. So the default became `medium`,
  quarter windows are computed in code, rules were added, six questions were reworded. Eight fresh
  questions written before those changes: 8 of 8.
- All 98 at `medium`, twice: **96 and 97**, different misses: three doctors sharing a name added into one
  figure; `Unknown` counted as a provider (side effect of a new rule, then corrected); one needless question.
- Reported run (`eval_summary.json`): **97 of 98.** "How much did we pay out last month?" was called
  unanswerable (no payment records) though approved claims are the ones paid: the price of the "no
  substitutes" rule. Three runs, three different misses.

**This is an upper bound.** Questions and semantic layer have the same author, and the expected SQL shares
one reading of the open points below; where the data owner reads them differently the agent is consistently
wrong and this evaluation cannot show it.

## What I would ask the data owner, and what I assumed

- **Versions loaded after the as-of date** (624 rows, 1-2 December): the latest version wins; ignoring them
  changes Q1 from 1,775 to 1,766.
- **Duplicates**: 12 providers and the two "Locum Doctor" rows are double entry; doctors with an identical
  name (18 names) are different people.
- **"Rejected"** = `rejected_on` set on the latest version, window on `visit_date` (4,280 such claims are
  also approved). **"In MYR"** = the claims billed in MYR. **Diagnosis** = one ICD code.

## With another week

Questions written by someone else on a realistic second database, each run several times; views for
version history, where the agent still reasons unaided; the allow-list taken from the engine's plan.

---

## Models and AI usage

**Model that powers the agent:** OpenAI `gpt-6-luna`, the small low-cost tier, chosen because the brief
says a cheap model should be enough and the semantic layer is meant to carry the hard parts. Reasoning
effort is `medium`, chosen on the evaluation: `low` is about 2 seconds faster per question but made logic
errors on multi-step questions and gave different results on a repeat, and `high` ran past the time limit.
A full 98-question run uses about 1.4 million input and 38 thousand output tokens (roughly USD 0.16 at
list price) and takes 3 to 13 seconds per question, 6 on average.

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
