"""Load only validated, current local segmentation artifacts and models."""
import json
from pathlib import Path
import pickle
import math
import pandas as pd
import sklearn
from src import config
from src.artifact_io import file_fingerprint
from src.scope import policy_fingerprint
from src.segmentation import settings_fingerprint


def artifact_path(name):
    locations = {f"{table}.parquet": config.PROCESSED_DIR for table in config.SEGMENT_TABLE_NAMES}
    locations.update({filename: config.OUTPUTS_DIR for filename in config.SEGMENT_OUTPUT_NAMES})
    locations.update({filename: config.MODELS_DIR for filename in config.SEGMENT_MODEL_NAMES})
    if name not in locations or Path(name).name != name:
        raise ValueError("Unknown segmentation artifact name.")
    return locations[name] / name


def load_segmentation_report(require_validation=True):
    report = json.loads(config.SEGMENT_BUILD_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint") != policy_fingerprint() or report.get("settings_fingerprint") != settings_fingerprint():
        raise ValueError("Segmentation policy or settings changed; rebuild and validate saved models.")
    if report.get("master_sha256") != file_fingerprint(config.MASTER_FILE)["sha256"] or report.get("household_summary_sha256") != file_fingerprint(config.PROCESSED_DIR / "household_summary.parquet")["sha256"]:
        raise ValueError("Segmentation source snapshot changed; rebuild and validate models.")
    if report.get("demographic_lookup_sha256") != file_fingerprint(config.PROCESSED_DIR / "household_demographics.parquet")["sha256"]:
        raise ValueError("Demographic source snapshot changed; rebuild profiles and validate.")
    if report.get("sklearn_version") != sklearn.__version__:
        raise ValueError("scikit-learn version changed; retrain saved models in the current environment.")
    expected_names = {f"{table}.parquet" for table in config.SEGMENT_TABLE_NAMES} | set(config.SEGMENT_MODEL_NAMES) | set(config.SEGMENT_OUTPUT_NAMES)
    if {item["name"] for item in report["artifacts"]} != expected_names or len(report["artifacts"]) != len(expected_names):
        raise ValueError("Segmentation artifact inventory is incomplete or duplicated.")
    for expected in report["artifacts"]:
        if expected != file_fingerprint(artifact_path(expected["name"])):
            raise ValueError(f"Segmentation artifact changed: {expected['name']}; rebuild and validate.")
    if require_validation:
        validation = json.loads(config.SEGMENT_VALIDATION_FILE.read_text(encoding="utf-8"))
        if validation.get("status") != "PASS" or validation.get("build_report_sha256") != file_fingerprint(config.SEGMENT_BUILD_FILE)["sha256"]:
            raise ValueError("Saved segmentation has not passed current independent validation.")
    return report


def load_segment_models(require_validation=True):
    report = load_segmentation_report(require_validation)
    # Fingerprints and exact artifact names are checked before loading local model pickles.
    scaler = pickle.loads((config.MODELS_DIR / "scaler.pkl").read_bytes())
    model = pickle.loads((config.MODELS_DIR / "kmeans_model.pkl").read_bytes())
    return scaler, model, report


def json_records(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def saved_segment_result(scoped, start_week, end_week):
    report = load_segmentation_report()
    if start_week != report["start_week"] or end_week != report["end_week"]:
        return None
    if len(scoped) != report["transaction_lines"] or scoped.household_key.nunique() != report["households"] or not math.isclose(float(scoped.SALES_VALUE.sum()), report["revenue"], abs_tol=config.REVENUE_TOLERANCE_USD, rel_tol=0):
        raise ValueError("Requested transactions do not match the saved model's training scope.")
    profiles = pd.read_parquet(config.SEGMENT_PROFILES_FILE)
    evaluation = pd.read_csv(config.OUTPUTS_DIR / "clustering_evaluation.csv")
    return {
        "mode": "saved_model", "currency": config.CURRENCY, "source_table": config.SEGMENT_MODEL_SOURCE,
        "scope": f"IN_SCOPE=True; saved RFM model and profiles for weeks {start_week} through {end_week}, inclusive",
        "start_week": start_week, "end_week": end_week,
        "revenue_definition": "Sum of SALES_VALUE; no additional discount adjustment",
        "result_status": "Saved real-data segmentation passed independent technical validation; business usefulness review pending",
        "rows": json_records(profiles), "evaluation": json_records(evaluation),
        "chosen_k": report["chosen_k"], "silhouette": report["silhouette"],
        "stability_mean_ari": report["stability_mean_ari"],
        "households": report["households"], "revenue": report["revenue"], "reference_day": report["reference_day"],
        "models": list(config.SEGMENT_MODEL_NAMES), "model_validation_passed": True,
        "method": report["selection"] + "; saved scaler and K-Means; log1p RFM; seed 42",
        "note": "Practical divisions of a customer continuum. Initialization stability was measured; temporal/sample stability was not. Business names/actions describe measured medians and remain provisional. Demographics cover a subset and are not model inputs. Customer rates use observed participation rather than verified tenure.",
    }

