# Design note

## Tools, and why these three

One loop, driven by the model: it picks the next tool every turn until it calls `final_answer`.

| Tool | What it does | Why |
|---|---|---|
| `get_catalogue` | Relations, column meanings, coded values, and data-quality facts **measured on the database it is pointed at** (versions per claim, future visit dates, unmatched and duplicate providers, unusable FX rates). | Nothing about the data is in the prompt, so a second database is described correctly. |
| `run_sql` | Runs one guarded SELECT, returns rows and a `query_id`. | The only way to obtain a figure. |
| `final_answer` | Status, answer text, assumptions, `query_id`s. | `tables` and `sql` are **copied by code from the queries that ran**. No query, no assumptions, or a number in the text that is in no table: sent back. |

## How the agent learns the business rules

1. **Rules that never depend on the question live in SQL views**, where the model cannot forget them.
   `claim_latest` is one row per claim: latest loaded version, `is_approved` / `is_rejected` / `is_voided`,
   `claim_amt_sgd = claim_amt / currency_rate`, provider and doctor attributes with `'Unknown'` for missing
   attribution. `claim_icd` is one row per claim and diagnosis. `provider_dim` / `doctor_dim` merge duplicates.
2. **Rules that depend on the question live in one page, `business_rules.md`,** in the system prompt on
   every call: approved by default, net amount, SGD, windows on `visit_date`, Unknown in rankings, when to
   decline / clarify / say unanswerable. A file, not retrieval: the rules fit in one page, and retrieval
   would only add a way to miss one. Date windows are computed in code from `--as-of`.

## What the data does, and what stops a wrong-but-plausible answer

| Trap found in the data | Plausible wrong answer | What prevents it |
|---|---|---|
| 82,549 rows for 60,000 claims (edits are appended) | Q1 = 1,837 instead of 1,775 | `claim_latest` |
| Filter approved first, then take the latest version | Keeps 1,215 claims whose latest version is voided | Versions are ranked before any status filter |
| 371 claims with a visit date after as-of (up to 2099) | Inflated all-time totals | Catalogue reports the count; rule `visit_date <= as-of` |
| Amounts in SGD, MYR, IDR; Vietnamese providers bill in SGD | Summing `claim_amt` across currencies; country inferred from currency | `claim_amt_sgd` (rate is local per SGD, so divide); country comes from the provider |
| 22,388 claims with provider id 0 / 90xx and doctor id `''` / `'0'` | An inner join drops 37 % of claims | Left joins, `'Unknown'` group kept |
| 12 providers and 1 doctor entered twice (ids 401-412 lower-cased plus a dot; "Locum Doctor" / "Locum doctor") | "412 providers"; one clinic on two rows of a top 10 | Providers merged when name, type, country, region match; doctors only when one name is typed two ways |
| `lookup` rows repeated; `provider.type` is `1`, the code is `'001'` | Doubled counts, or no match | `lookup_clean`, numeric code key |
| 4,048 repeated claim-diagnosis pairs; 1,350 rows point at 20 ICD ids that do not exist; several diagnoses per claim | Double counting, dropped claims | `claim_icd`; count distinct claims, groups overlap |
| Every timestamp is at 02:00; an amount repeats per diagnosis after a join | `<= DATE` loses a day (1,222 vs 1,240); 5.16 M instead of 3.53 M | Two rules: compare the day; reduce to one row per claim first |

## Safety

Three layers, strongest first, none a prompt instruction. `run_sql.py` and the agent share `execute_sql`.

1. **The sensitive text is never loaded.** Each call copies the eight tables from `CLAIMS_DB` (attached
   read-only) into a private in-memory database without `diagnosis_note`, then detaches the file. The copy
   is written during setup only; a bypass could at most touch a throw-away copy.
2. **Engine settings**: external access off, memory capped, configuration locked.
3. **Parser guard** (sqlglot AST): one SELECT, allow-listed relations, no schema-qualified names, table
   functions or file paths, no identifier `diagnosis_note`, unknown functions only from an allow-list;
   DuckDB's own parser must agree it is one SELECT.

An independent red-team pass (a second AI session given the code, not my conclusions) got past layer 3
once: zero-width characters are white space to DuckDB and part of a name to sqlglot, which exposed view
definitions. Notes, writes and files stayed out of reach thanks to layers 1 and 2. Now such characters are
refused, errors do not quote data, and results are capped (10,000 rows, 2,000 characters per cell, 2 MB,
20 seconds). In production I would enforce this in the database (read-only role, governed views, timeout).

## Evaluation: what was measured, and what it does not show

48 questions: 38 with a figure, 10 where the right reply is declined / unanswerable / clarify. Expected
answers are hand-written SQL on the raw tables, in a different technique from the views; three questions run
on a second, 6-claim database with another as-of date. In order, each on first contact:

- 17 questions: 17 of 17. Too easy, so 17 harder ones were written before running them: **33 of 34.**
- The failure: *"How many unique patients had an approved claim last month?"* got the claim count (1,775)
  plus a caveat, 4 times out of 5. There is no patient id, so this is a plausible wrong number. One new rule
  ("a claim is not a person; a caveat does not turn a substitute into an answer"): 5 of 5.
- 10 more unseen questions, written before that fix and run without it: 10 of 10.
- Independent audit: a reviewer given only the database got the same nine answers for Q1-Q9; 20 paraphrases
  of the public questions, 20 of 20; one answer quoted a figure the model had computed itself.
- Final set of 48 (4 added for what the audit found): **48 of 48**, on two consecutive full runs.

**This is an upper bound.** I wrote the questions and the semantic layer, and the expected SQL shares my
reading of the open points below: where the data owner reads them differently, the agent is consistently
wrong and this evaluation cannot show it. The judge allows extra rows and does not read the answer text.

## What I would ask the data owner, and what I assumed

- **Versions loaded after the as-of date** (624 rows, 1-2 December): the latest version wins; ignoring them
  changes Q1 from 1,775 to 1,766.
- **Duplicates**: 12 providers and the two "Locum Doctor" rows are treated as double entry; doctors with an
  identical name (18 names) as different people.
- **"Rejected"**: `rejected_on` set on the latest version, window on `visit_date`; 4,280 claims are both
  rejected and approved.
- **A named currency** ("in MYR"): the claims billed in it, local amount. **Diagnosis** = one ICD code.
  **Unknown in a top N**: outside the ranking, reported separately.

## With another week

- Questions and paraphrases written by someone else, run several times, on a realistic second database.
- Take the relation allow-list from the engine's bound plan, not from a second parser.
- Make each open assumption a switch: a configuration change once the data owner answers.

---

## Models and AI usage

**Model that powers the agent:** OpenAI `gpt-6-luna`, the small low-cost tier, with reasoning effort `low`.
Chosen because the brief says a cheap model should be enough and the semantic layer is meant to carry the
hard parts. A full run of the evaluation uses about 0.6 million input and 11 thousand output tokens
(roughly USD 0.07 at list price) and takes 3 to 12 seconds per question.

**How it is used:** one tool-calling loop over the OpenAI Responses API (stateless, `store: false`; the
model's reasoning items are replayed between steps). The Responses API is used because, for this model,
chat completions allows function tools only with reasoning switched off. Default sampling settings, at most
14 steps and 100 seconds per question. Every setting has a default, so an API key alone is enough. The
client also speaks plain chat completions (`LLM_API_STYLE=chat`) so a local open-weight model can be
substituted; that path was spot-checked on four questions with reasoning off (4 of 4). The system prompt is
the protocol, the date windows for the given as-of date, and `business_rules.md`. No few-shot examples of
the public questions, no cached answers. No model is used as a judge: the evaluation compares the agent's
tables with the results of hand-written SQL in code.

**AI coding assistants:** ChatGPT / Codex were used to read the brief and for the first read-only
exploration of the CSV files. Claude Code was used to re-profile the data, write the code, the tests, the
evaluation questions with their expected SQL, and the first draft of this note. Two further Claude Code
sessions acted as independent reviewers (a data audit and a red-team test of the SQL layer); what they found
is described above. I reviewed the business rules, the SQL and the assumptions, and I can explain each of them.
