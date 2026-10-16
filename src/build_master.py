"""Build the master and review audits. Run: python src/build_master.py."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.preprocessing import prepare_master
from src.scope import current_scope_policy, policy_fingerprint


def save_parquet(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    data.to_parquet(temporary, index=False, compression=config.PARQUET_COMPRESSION)
    temporary.replace(path)


def main():
    raw = pd.read_csv(config.TRANSACTION_FILE)
    products = pd.read_csv(config.PRODUCT_FILE)
    demographics = pd.read_csv(config.DEMOGRAPHIC_FILE)
    if demographics.household_key.isna().any() or demographics.household_key.duplicated().any():
        raise ValueError("Demographic household keys must be nonmissing and unique.")
    policy = current_scope_policy()
    master, removed, report = prepare_master(raw, products, policy)
    report["demographic_households"] = int(demographics.household_key.nunique())
    covered = master.household_key.drop_duplicates().isin(demographics.household_key)
    report["retained_households_with_demographics"] = int(covered.sum())
    report["demographic_household_coverage_pct"] = float(covered.mean() * 100)
    report["demographic_note"] = "Demographics are not joined to transactions; missing coverage does not remove households or sales."
    report["policy_fingerprint"] = policy_fingerprint(policy)
    report["sources"] = [file_fingerprint(path) for path in [config.TRANSACTION_FILE, config.PRODUCT_FILE, config.DEMOGRAPHIC_FILE]]
    save_parquet(master, config.MASTER_FILE)
    save_parquet(removed, config.PROCESSED_DIR / "removed_zero_zero_lines.parquet")
    save_parquet(products, config.PRODUCT_LOOKUP_FILE)
    save_parquet(demographics, config.PROCESSED_DIR / "household_demographics.parquet")
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    departments = master.groupby("DEPARTMENT", observed=True).agg(transaction_lines=("SOURCE_ROW_ID", "size"), unscoped_sales_value_usd=("SALES_VALUE", "sum"), households=("household_key", "nunique"), commodities=("COMMODITY_DESC", "nunique")).reset_index()
    departments.to_csv(config.OUTPUTS_DIR / "department_scope_audit.csv", index=False)
    commodities = master.groupby(["DEPARTMENT", "COMMODITY_DESC"], observed=True).agg(transaction_lines=("SOURCE_ROW_ID", "size"), unscoped_sales_value_usd=("SALES_VALUE", "sum"), households=("household_key", "nunique")).reset_index()
    commodities.to_csv(config.OUTPUTS_DIR / "commodity_scope_audit.csv", index=False)
    commodities.loc[commodities.DEPARTMENT.astype("string").str.strip().eq("DRUG GM")].to_csv(config.OUTPUTS_DIR / "drug_gm_scope_audit.csv", index=False)
    first_weeks = master.groupby("household_key").WEEK_NO.min()
    ramp = first_weeks.value_counts().sort_index().reindex(range(int(master.WEEK_NO.min()), int(master.WEEK_NO.max()) + 1), fill_value=0).rename_axis("week").reset_index(name="first_observed_households")
    ramp["cumulative_observed_households"] = ramp.first_observed_households.cumsum()
    ramp["cumulative_pct"] = ramp.cumulative_observed_households / len(first_weeks) * 100
    ramp.to_csv(config.OUTPUTS_DIR / "household_join_ramp_unscoped.csv", index=False)
    report["artifacts"] = [file_fingerprint(config.MASTER_FILE), file_fingerprint(config.PROCESSED_DIR / "removed_zero_zero_lines.parquet"), file_fingerprint(config.PRODUCT_LOOKUP_FILE), file_fingerprint(config.PROCESSED_DIR / "household_demographics.parquet")]
    write_json(config.MASTER_REPORT_FILE, report)
    print(f"Master built: {len(master):,} retained lines; {len(removed):,} zero/zero lines saved separately.", flush=True)
    print(f"Status: {report['status']}; calendar week mismatches: {report['calendar_week_line_mismatches']}", flush=True)
    for reason in report["scope_pending"]:
        print(f"PENDING: {reason}", flush=True)
    print("Run python src/validate_master.py next. No final FMCG metrics were produced.", flush=True)


if __name__ == "__main__":
    main()
