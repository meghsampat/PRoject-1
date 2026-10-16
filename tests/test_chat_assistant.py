"""Conversation behavior, checked suggestions and optional AI contracts."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src import config
from src.chat_assistant import canonical_decision, plan_question, run_chat_turn, response_blocks, select_blocks, verify_chat_blocks
from src.chat_cloud import GeminiChat, connection_status
from test_prototype import sample_transactions
from src.agents.data_science_agent import answer


class ChatTests(unittest.TestCase):
    def setUp(self):
        # Provider behavior below is an injected-stub contract, not active app access.
        self.enterContext(patch("src.config.LOCAL_ONLY_MODE", False))
        self.enterContext(patch("src.config.ANALYSIS_START_WEEK", 1))

    def context(self):
        response = answer("sales_kpis", sample_transactions(), None, 1, 3)
        return {"decision": canonical_decision("sales_kpis"), "response": response}

    def test_natural_requests_cover_all_available_analyses(self):
        cases = {
            "Please summarize our sales!": "sales_kpis",
            "Can you show me sales over time?": "sales_trend",
            "What are our best sellers?": "top_products",
            "Tell me about our customers": "customer_segments",
            "Which categories should we focus on?": "category_intelligence",
            "Why did sales spike in week 92?": "week_diagnosis",
            "How can we improve sales?": "recommendations",
            "Predict milk sales for next month": "forecast",
            "give suggestions": "recommendations",
        }
        for question, intent in cases.items():
            with self.subTest(question=question):
                self.assertEqual(plan_question(question)["decision"]["intent"], intent)

    def test_context_followups_keep_the_last_analysis_and_forecast_category(self):
        context = {"decision": canonical_decision("forecast", "milk")}
        for question, focus in [("Why?", "explain"), ("What should I do next?", "suggestions"), ("What are the limitations?", "risks")]:
            plan = plan_question(question, context)
            self.assertEqual(plan["decision"]["category"], "milk")
            self.assertEqual(plan["focus"], focus)
            self.assertTrue(plan["context_used"])

    def test_ambiguous_followup_and_greeting_do_not_fabricate_metrics(self):
        for question in ["Why?", "hi", "What can you do?", "thanks", "write a poem"]:
            self.assertEqual(plan_question(question)["kind"], "message")
        self.assertEqual(plan_question("What should I do next?")["decision"]["intent"], "recommendations")

    def test_scope_and_multiple_tasks_are_not_silently_discarded(self):
        for question in ["Show sales KPIs for milk", "How are sales doing in Mumbai", "Show sales for store 1",
                         "Best sellers this year", "Show top products and customer segments", "Explain week 95"]:
            with self.subTest(question=question):
                self.assertEqual(plan_question(question, model_planner=lambda *_: self.fail("Must not call model"))["kind"], "message")

    def test_empty_and_oversized_messages_are_rejected(self):
        for question in ["", "x" * (config.CHAT_MAX_INPUT_CHARS + 1)]:
            with self.assertRaises(ValueError):
                plan_question(question)

    def test_actual_tool_judge_and_suggestion_pipeline_on_fixture(self):
        turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: self.fail("No lookup needed"), 1, 3)
        self.assertTrue(turn["judge"]["accepted"])
        self.assertTrue(verify_chat_blocks(turn))
        self.assertIn("Suggested next steps", turn["content"])
        self.assertEqual(turn["response"]["evidence"]["revenue"], 18)
        json.dumps(turn, allow_nan=False)
        followup = run_chat_turn("Why?", sample_transactions(), lambda: None, 1, 3, turn)
        self.assertEqual(followup["focus"], "explain")
        self.assertIn("distinct baskets", followup["content"])
        self.assertTrue(verify_chat_blocks(followup))

    def test_rejected_judge_withholds_numeric_results_and_suggestions(self):
        with patch("src.chat_assistant.validate_answer", return_value={"accepted": False}):
            turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3)
        self.assertEqual(turn["status"], "rejected")
        self.assertNotIn("response", turn)
        self.assertNotIn("Suggested next steps", turn["content"])

    def test_changed_blocks_and_changed_core_claims_are_rejected(self):
        turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3)
        edited = copy.deepcopy(turn)
        edited["blocks"][0]["text"] = "Guaranteed profit of 999 dollars."
        self.assertFalse(verify_chat_blocks(edited))
        edited = copy.deepcopy(turn)
        edited["response"]["claims"]["revenue"] = 999
        self.assertFalse(verify_chat_blocks(edited))

    def test_limitations_followup_answers_the_requested_caveats_first(self):
        previous = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3)
        turn = run_chat_turn("What are the limitations?", sample_transactions(), lambda: None, 1, 3, previous)
        self.assertTrue(turn["content"].startswith("Recorded revenue does not establish"))
        self.assertTrue(verify_chat_blocks(turn))
    def test_model_enum_routes_reject_extra_fields_and_filters(self):
        good = lambda *_: {"intent": "sales_kpis", "category": None, "unsupported_scope": False}
        self.assertEqual(plan_question("Assess business performance", model_planner=good)["decision"]["intent"], "sales_kpis")
        for result in [{"intent": "delete_files", "category": None, "unsupported_scope": False},
                       {"intent": "sales_kpis", "category": "milk", "unsupported_scope": False},
                       {"intent": "sales_kpis", "category": None, "unsupported_scope": False, "sql": "SELECT *"}]:
            with self.assertRaises(ValueError):
                plan_question("Assess performance", model_planner=lambda *_: result)
        result = {"intent": "sales_kpis", "category": None, "unsupported_scope": True}
        self.assertEqual(plan_question("Assess performance", model_planner=lambda *_: result)["kind"], "message")

    def test_model_selection_cannot_insert_text_or_hide_limits(self):
        blocks = response_blocks(self.context()["response"])
        for ids in [["summary", "new fabricated claim", "limitations"], ["summary", "action_products"], ["summary", "summary", "limitations"],
                    ["summary", "limitations"], ["summary", {"text": "new text"}, "limitations"]]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                select_blocks(blocks, "summary", lambda *_: ids)
        selected = select_blocks(blocks, "summary", lambda *_: ["summary", "action_products", "limitations"])
        self.assertEqual(selected[1]["id"], "action_products")

    def test_ai_failure_falls_back_with_explicit_local_mode(self):
        class Broken:
            def plan(self, *_): raise RuntimeError("private credential text")
            def select(self, *_): raise RuntimeError("private credential text")
        turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3, model=Broken())
        self.assertTrue(verify_chat_blocks(turn))
        self.assertEqual(turn["mode"], "local")
        self.assertIn("local assistant", turn["notice"])
        self.assertNotIn("private", json.dumps(turn))

    def test_recommendation_actions_respect_promote_and_maintain_labels(self):
        response = {"tool": "get_recommendations", "answer": "Fixture only", "evidence": {
            "weights": {"forecast": config.REC_FORECAST_WEIGHTS, "segment": config.REC_SEGMENT_WEIGHTS},
            "rows": [{"candidate": "forecast", "rank": 1, "COMMODITY_DESC": "A", "priority_label": "review", "execution_status": "review_required"},
                     {"candidate": "forecast", "rank": 2, "COMMODITY_DESC": "B", "priority_label": "promote", "execution_status": "review_required"},
                     {"candidate": "segment", "rank": 1, "COMMODITY_DESC": "C", "priority_label": "maintain", "execution_status": "review_required"}]}}
        blocks = {item["id"]: item for item in response_blocks(response)}
        self.assertIn("Review B", blocks["action_forecast"]["text"])
        self.assertIn("label maintain", blocks["action_segment"]["text"])
        self.assertNotIn("Guaranteed", str(blocks))

    def test_connection_requires_matching_actual_proof_and_local_prerequisites(self):
        settings = {"project_id": "fixture-project", "location": "global", "model": "fixture-model", "deployment_region": "us-central1"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "proof.json"
            with patch("src.chat_cloud.cloud_configuration", return_value=settings), patch("src.chat_cloud.preflight", return_value={"missing": []}), patch("src.config.CLOUD_SMOKE_FILE", path):
                self.assertFalse(connection_status()["ready"])
                path.write_text(json.dumps({"status": "PASS", "cloud_call_verified": True, "configuration": settings}))
                self.assertTrue(connection_status()["ready"])
                path.write_text(json.dumps({"status": "PASS", "cloud_call_verified": True, "configuration": {**settings, "model": "other"}}))
                self.assertFalse(connection_status()["ready"])

    def test_short_and_long_requests_preserve_forecast_context(self):
        context = {"decision": canonical_decision("forecast", "milk")}
        for prompt, focus in [("short ans", "brief"), ("Give me a short answer", "brief"), ("Just give me short ans", "brief"), ("keep it short", "brief"), ("Explain in detail", "detail"), ("Give me a long answer", "detail")]:
            plan = plan_question(prompt, context)
            self.assertEqual(plan["focus"], focus)
            self.assertEqual(plan["decision"]["category"], "milk")
        self.assertEqual(plan_question("Short answer")["kind"], "message")

    def test_short_kpi_answer_has_checked_figures_and_full_actions_available(self):
        turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3)
        views = turn["presentation"]
        self.assertIn("USD 18.00", views["short_answer"])
        self.assertIn("3 baskets", views["short_answer"])
        self.assertIn("USD 6.00", views["short_answer"])
        self.assertLess(len(views["short_answer"].split()), 40)
        self.assertIn("What to do next", views["detailed_answer"])
        self.assertIn(turn["response"]["evidence"]["scope"], views["export_markdown"])
        self.assertTrue(views["next_steps"] and verify_chat_blocks(turn))

    def test_changed_short_long_actions_and_download_content_are_rejected(self):
        turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3)
        for field in ["short_answer", "detailed_answer", "caveat", "export_markdown", "next_steps"]:
            edited = copy.deepcopy(turn)
            edited["presentation"][field] = ["Guarantee ROI"] if field == "next_steps" else "Guarantee ROI"
            self.assertFalse(verify_chat_blocks(edited), field)

    def test_forecast_details_keep_losing_baselines_and_error_definition(self):
        from src.chat_presentation import answer_views
        response = {"tool": "forecast_demand", "evidence": {
            "category": "FIXTURE MILK", "forecast_total": 400.0, "forecast_horizon": 4,
            "scope": "Fixture weeks only", "revenue_definition": "Fixture SALES_VALUE",
            "four_week_evaluation": [
                {"model": "Gradient boosting", "WAPE_pct": 15.0},
                {"model": "Seasonal naive (52 weeks)", "WAPE_pct": 10.0},
                {"model": "Validation-selected forecast", "WAPE_pct": 12.0},
                {"model": "Undefined baseline", "WAPE_pct": None},
            ]}}
        blocks = [{"id": "summary", "kind": "fact", "text": "Fixture"},
                  {"id": "action_plan", "kind": "suggestion", "text": "Review stock"},
                  {"id": "limitations", "kind": "limitation", "text": "No physical-unit claim"}]
        views = answer_views(response, blocks)
        self.assertIn("USD 400.00", views["short_answer"])
        self.assertIn("| Gradient boosting | 15.00%", views["detailed_answer"])
        self.assertIn("| Seasonal naive (52 weeks) | 10.00%", views["detailed_answer"])
        self.assertIn("| Undefined baseline | Undefined", views["detailed_answer"])
        self.assertIn("error, not accuracy", views["detailed_answer"])


    def test_google_sdk_stub_receives_json_schema_explicit_credentials_and_only_blocks(self):
        calls = []
        class Fake:
            def __init__(self, **kwargs): calls.append(kwargs); self.models = self
            def generate_content(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text='{"ids":["summary","action_products","limitations"]}')
            def close(self): calls.append("closed")
        model = GeminiChat({"project_id": "fixture-project", "location": "global", "model": "fixture-model"},
            Fake, lambda **_: ("fixture-credentials", None))
        blocks = response_blocks(self.context()["response"])
        try:
            ids = model.select("what next", blocks, "summary")
            self.assertIn("limitations", ids)
            self.assertEqual(calls[0]["credentials"], "fixture-credentials")
            self.assertEqual(calls[1]["config"]["response_mime_type"], "application/json")
            self.assertNotIn("SOURCE_ROW_ID", calls[1]["contents"])
        finally:
            model.close()
        self.assertEqual(calls[-1], "closed")


if __name__ == "__main__":
    unittest.main()
