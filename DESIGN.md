# Design note

## Tools, and why these three

One loop, driven by the model: it picks the next tool every turn until it calls `final_answer`.

| Tool | What it does | Why |
|---|---|---|
| `get_catalogue` | Relations, column meanings, values of coded columns, and data-quality facts **measured on the database it is pointed at** (versions per claim, future visit dates for the given as-of, unmatched providers, unusable FX rates, duplicate providers). | Nothing about the data is written into the prompt, so the agent describes a second database correctly. |
| `run_sql` | Runs one guarded SELECT, returns rows and a `query_id`. | The only way to obtain a figure. |
| `final_answer` | Status, answer text, assumptions and a list of `query_id`s. | `tables` and `sql` are **copied by code from the queries that ran**; the model cannot type a number into a table. `answered` without a query or without assumptions is rejected and sent back. |

## How the agent learns the business rules

1. **Rules that never depend on the question live in SQL views**, where the model cannot forget them.
   `claim_latest` is one row per claim: latest loaded version, `is_approved` / `is_rejected` / `is_voided`,
   `claim_amt_sgd = claim_amt / currency_rate`, provider and doctor attributes with `'Unknown'` for missing
   attribution. `claim_icd` is one row per claim and diagnosis. `provider_dim` merges duplicate providers.
2. **Rules that depend on the question live in one page, `business_rules.md`,** in the system prompt on
   every call: approved by default, net amount, SGD, windows on `visit_date`, Unknown in rankings, when to
   decline / clarify / say unanswerable. A file rather than retrieval: the rules fit in one page, and
   retrieval would only add a way to miss one. Date windows are computed in code from `--as-of` and handed
   over as literal dates, because month arithmetic is where off-by-one errors come from.

## What the data does, and what stops a wrong-but-plausible answer

| Trap found in the data | Plausible wrong answer | What prevents it |
|---|---|---|
| 82,549 rows for 60,000 claims (edits are appended) | Q1 = 1,837 instead of 1,775 | `claim_latest` |
| Filter approved first, then take the latest version | Keeps 1,215 claims whose latest version is voided | Versions are ranked before any status filter |
| 371 claims with a visit date after as-of (up to 2099) | Inflated all-time totals | Catalogue reports the count; rule `visit_date <= as-of` |
| Amounts in SGD, MYR, IDR; Vietnamese providers bill in SGD | Summing `claim_amt` across currencies; country inferred from currency | `claim_amt_sgd` (rate is local per SGD, so divide); country comes from the provider |
| 22,388 claims with provider id 0 / 90xx, doctor id `''` / `'0'` | An inner join drops 37 % of claims | Left joins, `'Unknown'` group kept |
| 12 providers entered twice (ids 401-412, lower-cased name plus a dot) | "412 providers"; one clinic on two rows of a top 10 | Merged when name **and** type, country, region match |
| `lookup` rows repeated; `provider.type` is `1`, the code is `'001'` | Doubled counts, or no match | `lookup_clean`, numeric code key |
| 4,048 repeated claim-diagnosis pairs, 1,350 unknown ICD ids, several diagnoses per claim | Double counting, dropped claims | `claim_icd`; count distinct claims, groups overlap |

## Safety

Three layers, none of them a prompt instruction. `run_sql.py` and the agent call the same `execute_sql`.

1. **The sensitive text is never loaded.** Each call copies the eight tables from `CLAIMS_DB` (attached
   read-only) into a private in-memory database, without `diagnosis_note`, and detaches the file. So
   `SELECT *` cannot return notes and the source cannot be written. The boundary, stated plainly: the copy
   is written during setup; afterwards the guard keeps it read-only, and a bypass could only touch a
   throw-away copy.
2. **Parser guard** (sqlglot AST, fails closed): one statement, SELECT only, allow-listed relations and
   functions, no schema-qualified names, table functions or file paths, no identifier `diagnosis_note`.
   DuckDB's own parser must also classify the statement as a single SELECT.
3. **Engine settings**: external access disabled, configuration locked.

Result size and time: this build caps rows (10,000) and interrupts a statement after 20 seconds. In
production I would enforce both in the database (read-only role, statement timeout, memory limit,
governed views with column grants) and not copy data per call.

## Evaluation: what was measured, and what it does not show

44 questions: 34 with a figure, 10 where the right reply is declined / unanswerable / clarify. Expected
answers are hand-written SQL on the raw tables, in a different technique from the views (join on
`max(loaded_at)`, not `row_number`). Three questions run on a second, 6-claim database with another as-of
date. Results in the order they happened, each on first contact:

- First 17 questions: 17 of 17. Too easy, so 17 harder ones were written before running them: **33 of 34.**
- The failure: *"How many unique patients had an approved claim last month?"* was answered with the claim
  count (1,775) plus a caveat, 4 times out of 5 on repeat. The data has no patient id, so this is exactly a
  plausible wrong number. Fix: one rule ("a claim is not a person; a caveat does not turn a substitute into
  an answer"). After it: 5 of 5, and 3 of 3 on new wordings.
- 10 more unseen questions, written before that fix and run without it: 10 of 10.
- Final set of 44: **44 of 44**, on four consecutive full runs (`eval_summary.json` is the last of them).

**This number is an upper bound.** I wrote both the questions and the semantic layer. The expected SQL
shares my reading of the open points below; where the data owner reads them differently the agent will be
consistently wrong, and this evaluation cannot show it.

## What I would ask the data owner, and what I assumed

- **Versions loaded after the as-of date** (624 rows dated 1 and 2 December): assumed the latest version
  wins; they look like ordinary edits. Ignoring them changes Q1 from 1,775 to 1,766.
- **Duplicate providers**: assumed one provider entered twice. Doctors with equal names have different
  specialties and are not merged.
- **"Rejected"**: `rejected_on` set on the latest version, window on `visit_date`; 4,280 claims are both
  rejected and approved.
- **A named currency** ("in MYR"): assumed the claims billed in that currency, in local amount.
- **Diagnosis** = one ICD code. **Unknown in a top N**: left out of the ranking, reported separately.

## With another week

- Questions and paraphrases written by someone else, each run several times.
- A realistic second database with other traps (versions sharing a timestamp, FX rates that move).
- Reject an answer whose text quotes a number that is not in its tables.
- Make each open assumption a switch, so the data owner's answer becomes a configuration change.

---

## Models and AI usage

**Model that powers the agent:** OpenAI `gpt-6-luna`, the small low-cost tier, with reasoning effort `low`.
Chosen because the brief says a cheap model should be enough and the semantic layer is meant to carry the
hard parts. A full 44-question run uses about 0.5 million input and 10 thousand output tokens (roughly
USD 0.05 at list price) and takes 5 to 10 seconds per question.

**How it is used:** one tool-calling loop over the OpenAI Responses API (stateless, `store: false`; the
model's reasoning items are replayed between steps). The Responses API is used because, for this model,
chat completions allows function tools only with reasoning switched off. Default sampling settings, at most
14 steps and 100 seconds per question. The client also speaks plain chat completions (`LLM_API_STYLE=chat`)
so a local open-weight model can be substituted; that path was spot-checked on three questions with
reasoning off (3 of 3). The system prompt is the protocol, the date windows for the given as-of date, and
`business_rules.md`. No few-shot examples of the public questions, no cached answers. No model is used as a
judge: the evaluation compares the agent's tables with the results of hand-written SQL in code.

**AI coding assistants:** ChatGPT / Codex were used to read the brief and for the first read-only
exploration of the CSV files. Claude Code was used to re-profile the data, write the code, the tests, the
evaluation questions with their expected SQL, and the first draft of this note. I reviewed the business
rules, the SQL and the assumptions, and I can explain each of them.
