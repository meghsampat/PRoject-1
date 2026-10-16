"""Read-only UI validation with an isolated, unapproved real-data scope scenario."""
from pathlib import Path
import json
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from streamlit.testing.v1 import AppTest
from src import config
from src.artifact_io import file_fingerprint
from src.data_access import load_processed_master
from src.scope import apply_scope_policy


def main():
    original = {"config": file_fingerprint(Path(config.__file__)), "master": file_fingerprint(config.MASTER_FILE)}
    proposal = json.loads((config.PROPOSED_SCOPE_DIR / "scope_proposal.json").read_text(encoding="utf-8"))
    validation = json.loads((config.PROPOSED_SCOPE_DIR / "scenario_validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "PASS_SCENARIO_NOT_APPROVED"
    assert proposal["source_master_sha256"] == original["master"]["sha256"]
    master = load_processed_master(require_scope=False)
    products = pd.read_parquet(config.PRODUCT_LOOKUP_FILE)
    master["IN_SCOPE"], _ = apply_scope_policy(master, proposal["policy"], products)
    data = master.loc[master.IN_SCOPE & config.in_analysis_window(master)].copy()
    # This patch affects only this test process. The active app/config/files stay unchanged.
    with patch("src.data_access.load_analysis_transactions", return_value=data):
        app = AppTest.from_file(str(config.PROJECT_ROOT / "app.py"), default_timeout=120).run()
        assert not app.exception and not app.error and len(app.metric) == 4
        for question in config.DEMO_QUESTIONS:
            app.selectbox[0].select(question).run()
            app.button[0].click().run()
            assert not app.exception and not app.error
            assert len(app.success) == 1
            assert app.session_state["analysis"]["judge"]["accepted"]
            if question != config.DEMO_QUESTIONS[0]:
                assert len(app.get("plotly_chart")) == 1
            print(f"PASS isolated scenario UI result/chart/transparency: {question}", flush=True)
        current_start = app.sidebar.number_input[0].value
        app.sidebar.number_input[0].set_value(current_start + 1).run()
        assert not app.exception and not app.error and len(app.success) == 0
        app.text_input[0].set_value("Show sales KPIs for store 1")
        app.button[0].click().run()
        assert not app.exception and len(app.error) == 1 and len(app.success) == 0
    assert original["config"] == file_fingerprint(Path(config.__file__))
    assert original["master"] == file_fingerprint(config.MASTER_FILE)
    print("PASS: isolated scenario UI flows and source/scope invalidation; active configuration/master unchanged.", flush=True)


if __name__ == "__main__":
    main()
