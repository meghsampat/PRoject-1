"""Start the local dashboard from VS Code; no browser or cloud process is launched."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config
from src.scope import policy_fingerprint


def streamlit_argv():
    if not config.LOCAL_ONLY_MODE or config.LOCAL_SERVER_HOST != "127.0.0.1":
        raise ValueError("This launcher requires local-only mode and the loopback address.")
    return ["streamlit", "run", str(config.PROJECT_ROOT / "app.py"),
            "--server.address", config.LOCAL_SERVER_HOST,
            "--server.port", str(config.LOCAL_SERVER_PORT),
            "--server.headless", "true", "--browser.gatherUsageStats", "false"]


def check_setup():
    required = ("streamlit", "pandas", "numpy", "plotly", "sklearn", "pyarrow")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    paths = [config.PROJECT_ROOT / "app.py", config.MASTER_FILE, config.PRODUCT_LOOKUP_FILE,
             config.OUTPUTS_DIR / "master_validation.json", config.OUTPUTS_DIR / "aggregate_validation.json"]
    missing += [path.name for path in paths if not path.is_file()]
    if missing:
        raise ValueError("Missing local dependencies/artifacts: " + ", ".join(missing))
    validation = json.loads((config.OUTPUTS_DIR / "master_validation.json").read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("policy_fingerprint") != policy_fingerprint():
        raise ValueError("The current local master must pass scope validation before launch.")
    return {"status": "PASS", "local_only": config.LOCAL_ONLY_MODE,
            "cloud_required": False, "deployment_required": False,
            "interpreter": sys.executable,
            "url": f"http://{config.LOCAL_SERVER_HOST}:{config.LOCAL_SERVER_PORT}",
            "argv": streamlit_argv()}


def main():
    parser = argparse.ArgumentParser(description="Run the FMCG dashboard locally in VS Code.")
    parser.add_argument("--check", action="store_true", help="Check local setup without starting a server.")
    args = parser.parse_args()
    try:
        checked = check_setup()
    except (OSError, ValueError) as error:
        print(f"Local setup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    if args.check:
        print(json.dumps(checked, indent=2))
        return
    print("FMCG_STARTING local dashboard; cloud and deployment disabled", flush=True)
    # VS Code opens the printed URL with its integrated browser; Streamlit stays headless.
    sys.argv = checked["argv"]
    from streamlit.web import cli
    cli.main()


if __name__ == "__main__":
    main()
