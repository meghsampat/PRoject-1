"""The active VS Code workflow must work without cloud credentials or external calls."""
import ast
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from src import config
from src.chat_assistant import run_chat_turn, verify_chat_blocks
from src.cloud_access import perform_smoke, preflight
from src.chat_cloud import GeminiChat, connection_status
from scripts.run_local import streamlit_argv
from test_prototype import sample_transactions


class LocalWorkflowTests(unittest.TestCase):
    def test_local_mode_blocks_cloud_before_credentials_or_client_creation(self):
        factory, credentials = Mock(), Mock()
        with patch("src.config.LOCAL_ONLY_MODE", True):
            self.assertEqual(preflight({})["status"], "DISABLED_BY_USER")
            self.assertFalse(connection_status()["ready"])
            with self.assertRaisesRegex(ValueError, "disabled"):
                perform_smoke({}, factory, credentials)
            with self.assertRaisesRegex(ValueError, "disabled"):
                GeminiChat({}, factory, credentials)
        factory.assert_not_called()
        credentials.assert_not_called()

    def test_local_chat_ignores_injected_external_model_without_losing_evidence(self):
        forbidden = Mock()
        with patch("src.config.LOCAL_ONLY_MODE", True), patch("src.config.ANALYSIS_START_WEEK", 1), patch("urllib.request.urlopen", side_effect=AssertionError("No external request")):
            turn = run_chat_turn("How are sales doing?", sample_transactions(), lambda: None, 1, 3, model=forbidden)
        self.assertTrue(verify_chat_blocks(turn))
        self.assertEqual(turn["mode"], "local")
        forbidden.plan.assert_not_called()
        forbidden.select.assert_not_called()

    def test_vscode_launch_stays_inside_editor_and_uses_loopback_without_telemetry(self):
        args = streamlit_argv()
        self.assertEqual(args[args.index("--server.address") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("--server.headless") + 1], "true")
        self.assertEqual(args[args.index("--browser.gatherUsageStats") + 1], "false")
        launch = json.loads((config.PROJECT_ROOT / ".vscode/launch.json").read_text())
        server = launch["configurations"][0]
        self.assertEqual(server["console"], "integratedTerminal")
        self.assertEqual(server["serverReadyAction"]["action"], "openIntegratedBrowser")
        imports = [node.module for node in ast.walk(ast.parse((config.PROJECT_ROOT / "app.py").read_text())) if isinstance(node, ast.ImportFrom)]
        self.assertNotIn("src.chat_cloud", imports)


if __name__ == "__main__":
    unittest.main()
