"""Compare every persisted aggregate with the appropriate processed-source benchmark."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_processed_master
from src.scope import policy_fingerprint


def main():
    master = load_processed_master(require_scope=True)
    scoped = master.loc[master.IN_SCOPE]
    window = scoped.loc[config.in_analysis_window(scoped)]
    daily = pd.read_parquet(config.PROCESSED_DIR / "commodity_daily.parquet")
    weekly = pd.read_parquet(config.PROCESSED_DIR / "commodity_weekly.parquet")
    households = pd.read_parquet(config.PROCESSED_DIR / "household_summary.parquet")
    kpis = json.loads((config.OUTPUTS_DIR / "kpi_summary.json").read_text(encoding="utf-8"))
    build = json.loads((config.OUTPUTS_DIR / "aggregate_build_report.json").read_text(encoding="utf-8"))
    assert build["policy_fingerprint"] == policy_fingerprint()
    assert build["master_sha256"] == file_fingerprint(config.MASTER_FILE)["sha256"]
    for expected in build["artifacts"]:
        parent = config.OUTPUTS_DIR if expected["name"].endswith(".json") else config.PROCESSED_DIR
        assert expected == file_fingerprint(parent / expected["name"])
    benchmark_pairs = [
        (daily.revenue.sum(), scoped.SALES_VALUE.sum()),
        (weekly.revenue.sum(), scoped.loc[scoped.IS_COMPLETE_WEEK, "SALES_VALUE"].sum()),
        (households.revenue.sum(), window.SALES_VALUE.sum()),
        (daily.loc[daily.in_window, "revenue"].sum(), window.SALES_VALUE.sum()),
        (weekly.loc[weekly.in_window, "revenue"].sum(), window.loc[window.IS_COMPLETE_WEEK, "SALES_VALUE"].sum()),
        (kpis["revenue"], window.SALES_VALUE.sum()),
    ]
    assert all(np.isclose(actual, expected, rtol=0, atol=config.REVENUE_TOLERANCE_USD) for actual, expected in benchmark_pairs)
    assert not daily.duplicated(["COMMODITY_DESC", "DATE"]).any()
    assert not weekly.duplicated(["COMMODITY_DESC", "WEEK_NO"]).any()
    assert not households.household_key.duplicated().any()
    expected_categories = scoped.COMMODITY_DESC.nunique()
    expected_days = (master.DATE.max() - master.DATE.min()).days + 1
    assert len(daily) == expected_categories * expected_days
    full_week_count = master.loc[master.IS_COMPLETE_WEEK, "WEEK_NO"].nunique()
    assert len(weekly) == expected_categories * full_week_count
    assert kpis["baskets"] == window.BASKET_ID.nunique()
    assert kpis["households"] == window.household_key.nunique() == len(households)
    assert np.isclose(kpis["average_basket_value"], kpis["revenue"] / kpis["baskets"])
    expected_household = window.groupby("household_key").SALES_VALUE.sum().sort_index()
    actual_household = households.set_index("household_key").revenue.sort_index()
    assert np.allclose(expected_household, actual_household)
    assert households.recency_days.ge(0).all() and households.observed_weeks.gt(0).all()
    assert np.allclose(households.baskets_per_week, households.baskets / households.observed_weeks)
    assert np.allclose(households.revenue_per_week, households.revenue / households.observed_weeks)
    assert daily.in_window.equals(config.in_analysis_window(daily))
    assert weekly.in_window.equals(config.in_analysis_window(weekly))
    shares = weekly.loc[weekly.in_window].assign(sold=lambda frame: frame.revenue.gt(0)).groupby("COMMODITY_DESC").sold.mean()
    assert np.allclose(weekly.window_week_sale_share, weekly.COMMODITY_DESC.map(shares))
    assert weekly.forecastable.equals(weekly.window_week_sale_share.ge(config.FORECASTABLE_WEEK_SHARE))
    write_json(config.OUTPUTS_DIR / "aggregate_validation.json", {"status": "PASS", "master_sha256": build["master_sha256"], "policy_fingerprint": policy_fingerprint(), "checks": ["Six revenue benchmarks reconcile", "Unique keys and complete zero-filled grids", "KPI distinct counts and basket-value arithmetic", "Household revenue and observed-period rates", "Window flags and forecastability threshold"], "note": "Validated calculations under configured scope; no Review 3 field mapping was supplied."})
    print("PASS: aggregate revenue, keys, grids, KPIs, household rates and forecastability. Saved outputs/aggregate_validation.json.")


if __name__ == "__main__":
    main()

