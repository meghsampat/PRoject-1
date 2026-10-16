"""Validate processed-data flows or the explicit pending-scope UI gate."""
from pathlib import Path
import ast
import hashlib
import json
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamlit.testing.v1 import AppTest
from src import config
from src.config import DEMO_QUESTIONS
from src.data_access import load_analysis_transactions, load_processed_master, load_products
from src.judge import validate_answer
from src.scope import ScopeNotConfiguredError
from src.supervisor import route_question, run_specialist


def scope_button(app):
    return next(button for button in app.button if button.label == "Generate scope configuration")


def main():
    master = load_processed_master(require_scope=False)
    app_path = str(config.PROJECT_ROOT / "app.py")
    try:
        data = load_analysis_transactions()
    except ScopeNotConfiguredError:
        app = AppTest.from_file(app_path, default_timeout=120).run()
        assert not app.exception and not app.error
        assert len(app.metric) == 0 and len(app.success) == 0
        assert any("scope definitions" in warning.value.lower() for warning in app.warning)
        assert len(app.get("download_button")) >= 3
        assert len(app.multiselect) == 3 and scope_button(app).disabled
        original_config_hash = hashlib.sha256(Path(config.__file__).read_bytes()).hexdigest()
        app.multiselect[0].select("AUTOMOTIVE")
        app.multiselect[1].select("FLUID MILK PRODUCTS")
        app.multiselect[2].select("APPAREL")
        app.selectbox[0].select("Exclude").run()
        assert not app.exception and scope_button(app).disabled
        app.checkbox[0].check().run()
        assert not scope_button(app).disabled
        scope_button(app).click().run()
        assert not app.exception and not app.error
        draft = app.session_state["scope_draft"]["proposal"]
        assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(draft["configuration_block"]).body}
        assert assignments["EXCLUDED_DEPARTMENTS"] == ["AUTOMOTIVE"]
        assert assignments["EXCLUDED_COMMODITIES"] == ["FLUID MILK PRODUCTS"]
        assert assignments["DRUG_GM_REVIEW_COMMODITIES"] == ["APPAREL"]
        assert assignments["DRUG_GM_POLICY"] == "exclude"
        assert config.EXCLUDED_DEPARTMENTS is None and config.DRUG_GM_POLICY is None
        assert hashlib.sha256(Path(config.__file__).read_bytes()).hexdigest() == original_config_hash
        assert len(app.metric) == 0 and len(app.success) == 0
        app.multiselect[1].set_value([]).run()
        assert not app.exception and not app.error
        assert "scope_draft" not in app.session_state
        assert scope_button(app).disabled and not app.checkbox[0].value
        proposal_path = config.PROPOSED_SCOPE_DIR / "scope_proposal.json"
        if proposal_path.is_file():
            tested = json.loads(proposal_path.read_text(encoding="utf-8"))
            next(button for button in app.button if button.label == "Load tested proposal for review").click().run()
            assert not app.exception and not app.error
            assert app.multiselect[0].value == tested["policy"]["excluded_departments"]
            assert app.multiselect[1].value == tested["policy"]["excluded_commodities"]
            assert app.multiselect[2].value == tested["policy"]["drug_gm_review_commodities"]
            assert scope_button(app).disabled and not app.checkbox[0].value
            app.checkbox[0].check().run()
            scope_button(app).click().run()
            assert not app.exception and not app.error
            assert app.session_state["scope_draft"]["proposal"]["policy"] == tested["policy"]
            assert config.EXCLUDED_DEPARTMENTS is None and config.DRUG_GM_POLICY is None
            assert hashlib.sha256(Path(config.__file__).read_bytes()).hexdigest() == original_config_hash
            print("PASS: tested proposal loads exact selections, requires review and changes no active scope", flush=True)
        print("PASS: scope draft selection, review gate, literal configuration output, no file changes and stale-draft invalidation", flush=True)
        print("PASS: validated processed master is readable", flush=True)
        print("PASS: unknown IN_SCOPE blocks KPIs and agent results; UI offers three scope audit downloads", flush=True)
        print("PENDING: five processed-data analytics flows require exact scope definitions. No real scoped metrics were generated.", flush=True)
        return
    products = load_products()
    start_week, end_week = int(data.WEEK_NO.min()), int(data.WEEK_NO.max())
    reference = master.loc[master.IN_SCOPE & config.in_analysis_window(master)]
    for question in DEMO_QUESTIONS:
        decision = route_question(question)
        response = run_specialist(decision, data, products, start_week, end_week)
        judgement = validate_answer(response, decision, start_week, end_week)
        assert judgement["accepted"], judgement
        if decision["intent"] == "sales_kpis":
            evidence = response["evidence"]
            assert math.isclose(evidence["revenue"], reference.SALES_VALUE.sum(), abs_tol=config.REVENUE_TOLERANCE_USD)
            assert evidence["baskets"] == reference.BASKET_ID.nunique()
            assert evidence["households"] == reference.household_key.nunique()
        if decision["intent"] == "customer_segments" and config.SEGMENT_BUILD_FILE.is_file():
            assert response["evidence"]["mode"] == "saved_model"
            assert response["evidence"]["model_validation_passed"]
            json.dumps(response["evidence"], allow_nan=False)
        if decision["intent"] == "forecast":
            assert response["evidence"]["mode"] == "saved_direct_model"
            assert response["evidence"]["model_validation_passed"]
            from unittest.mock import patch
            with patch("src.config.FORECAST_SCALE_FLOOR", config.FORECAST_SCALE_FLOOR + 1):
                try:
                    run_specialist(decision, data, products, start_week, end_week)
                except ValueError as error:
                    assert "settings/scope" in str(error)
                else:
                    raise AssertionError("Changed forecast settings did not invalidate saved models")
            assert len(response["evidence"]["holdout"]) == 42
            assert {row["horizon"] for row in response["evidence"]["evaluation"]} == {1,2,3,4}
            json.dumps(response["evidence"], allow_nan=False)
        if decision["intent"] == "week_diagnosis":
            assert response["evidence"]["validation_passed"] and response["evidence"]["cause_verified"] is False
            json.dumps(response["evidence"], allow_nan=False)
            import copy
            altered = copy.deepcopy(response)
            altered["evidence"]["cause_verified"] = True
            assert not validate_answer(altered, decision, start_week, end_week)["accepted"]
            try:
                run_specialist(decision, data, products, start_week+1, end_week)
            except ValueError as error:
                assert "full approved window" in str(error)
            else:
                raise AssertionError("Subset request incorrectly reused full-window diagnosis")
        if decision["intent"] == "recommendations":
            assert response["evidence"]["validation_passed"]
            assert len(response["evidence"]["rows"]) == 20
            assert response["evidence"]["business_usefulness_review_complete"] is False
            assert response["evidence"]["arbitration"]["selected_candidate"] is None
            json.dumps(response["evidence"], allow_nan=False)
            try:
                run_specialist(decision, data, products, start_week+1, end_week)
            except ValueError as error:
                assert "full approved window" in str(error)
            else:
                raise AssertionError("Subset request incorrectly served full-window recommendations")
            from unittest.mock import patch
            with patch("src.config.REC_HIGH_SPEND_INDEX", config.REC_HIGH_SPEND_INDEX+1):
                try:
                    run_specialist(decision, data, products, start_week, end_week)
                except ValueError as error:
                    assert "settings/scope" in str(error)
                else:
                    raise AssertionError("Changed recommendation settings were not rejected")
        if decision["intent"] == "category_intelligence":
            assert response["evidence"]["scoring_validation_passed"]
            json.dumps(response["evidence"], allow_nan=False)
            try:
                run_specialist(decision, data, products, start_week + 1, end_week)
            except ValueError as error:
                assert "full approved window" in str(error)
            else:
                raise AssertionError("Subset query incorrectly served full-window scores")
        print(f"PASS processed-data tool + Judge: {response['tool']}", flush=True)
    app = AppTest.from_file(app_path, default_timeout=120).run()
    assert not app.exception and not app.error and len(app.metric) == 4
    for question in DEMO_QUESTIONS:
        app.selectbox[0].select(question).run()
        assert app.text_input[0].value == question
        next(button for button in app.button if button.label == "Analyse").click().run()
        assert not app.exception and not app.error, app.error
        assert len(app.success) == 1
        assert app.session_state["analysis"]["judge"]["accepted"]
        if question != DEMO_QUESTIONS[0]:
            assert len(app.get("plotly_chart")) == 2
        print(f"PASS Streamlit result, chart and transparency: {question}", flush=True)
    # Exercise natural questions through the actual chat widget and retain topic context.
    from src.chat_assistant import verify_chat_blocks
    chat_cases = [
        ("How can we improve sales?", "recommendations", "summary"),
        ("Why?", "recommendations", "explain"),
        ("What should I do next?", "recommendations", "suggestions"),
        ("Forecast milk for next month", "forecast", "summary"),
        ("What should I do next?", "forecast", "suggestions"),
        ("What are the limitations?", "forecast", "risks"),
        ("Give me a short answer", "forecast", "brief"),
        ("Explain in detail", "forecast", "detail"),
        ("Why did sales spike in week 92?", "week_diagnosis", "explain"),
    ]
    for prompt, intent, focus in chat_cases:
        before = len(app.session_state["messages"])
        app.chat_input[0].set_value(prompt).run()
        assert not app.exception and not app.error, app.exception
        messages = app.session_state["messages"]
        turn = messages[-1]["turn"]
        assert len(messages) == before + 2
        assert turn["status"] == "accepted" and turn["decision"]["intent"] == intent and turn["focus"] == focus
        assert verify_chat_blocks(turn) and "Suggested next steps" in turn["content"]
        views = turn["presentation"]
        assert views["short_answer"] and views["detailed_answer"] and views["next_steps"]
        assert any(element.value == views["export_markdown"] for element in app.get("code"))
        assert any(button.label == "Download answer" for button in app.get("download_button"))
        assert turn["mode"] == "local" and len(app.toggle) == 0
        if intent == "forecast":
            assert turn["response"]["evidence"]["category"] == "FLUID MILK PRODUCTS"
        if intent == "recommendations":
            assert any(block["id"] == "action_forecast" for block in turn["blocks"])
            assert "not campaign approval" in turn["content"]
        json.dumps(turn, allow_nan=False)
        print(f"PASS natural chat, checked suggestions and context: {prompt}", flush=True)
    # Length preference changes presentation without a new analysis or duplicated messages.
    before_mode_change = len(app.session_state["messages"])
    app.sidebar.radio[0].set_value("Detailed").run()
    assert not app.exception and len(app.session_state["messages"]) == before_mode_change
    app.sidebar.radio[0].set_value("Short + details").run()
    assert not app.exception and len(app.session_state["messages"]) == before_mode_change
    count = len(app.session_state["messages"])
    app.run()
    assert len(app.session_state["messages"]) == count, "A rerun duplicated the last submission"
    # An unknown request stays visible and cannot become a fabricated analysis.
    app.chat_input[0].set_value("Write a poem about space").run()
    assert not app.exception and not app.error
    assert app.session_state["messages"][-1]["turn"]["status"] == "message"
    assert "analysis" not in app.session_state
    app.chat_input[0].set_value("Why?").run()
    assert app.session_state["messages"][-1]["turn"]["decision"]["intent"] == "week_diagnosis"
    assert verify_chat_blocks(app.session_state["messages"][-1]["turn"])
    next(button for button in app.button if button.label == "New conversation").click().run()
    assert not app.exception and not app.session_state["messages"] and "analysis" not in app.session_state
    # Starter and follow-up buttons must submit real turns, not just fill placeholders.
    next(button for button in app.button if button.label == config.CHAT_STARTERS[0]).click().run()
    assert app.session_state["messages"][-1]["turn"]["decision"]["intent"] == "sales_kpis"
    next(button for button in app.button if button.label == "Why?").click().run()
    assert app.session_state["messages"][-1]["turn"]["focus"] == "explain"
    # Cap whole user/assistant turns and clear history on source invalidation.
    from unittest.mock import patch
    with patch("src.config.CHAT_MAX_TURNS", 2):
        for prompt in ("hi", "thanks", "What are the limitations?"):
            app.chat_input[0].set_value(prompt).run()
            assert len(app.session_state["messages"]) <= 4
    app.session_state["chat_signature"] = ("stale-source",)
    app.run()
    assert not app.exception and not app.session_state["messages"] and "analysis" not in app.session_state
    print("PASS chat no-duplicate reruns, unknown requests, starter/follow-up buttons, reset, retention cap and source invalidation", flush=True)
    from src.artifact_io import write_json
    write_json(config.OUTPUTS_DIR / "chat_validation.json", {
        "status": "PASS", "client_date": "2026-10-13",
        "processed_tool_judge_flows": len(DEMO_QUESTIONS),
        "streamlit_demo_flows": len(DEMO_QUESTIONS), "natural_chat_flows": len(chat_cases),
        "checks": ["Natural widget submission and remembered follow-up intents/categories",
                   "Every displayed block equals checked evidence-derived content",
                   "Provisional promotion labels and campaign-review guards retained",
                   "Unknown requests never fabricate analysis; previous topic remains available",
                   "Reruns do not duplicate turns; starters/follow-ups submit real turns",
                   "New conversation, bounded complete-turn retention and source/scope invalidation",
                   "Short/detail follow-ups, consistent figures/actions, length preference and copy/download content"],
        "actual_cloud_chat_verified": False, "short_and_detailed_answers_verified": True,
        "local_only": True, "cloud_required": False, "deployment_required": False,
        "note": "These flows exercised the local-only assistant on actual processed sources. No cloud or deployment is required."
    })

    app.sidebar.number_input[0].set_value(start_week + 1).run()
    assert not app.exception and not app.error and len(app.success) == 0
    app.text_input[0].set_value("Show sales KPIs for store 1")
    next(button for button in app.button if button.label == "Analyse").click().run()
    assert not app.exception and not app.error and len(app.success) == 0
    assert app.session_state["messages"][-1]["turn"]["status"] == "message"
    app.sidebar.number_input[0].set_value(end_week)
    app.sidebar.number_input[1].set_value(start_week)
    app.run()
    assert not app.exception and len(app.error) == 1 and len(app.metric) == 0
    print("PASS stale-answer invalidation, unsupported question, and invalid scope", flush=True)


if __name__ == "__main__":
    main()









