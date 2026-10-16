"""Independently validate the persisted master against raw sources and policy."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.scope import current_scope_policy, normalize_names, policy_fingerprint, scope_pending_reasons


def main():
    master = pd.read_parquet(config.MASTER_FILE)
    removed = pd.read_parquet(config.PROCESSED_DIR / "removed_zero_zero_lines.parquet")
    raw = pd.read_csv(config.TRANSACTION_FILE)
    products = pd.read_csv(config.PRODUCT_FILE)
    report = json.loads(config.MASTER_REPORT_FILE.read_text(encoding="utf-8"))
    policy = current_scope_policy()
    checks = []
    assert policy_fingerprint(policy) == report["policy_fingerprint"], "Policy changed; rebuild first"
    for expected in report["sources"]:
        assert file_fingerprint(config.PROJECT_ROOT / expected["name"]) == expected, "Raw source changed; rebuild first"
    for expected in report["artifacts"]:
        assert file_fingerprint(config.PROCESSED_DIR / expected["name"]) == expected, "Artifact changed after build"
    checks.append("Policy, raw-source and processed-artifact hashes match the build")
    zero_zero = raw.QUANTITY.eq(0) & raw.SALES_VALUE.eq(0)
    assert master.SOURCE_ROW_ID.is_unique and removed.SOURCE_ROW_ID.is_unique
    assert np.array_equal(master.SOURCE_ROW_ID.to_numpy(), np.flatnonzero(~zero_zero))
    assert np.array_equal(removed.SOURCE_ROW_ID.to_numpy(), np.flatnonzero(zero_zero))
    pd.testing.assert_frame_equal(master[config.RAW_TRANSACTION_COLUMNS].reset_index(drop=True), raw.loc[~zero_zero, config.RAW_TRANSACTION_COLUMNS].reset_index(drop=True), check_dtype=False)
    pd.testing.assert_frame_equal(removed[config.RAW_TRANSACTION_COLUMNS].reset_index(drop=True), raw.loc[zero_zero, config.RAW_TRANSACTION_COLUMNS].reset_index(drop=True), check_dtype=False)
    assert len(master) + len(removed) == len(raw)
    assert np.isclose(master.SALES_VALUE.sum() + removed.SALES_VALUE.sum(), raw.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    checks.append("Every raw line is either retained unchanged or documented as quantity=0 AND sales=0")
    lookup = products.set_index("PRODUCT_ID")
    for column in config.LOOKUP_COLUMNS:
        if column != "PRODUCT_ID":
            expected = master.PRODUCT_ID.map(lookup[column]).astype("string")
            assert master[column].astype("string").equals(expected), f"Lookup mismatch: {column}"
    checks.append("All product metadata matches the unique raw lookup without revenue multiplication")
    expected_dates = pd.Timestamp(config.CALENDAR_DAY_ONE) + pd.to_timedelta(master.DAY - 1, unit="D")
    assert master.DATE.equals(expected_dates)
    monday_dates = master.DATE - pd.to_timedelta(master.DATE.dt.dayofweek, unit="D")
    anchor = pd.Timestamp(config.CALENDAR_DAY_ONE)
    anchor_monday = anchor - pd.Timedelta(days=anchor.weekday())
    datetime_weeks = (monday_dates - anchor_monday).dt.days // config.DAYS_PER_WEEK + 1
    assert datetime_weeks.eq(master.WEEK_NO).all()
    assert master.IN_ANALYSIS_WINDOW.equals(config.in_analysis_window(master))
    day_counts = raw.groupby("WEEK_NO").DAY.nunique()
    assert master.IS_COMPLETE_WEEK.equals(master.WEEK_NO.map(day_counts).eq(config.DAYS_PER_WEEK))
    checks.append("Synthetic dates, Monday-derived weeks, week-19 mask, and complete-week flags reconcile")
    assert master.IS_FREE_ITEM.equals(master.QUANTITY.gt(0) & master.SALES_VALUE.eq(0))
    assert master.HAS_LOYALTY_DISC.equals(master.RETAIL_DISC.lt(0))
    assert master.HAS_COUPON.equals(master.COUPON_DISC.lt(0) | master.COUPON_MATCH_DISC.lt(0))
    assert master.ZERO_QTY_NONZERO_SALES.equals(master.QUANTITY.eq(0) & master.SALES_VALUE.ne(0))
    assert master.NEGATIVE_QUANTITY.equals(master.QUANTITY.lt(0))
    assert master.NEGATIVE_SALES.equals(master.SALES_VALUE.lt(0))
    assert master.POSITIVE_DISCOUNT_VALUE.equals(master[["RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC"]].gt(0).any(axis=1))
    if scope_pending_reasons(policy):
        assert master.IN_SCOPE.isna().all(), "Unknown scope must not become True"
        assert master.UNIT_PRICE_PAID.isna().all()
    else:
        departments = master.DEPARTMENT.astype("string").str.strip().str.upper()
        commodities = master.COMMODITY_DESC.astype("string").str.strip().str.upper()
        expected = ~departments.isin(normalize_names(policy["excluded_departments"])) & ~commodities.isin(normalize_names(policy["excluded_commodities"]))
        if policy["drug_gm_policy"] == "exclude":
            expected &= ~(departments.eq("DRUG GM") & commodities.isin(normalize_names(policy["drug_gm_review_commodities"])))
        assert master.IN_SCOPE.astype(bool).equals(expected.astype(bool))
        priceable = expected & master.QUANTITY.gt(0)
        assert master.loc[~priceable, "UNIT_PRICE_PAID"].isna().all()
        assert np.allclose(master.loc[priceable, "UNIT_PRICE_PAID"], master.loc[priceable, "SALES_VALUE"] / master.loc[priceable, "QUANTITY"])
    if policy["weighted_commodities"] is None:
        assert master.IS_WEIGHTED.isna().all()
    checks.append("Flags retain anomalies; unknown scope/weighted classification is not fabricated")
    validation = {"status": "PASS", "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"], "policy_fingerprint": policy_fingerprint(policy), "checks": checks, "scope_ready": not scope_pending_reasons(policy), "note": "Preparation correctness is validated; pending scope prevents final results."}
    write_json(config.OUTPUTS_DIR / "master_validation.json", validation)
    for check in checks:
        print(f"PASS: {check}", flush=True)
    print(f"Scope ready: {validation['scope_ready']}. Saved outputs/master_validation.json.", flush=True)


if __name__ == "__main__":
    main()

