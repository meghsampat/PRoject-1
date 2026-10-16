"""Read source data without silently removing records."""
from pathlib import Path
import numpy as np
import pandas as pd
from src.config import PRODUCT_COLUMNS, PRODUCT_LOOKUP_FILE, REQUIRED_COLUMNS, TRANSACTION_FILE


def load_raw_transactions_for_validation(path=TRANSACTION_FILE):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Transaction file not found: {path}")
    data = pd.read_csv(path, usecols=REQUIRED_COLUMNS)
    if data.empty:
        raise ValueError("Transaction file is empty.")
    if data[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("Required columns contain missing values; resolve them before calculating results.")
    for column in REQUIRED_COLUMNS:
        if not pd.api.types.is_numeric_dtype(data[column]):
            raise ValueError(f"{column} must contain numeric values.")
        if not np.isfinite(data[column].to_numpy()).all():
            raise ValueError(f"{column} contains non-finite values.")
    for column in ["WEEK_NO", "DAY", "household_key", "BASKET_ID", "PRODUCT_ID"]:
        if (data[column] % 1 != 0).any():
            raise ValueError(f"{column} must contain whole numbers.")
    return data


def load_products(path=PRODUCT_LOOKUP_FILE):
    data = pd.read_parquet(path, columns=PRODUCT_COLUMNS)
    if data.empty or data[PRODUCT_COLUMNS].isna().any().any():
        raise ValueError("Product lookup is empty or has missing required values.")
    if data.PRODUCT_ID.duplicated().any():
        raise ValueError("Product lookup has duplicate PRODUCT_ID values; a join would duplicate sales.")
    if not pd.api.types.is_numeric_dtype(data.PRODUCT_ID) or not np.isfinite(data.PRODUCT_ID).all() or (data.PRODUCT_ID % 1 != 0).any():
        raise ValueError("Product lookup IDs must be finite integers.")
    return data


def load_processed_master(require_scope=True):
    """Read the validated processed master. New analyses must use this, not raw CSVs."""
    import json
    from src import config
    from src.artifact_io import file_fingerprint
    from src.scope import policy_fingerprint, require_final_scope
    if not config.MASTER_FILE.is_file():
        raise FileNotFoundError("Processed master missing. Run python src/build_master.py and python src/validate_master.py.")
    validation_file = config.OUTPUTS_DIR / "master_validation.json"
    if not validation_file.is_file():
        raise ValueError("Master validation missing. Run python src/validate_master.py.")
    validation = json.loads(validation_file.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("master_sha256") != file_fingerprint(config.MASTER_FILE)["sha256"]:
        raise ValueError("Processed master changed or failed validation; rebuild and validate.")
    if validation.get("policy_fingerprint") != policy_fingerprint():
        raise ValueError("Preparation/scope configuration changed; rebuild and validate before analysis.")
    data = pd.read_parquet(config.MASTER_FILE)
    if require_scope:
        require_final_scope(data)
    return data


def load_analysis_transactions():
    """Return only in-scope week-19-window transactions from validated processed data."""
    from src import config
    master = load_processed_master(require_scope=True)
    return master.loc[master.IN_SCOPE & config.in_analysis_window(master)].copy()



def load_validated_aggregate(name):
    """Load an aggregate only when its source snapshot, policy and content are validated."""
    import json
    from src import config
    from src.artifact_io import file_fingerprint
    from src.scope import policy_fingerprint
    if name not in {"commodity_daily", "commodity_weekly", "household_summary"}:
        raise ValueError("Unknown aggregate table.")
    build = json.loads((config.OUTPUTS_DIR / "aggregate_build_report.json").read_text(encoding="utf-8"))
    validation = json.loads((config.OUTPUTS_DIR / "aggregate_validation.json").read_text(encoding="utf-8"))
    master_hash = file_fingerprint(config.MASTER_FILE)["sha256"]
    if validation.get("status") != "PASS" or any(report.get("master_sha256") != master_hash or report.get("policy_fingerprint") != policy_fingerprint() for report in [build, validation]):
        raise ValueError("Aggregate source or policy changed; rebuild and validate aggregates.")
    path = config.PROCESSED_DIR / f"{name}.parquet"
    expected = next((item for item in build["artifacts"] if item["name"] == path.name), None)
    if expected != file_fingerprint(path):
        raise ValueError("Aggregate content changed after validation.")
    return pd.read_parquet(path)
