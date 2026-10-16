"""Persist aggregate tables after source preparation and final scope checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config
from src.aggregation import build_aggregate_frames
from src.artifact_io import file_fingerprint, write_json
from src.build_master import save_parquet
from src.data_access import load_processed_master
from src.scope import ScopeNotConfiguredError, policy_fingerprint


def main():
    master = load_processed_master(require_scope=True)
    daily, weekly, households, kpis, benchmarks = build_aggregate_frames(master)
    for name, frame in [("commodity_daily", daily), ("commodity_weekly", weekly), ("household_summary", households)]:
        save_parquet(frame, config.PROCESSED_DIR / f"{name}.parquet")
    write_json(config.OUTPUTS_DIR / "kpi_summary.json", kpis)
    write_json(config.OUTPUTS_DIR / "aggregate_build_report.json", {
        "status": "BUILT_REQUIRES_VALIDATION", "policy_fingerprint": policy_fingerprint(),
        "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"],
        "benchmarks": benchmarks,
        "note": "Daily includes all in-scope days; weekly excludes partial weeks; households and KPIs use the week-19 analysis window. Compare to the correct benchmark, not one universal revenue total.",
        "artifacts": [file_fingerprint(config.PROCESSED_DIR / f"{name}.parquet") for name in ["commodity_daily", "commodity_weekly", "household_summary"]] + [file_fingerprint(config.OUTPUTS_DIR / "kpi_summary.json")],
    })
    print("Built three processed aggregate tables and outputs/kpi_summary.json. Run python src/validate_aggregates.py.")


if __name__ == "__main__":
    try:
        main()
    except ScopeNotConfiguredError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
