"""Offline tests: no model, no network. Run with:  python -m unittest discover -s tests -v

They build a tiny database whose answers can be worked out by hand, and check
  1. the semantic layer (latest version before status, SGD conversion, Unknown, de-duplication),
  2. the SQL guard (what is refused), through the same execute_sql the agent uses,
  3. the tool loop plumbing with a scripted stand-in for the model (this is NOT an evaluation of the agent).
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp()
DB = os.path.join(TMP, "fixture.duckdb")
TRACE = os.path.join(TMP, "trace.jsonl")
FIXTURE_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture.sql")


def setUpModule():
    con = duckdb.connect(DB)
    con.execute(open(FIXTURE_SQL).read())
    con.close()
    os.environ["CLAIMS_DB"] = DB
    os.environ["TRACE_FILE"] = TRACE


def rows(sql):
    import sql_tool
    return sql_tool.execute_sql(sql)["rows"]


class SemanticLayer(unittest.TestCase):
    def test_one_row_per_claim(self):
        self.assertEqual(rows("SELECT count(*), count(DISTINCT claim_id) FROM claim_latest"), [[6, 6]])
        self.assertEqual(rows("SELECT count(*) FROM claim"), [[8]])       # raw table keeps the raw grain

    def test_version_is_chosen_before_status(self):
        # claim 1 was approved in an old version and voided in the latest one; claim 3 the other way round.
        self.assertEqual(rows("SELECT claim_id, is_approved, claim_amt FROM claim_latest "
                              "WHERE claim_id IN (1, 3) ORDER BY 1"), [[1, False, 100.0], [3, True, 80.0]])

    def test_approved_ignores_rejected(self):
        self.assertEqual(rows("SELECT is_approved, is_rejected FROM claim_latest WHERE claim_id = 5"), [[True, True]])

    def test_default_measure_by_hand(self):
        # approved, latest, not in the future as of 2026-03-15: claims 2, 3, 5, 6 -> 100 + 80 + 10 (+ NULL) SGD
        self.assertEqual(rows("SELECT count(*), round(sum(claim_amt_sgd), 2), count(claim_amt_sgd) FROM claim_latest "
                              "WHERE is_approved AND visit_date <= DATE '2026-03-15'"), [[4, 190.0, 3]])

    def test_fx_direction_and_bad_rate(self):
        self.assertEqual(rows("SELECT claim_id, round(claim_amt_sgd, 2) FROM claim_latest "
                              "WHERE claim_id IN (2, 5, 6) ORDER BY 1"), [[2, 100.0], [5, 10.0], [6, None]])

    def test_unknown_groups_reconcile(self):
        got = rows("SELECT country_code, count(*) FROM claim_latest WHERE is_approved "
                   "AND visit_date <= DATE '2026-03-15' GROUP BY 1 ORDER BY 1")
        self.assertEqual(got, [["MY", 2], ["SG", 1], ["Unknown", 1]])
        self.assertEqual(rows("SELECT specialty, count(*) FROM claim_latest GROUP BY 1 ORDER BY 1"),
                         [["General Practice", 4], ["Unknown", 2]])

    def test_lookup_duplicates_do_not_fan_out(self):
        self.assertEqual(rows("SELECT provider_id, provider_type, source_rows FROM provider_dim ORDER BY 1"),
                         [[1, "GP", 2], [2, "Specialist", 1], [4, "GP", 1]])

    def test_duplicate_providers_are_merged(self):
        # claim 5 is booked on provider 3, which is provider 1 entered twice -> reported under provider 1.
        self.assertEqual(rows("SELECT provider_id, provider_id_raw, provider_name, country_code FROM claim_latest "
                              "WHERE claim_id = 5"), [[1, 3, "A Clinic", "SG"]])

    def test_doctor_typed_twice_is_merged_but_namesakes_are_not(self):
        self.assertEqual(rows("SELECT doctor_id, doctor_name, source_rows FROM doctor_dim ORDER BY 1"),
                         [[1, "Dr X", 2], [3, "Dr Y", 1], [4, "Dr Y", 1]])
        # claim 6 is booked on doctor 2 (the re-typed row) -> reported under doctor 1; claim 3 has no doctor
        self.assertEqual(rows("SELECT claim_id, doctor_id, doctor_id_raw, doctor_name FROM claim_latest "
                              "WHERE claim_id IN (3, 6) ORDER BY 1"),
                         [[3, None, "0", "Unknown"], [6, 1, "2", "Dr X"]])

    def test_unknown_provider_is_one_group(self):
        self.assertEqual(rows("SELECT provider_id, provider_name FROM claim_latest WHERE claim_id = 3"),
                         [[None, "Unknown"]])

    def test_diagnoses_deduplicated_and_unknown(self):
        self.assertEqual(rows("SELECT claim_id, icd_id, diagnosis FROM claim_icd ORDER BY 1, 2"),
                         [[2, 1, "Flu"], [2, 2, "Cough"], [3, 9001, "Unknown"], [3, 9002, "Unknown"], [5, 1, "Flu"]])
        # claims per diagnosis: the two unknown codes of claim 3 still count as ONE claim under 'Unknown'
        self.assertEqual(rows("SELECT diagnosis, count(DISTINCT claim_id) FROM claim_icd GROUP BY 1 ORDER BY 1"),
                         [["Cough", 1], ["Flu", 2], ["Unknown", 1]])


class Guard(unittest.TestCase):
    REFUSED = [
        "DELETE FROM drug", "UPDATE claim SET claim_amt = 0", "INSERT INTO drug VALUES (9,'x','001')",
        "DROP TABLE claim", "CREATE TABLE x AS SELECT 1", "SELECT 1; SELECT 2", "SELECT 1 INTO x",
        "SELECT diagnosis_note FROM claim_diagnosis", "SELECT cd.DIAGNOSIS_NOTE FROM claim_diagnosis cd",
        'SELECT "diagnosis_note" FROM claim_diagnosis', "SELECT max(diagnosis_note) FROM claim_diagnosis",
        "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM '/etc/passwd'", "SELECT * FROM glob('*')",
        "SELECT getenv('HOME')", "SELECT * FROM duckdb_settings()", "SELECT * FROM information_schema.columns",
        "SELECT * FROM src.main.claim_diagnosis", "COPY claim TO '/tmp/x.csv'", "PRAGMA database_list",
        "SET enable_external_access = true", "ATTACH 'x.db' AS y", "DESCRIBE claim", "SUMMARIZE claim",
        "EXPLAIN SELECT 1", "CALL pragma_version()", "", "not sql at all",
    ]

    def test_refused(self):
        import sql_tool
        for sql in self.REFUSED:
            with self.subTest(sql=sql):
                with self.assertRaises(Exception):
                    sql_tool.execute_sql(sql)

    def test_invisible_characters_are_refused(self):
        # DuckDB reads these as white space, the guard's parser reads them as part of a name.
        import sql_tool
        for ch in ("\u200b", "\ufeff", "\u2060", "\u00a0", "\u3000", "\u000b"):
            with self.subTest(char=hex(ord(ch))):
                with self.assertRaises(Exception) as ctx:
                    sql_tool.execute_sql(f"SELECT view_name{ch}FROM{ch}duckdb_views")
                self.assertIn("Refused", str(ctx.exception))
        self.assertEqual(rows("SELECT 'Café' AS name"), [["Café"]])            # ordinary non-ASCII text is fine

    def test_errors_do_not_quote_data(self):
        import sql_tool
        with self.assertRaises(Exception) as ctx:
            sql_tool.execute_sql("SELECT CAST(provider_name AS INTEGER) FROM claim_latest WHERE claim_id = 2")
        self.assertNotIn("B Clinic", str(ctx.exception))
        with self.assertRaises(Exception) as ctx:                                  # schema errors stay helpful
            sql_tool.execute_sql("SELECT no_such_column FROM claim_latest")
        self.assertIn("no_such_column", str(ctx.exception))

    def test_result_size_is_bounded(self):
        import sql_tool
        res = sql_tool.execute_sql("SELECT repeat('y', 100000) AS big FROM range(5000)")
        self.assertTrue(res["truncated"])
        self.assertLess(len(json.dumps(res)), 3_000_000)
        self.assertLessEqual(max(len(r[0]) for r in res["rows"]), sql_tool.MAX_CELL_CHARS + 20)
        res = sql_tool.execute_sql("SELECT list(i) AS xs FROM range(100000) t(i)")
        self.assertTrue(res["truncated"])
        self.assertLessEqual(len(res["rows"][0][0]), sql_tool.MAX_LIST_ITEMS)

    def test_notes_never_come_back(self):
        # SELECT * on the table that holds the notes works, but the note column does not exist here.
        import sql_tool
        res = sql_tool.execute_sql("SELECT * FROM claim_diagnosis")
        self.assertEqual(res["columns"], ["claim_id", "icd_id"])
        self.assertNotIn("SECRET-NOTE", json.dumps(res))

    def test_source_file_untouched(self):
        import sql_tool
        sql_tool.execute_sql("SELECT count(*) FROM claim")
        con = duckdb.connect(DB, read_only=True)
        self.assertEqual(con.execute("SELECT count(*), count(diagnosis_note) FROM claim_diagnosis").fetchone(), (6, 6))
        con.close()

    def test_normal_queries_allowed(self):
        for sql in ["SELECT count(*) AS n FROM claim",
                    "WITH a AS (SELECT claim_id FROM claim_latest WHERE is_approved) SELECT count(*) FROM a",
                    "SELECT visit_month, round(sum(claim_amt_sgd), 2) FROM claim_latest GROUP BY 1 ORDER BY 1",
                    "SELECT strftime(visit_date, '%Y-%m'), count(*) FILTER (WHERE is_approved) FROM claim_latest GROUP BY 1",
                    "SELECT * FROM (SELECT 1 AS x UNION ALL SELECT 2) t"]:
            with self.subTest(sql=sql):
                self.assertTrue(rows(sql))


class DateWindows(unittest.TestCase):
    def test_windows(self):
        import agent
        w = agent.date_windows(dt.date(2026, 11, 30))
        self.assertEqual(w["last_month"], {"from": "2026-10-01", "to": "2026-10-31"})
        self.assertEqual(w["last_quarter"], {"from": "2026-07-01", "to": "2026-09-30"})
        self.assertEqual(w["last_12_months"], {"from": "2025-11-01", "to": "2026-10-31"})
        self.assertEqual(w["quarter_before_last"], {"from": "2026-04-01", "to": "2026-06-30"})
        self.assertEqual(w["last_2_quarters"], {"from": "2026-04-01", "to": "2026-09-30"})
        self.assertEqual(w["last_4_quarters"], {"from": "2025-10-01", "to": "2026-09-30"})
        w = agent.date_windows(dt.date(2027, 1, 15))                       # crosses a year boundary
        self.assertEqual(w["last_month"], {"from": "2026-12-01", "to": "2026-12-31"})
        self.assertEqual(w["last_quarter"], {"from": "2026-10-01", "to": "2026-12-31"})
        self.assertEqual(w["last_3_months"], {"from": "2026-10-01", "to": "2026-12-31"})
        self.assertEqual(w["last_2_quarters"], {"from": "2026-07-01", "to": "2026-12-31"})


class ModelSettings(unittest.TestCase):
    """A grader may supply nothing but an API key; every other setting must have a working default."""

    KEYS = ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL", "OPENAI_BASE_URL", "LLM_MODEL", "LLM_API_STYLE",
            "LLM_REASONING_EFFORT", "LLM_TEMPERATURE")

    def client(self, **env):
        import llm
        saved = {k: os.environ.pop(k, None) for k in self.KEYS}
        loader, llm.load_env_file = llm.load_env_file, lambda *a, **k: None       # ignore a developer's .env
        os.environ.update(env)
        try:
            return llm.ChatClient()
        finally:
            llm.load_env_file = loader
            for k in self.KEYS:
                os.environ.pop(k, None)
                if saved[k] is not None:
                    os.environ[k] = saved[k]

    def test_only_the_standard_openai_key(self):
        c = self.client(OPENAI_API_KEY="test-key")
        self.assertEqual((c.api_key, c.model, c.style, c.effort, c.base_url),
                         ("test-key", "gpt-6-luna", "responses", "medium", "https://api.openai.com/v1"))

    def test_chat_style_on_openai_switches_reasoning_off(self):
        c = self.client(LLM_API_KEY="test-key", LLM_MODEL="gpt-6-luna", LLM_API_STYLE="chat")
        self.assertEqual((c.style, c.effort), ("chat", "none"))

    def test_local_server_defaults_to_chat_without_key(self):
        c = self.client(LLM_BASE_URL="http://localhost:11434/v1", LLM_MODEL="some-local-model")
        self.assertEqual((c.style, c.effort, c.api_key), ("chat", "", ""))

    def test_missing_key_is_reported_clearly(self):
        import llm
        with self.assertRaises(llm.LLMError) as ctx:
            self.client()
        self.assertIn("API key", str(ctx.exception))


class AnswerNumbers(unittest.TestCase):
    def test_numbers_in_the_text_must_be_in_the_tables(self):
        import agent
        t = [{"columns": ["type", "n", "avg"], "rows": [["GP", 8497, 81.7], ["Specialist", 2177, 83.59]]}]
        f = agent.numbers_not_in_tables
        self.assertEqual(f("GP 81.70 (8,497 claims), Specialist 83.59; a gap of 1.89.", t), ["1.89"])
        self.assertEqual(f("GP 81.7 and Specialist 83.6 as of 2026-11-30, top 10, about 8.5k claims.", t), [])
        self.assertEqual(f("About 22.3% of 1.3 million.", [{"columns": ["a", "b"], "rows": [[0.2233, 1317371.62]]}]), [])

    def test_loop_asks_once_then_accepts_with_a_note(self):
        import agent
        sql = "SELECT count(*) AS approved_claims FROM claim_latest WHERE is_approved AND visit_date <= DATE '2026-03-15'"
        final = {"status": "answered", "answer": "There were 4 approved claims, 57 more than last year.",
                 "assumptions": ["Approved claims, latest version."], "query_ids": ["q1"]}
        out = agent.answer_question("How many approved claims?", "2026-03-15", client=Scripted([
            ("run_sql", {"sql": sql}), ("final_answer", final), ("final_answer", final)]))
        self.assertEqual(out["status"], "answered")
        self.assertIn("57", out["assumptions"][-1])                    # accepted the second time, flagged openly
        fixed = dict(final, answer="There were 4 approved claims.")
        out = agent.answer_question("How many approved claims?", "2026-03-15", client=Scripted([
            ("run_sql", {"sql": sql}), ("final_answer", final), ("final_answer", fixed)]))
        self.assertEqual(out["assumptions"], ["Approved claims, latest version."])


class Scripted:
    """Stands in for the model: replays a fixed list of tool calls. Tests the plumbing only."""

    def __init__(self, steps):
        self.steps = list(steps)

    def chat(self, messages, tools, timeout):
        name, args = self.steps.pop(0)
        return {"content": None, "tool_calls": [
            {"id": f"c{len(self.steps)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class Loop(unittest.TestCase):
    def test_tables_and_sql_come_from_executed_queries(self):
        import agent
        open(TRACE, "w").close()
        sql = "SELECT count(*) AS approved_claims FROM claim_latest WHERE is_approved AND visit_date <= DATE '2026-03-15'"
        out = agent.answer_question("How many approved claims?", "2026-03-15", client=Scripted([
            ("get_catalogue", {}),
            ("run_sql", {"sql": "SELECT diagnosis_note FROM claim_diagnosis"}),          # refused, loop continues
            ("final_answer", {"status": "answered", "answer": "4", "assumptions": ["x"], "query_ids": []}),   # rejected
            ("run_sql", {"sql": sql}),
            ("final_answer", {"status": "answered", "answer": "There were 4 approved claims.",
                              "assumptions": ["Approved claims, latest version."], "query_ids": ["q1"]}),
        ]))
        self.assertEqual(out["status"], "answered")
        self.assertEqual(out["tables"], [{"columns": ["approved_claims"], "rows": [[4]]}])
        self.assertEqual(out["sql"], [sql])
        with open(TRACE) as f:
            trace_text = f.read()
        events = [json.loads(line) for line in trace_text.splitlines()]
        self.assertEqual([e["type"] for e in events], ["tool_call", "tool_result"] * 5)
        self.assertNotIn("SECRET-NOTE", trace_text)

    def test_declined_has_no_tables(self):
        import agent
        out = agent.answer_question("Show the notes", "2026-03-15", client=Scripted([
            ("final_answer", {"status": "declined", "answer": "Diagnosis notes are sensitive.",
                              "assumptions": [], "query_ids": []})]))
        self.assertEqual((out["status"], out["tables"], out["sql"]), ("declined", [], []))


class ResponsesWireFormat(unittest.TestCase):
    """The OpenAI Responses translation, with the HTTP call replaced by canned replies (no network)."""

    def test_reasoning_items_and_tool_results_are_replayed_in_order(self):
        import agent
        import llm
        saved = {k: os.environ.get(k) for k in ("LLM_API_KEY", "LLM_MODEL", "LLM_API_STYLE", "LLM_REASONING_EFFORT",
                                                "LLM_TEMPERATURE")}
        os.environ.update(LLM_API_KEY="test-key", LLM_MODEL="test-model", LLM_API_STYLE="responses",
                          LLM_REASONING_EFFORT="low", LLM_TEMPERATURE="")
        try:
            client = llm.ChatClient()
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        sql = "SELECT count(*) AS n FROM drug"
        replies = [
            {"output": [{"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque-1"},
                        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "run_sql",
                         "arguments": json.dumps({"sql": sql})}]},
            {"output": [{"type": "reasoning", "id": "rs_2", "encrypted_content": "opaque-2"},
                        {"type": "function_call", "id": "fc_2", "call_id": "call_2", "name": "final_answer",
                         "arguments": json.dumps({"status": "answered", "answer": "There is 1 drug.",
                                                  "assumptions": ["All rows of drug count."], "query_ids": ["q1"]})}]},
        ]
        sent = []

        def fake_post(body, timeout):
            sent.append(json.loads(json.dumps(body)))
            return replies[len(sent) - 1]

        client._post = fake_post
        out = agent.answer_question("How many drugs?", "2026-03-15", client=client)
        self.assertEqual((out["status"], out["tables"], out["sql"]),
                         ("answered", [{"columns": ["n"], "rows": [[1]]}], [sql]))
        first, second = sent
        self.assertEqual(first["store"], False)
        self.assertEqual(first["reasoning"], {"effort": "low"})
        self.assertNotIn("temperature", first)
        self.assertIn("business rules", first["instructions"].lower())
        self.assertEqual(first["input"], [{"role": "user", "content": "How many drugs?"}])
        self.assertEqual({t["name"] for t in first["tools"]}, {"get_catalogue", "run_sql", "final_answer"})
        self.assertTrue(all("function" not in t for t in first["tools"]))           # flat tool definitions
        # second request: user, then the model's own items unchanged (reasoning first), then the tool result
        self.assertEqual([i.get("type", i.get("role")) for i in second["input"]],
                         ["user", "reasoning", "function_call", "function_call_output"])
        self.assertEqual(second["input"][1]["encrypted_content"], "opaque-1")
        self.assertEqual(second["input"][3]["call_id"], "call_1")
        self.assertEqual(json.loads(second["input"][3]["output"])["rows"], [[1]])


if __name__ == "__main__":
    unittest.main()
