"""Independently check Review III values, PPT package integrity and original-file preservation."""
from pathlib import Path
import json
import math
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_analysis_transactions
from src.scope import policy_fingerprint
from src.segment_access import load_segmentation_report
from src.category_access import load_category_report
from src.forecast_access import load_forecast_report
from src.recommendation_access import load_recommendation_report
from src.review3_presentation import NS, BLANK, inspect_slide
from src.review3_slide_text import slide_plan
from scripts.build_review3 import source_paths, value_rows


def equal(left, right):
    assert math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-7), (left, right)


def main():
    report = json.loads(config.REVIEW3_REPORT_FILE.read_text(encoding="utf-8"))
    v = report["values"]
    source = Path(report["source_presentation"])
    assert report["policy_fingerprint"] == policy_fingerprint()
    paths = source_paths(source)
    assert set(report["sources"]) == set(paths)
    for name, path in paths.items():
        assert report["sources"][name] == file_fingerprint(path), name
    for item in report["artifacts"]:
        assert item == file_fingerprint(config.REVIEW3_OUTPUT_DIR / item["name"]), item["name"]
    segment, category = load_segmentation_report(), load_category_report()
    forecast, recommendation = load_forecast_report(), load_recommendation_report()
    data = load_analysis_transactions()
    revenue = float(data.SALES_VALUE.sum())
    households, baskets = data.household_key.nunique(), data.BASKET_ID.nunique()
    equal(v["revenue_usd"], revenue)
    assert v["analysis_rows"] == len(data) and v["households"] == households and v["baskets"] == baskets
    equal(v["average_basket_value_usd"], revenue / baskets)
    equal(v["mean_baskets_per_household"], baskets / households)
    assert v["start_week"] == data.WEEK_NO.min() and v["end_week"] == data.WEEK_NO.max()
    master = json.loads(config.MASTER_REPORT_FILE.read_text())
    assert v["retained_master_rows"] == master["retained_transaction_lines"]
    assert v["removed_joint_zero_rows"] == master["removed_zero_quantity_and_zero_sales_lines"]
    weekly = data.loc[data.IS_COMPLETE_WEEK].groupby("WEEK_NO").SALES_VALUE.sum().sort_index()
    assert v["complete_weeks"] == len(weekly)
    assert v["peak_week"] == weekly.idxmax()
    equal(v["peak_week_revenue_usd"], weekly.max())
    equal(v["weekly_mean_revenue_usd"], weekly.mean())
    split = len(weekly) // 2
    equal(v["first_half_mean_revenue_usd"], weekly.iloc[:split].sum() / split)
    equal(v["second_half_mean_revenue_usd"], weekly.iloc[split:].sum() / (len(weekly) - split))
    equal(v["second_half_mean_change_pct"], (weekly.iloc[split:].mean() / weekly.iloc[:split].mean() - 1) * 100)
    mask = data.RETAIL_DISC.lt(0) | data.COUPON_DISC.lt(0) | data.COUPON_MATCH_DISC.lt(0)
    assert v["discounted_transaction_lines"] == mask.sum()
    equal(v["discounted_line_revenue_usd"], data.loc[mask, "SALES_VALUE"].sum())
    equal(v["discounted_sales_share_pct"], data.loc[mask, "SALES_VALUE"].sum() / revenue * 100)
    departments = data.groupby("DEPARTMENT").SALES_VALUE.sum().nlargest(config.REVIEW3_TOP_DEPARTMENT_COUNT)
    assert [row["department"] for row in v["top_departments"]] == departments.index.tolist()
    equal(v["top_departments_revenue_share_pct"], departments.sum() / revenue * 100)
    for row in v["top_departments"]:
        equal(row["revenue_usd"], departments[row["department"]])
    rfm = pd.read_parquet(config.PROCESSED_DIR / "household_rfm.parquet")
    assert set(rfm.household_key) == set(data.household_key) and rfm.household_key.is_unique
    for name, row in v["rfm_rule_groups"].items():
        group = rfm.loc[rfm.rule_segment.eq(name)]
        assert row["households"] == group.household_key.nunique()
        equal(row["revenue"], group.revenue.sum())
        equal(row["mean_window_spend"], group.revenue.sum() / len(group))
        equal(row["revenue_share_pct"], group.revenue.sum() / revenue * 100)
        equal(row["household_share_pct"], len(group) / households * 100)
    assert sum(row["households"] for row in v["rfm_rule_groups"].values()) == households
    equal(sum(row["revenue"] for row in v["rfm_rule_groups"].values()), revenue)
    biggest = max(v["rfm_rule_groups"].values(), key=lambda row: row["revenue"])
    assert v["largest_rule_group"] == biggest["rule_segment"]
    equal(v["largest_rule_revenue_share_pct"], biggest["revenue_share_pct"])
    equal(v["largest_rule_household_share_pct"], biggest["household_share_pct"])
    profiles = pd.read_parquet(config.PROCESSED_DIR / "segment_profiles.parquet")
    assert v["chosen_k"] == segment["chosen_k"] == len(profiles)
    for row in v["kmeans_groups"]:
        original = profiles.loc[profiles.segment.eq(row["segment"])].iloc[0]
        assert row["households"] == original.households
        equal(row["revenue"], original.revenue)
        equal(row["mean_window_spend"], original.revenue / original.households)
    top = pd.read_parquet(config.PROCESSED_DIR / "product_scores.parquet").nsmallest(config.REVIEW3_TOP_CATEGORY_COUNT, "rank")
    assert v["top_categories"] == top[["COMMODITY_DESC", "rank", "score"]].to_dict("records")
    panel = pd.read_parquet(config.PROCESSED_DIR / "forecast_panel.parquet")
    for horizon, start in v["training_label_first_week_by_horizon"].items():
        rows = panel.loc[panel.horizon.eq(int(horizon)) & panel.target_week.le(v["evaluation_training_cutoff"]) & panel.actual_revenue.notna()]
        assert start == rows.target_week.min()
    backtest = pd.read_parquet(config.PROCESSED_DIR / "forecast_backtest.parquet")
    h1 = backtest.loc[backtest.horizon.eq(v["metric_horizon"])]
    for name, column in [("Gradient boosting", "gradient_boosting"), ("Naive", "naive")]:
        actual, predicted = h1.actual_revenue.to_numpy(), h1[column].to_numpy()
        mask = actual != 0
        equal(v["horizon_metrics"][name]["MAPE_pct"], np.mean(np.abs(actual[mask] - predicted[mask]) / np.abs(actual[mask])) * 100)
        equal(v["horizon_metrics"][name]["RMSE"], np.sqrt(np.mean((actual - predicted) ** 2)))
    assert v["four_week_metrics"] == {row["model"]: row for row in forecast["four_week_total_metrics"]}
    assert v["forecast_categories"] == forecast["forecastable_categories"]
    assert report["value_rows"] == value_rows(v, segment)
    pd.testing.assert_frame_equal(pd.read_csv(config.REVIEW3_OUTPUT_DIR / "blank_values.csv"), pd.DataFrame(report["value_rows"]), check_dtype=False)
    plan = slide_plan(v, segment, category, recommendation)
    assert report["expected_slide_text"] == {str(number): text for number, text in plan.items()}
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(config.REVIEW3_FILLED_FILE) as filled:
        assert filled.testzip() is None and original.namelist() == filled.namelist()
        slides = [name for name in filled.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
        assert len(slides) == report["slide_count"] == 19
        for name in filled.namelist():
            match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
            if match and int(match.group(1)) in plan:
                number = int(match.group(1))
                xml = filled.read(name).decode("utf-8")
                root = ET.fromstring(xml)
                _, body, title = inspect_slide(xml)
                assert body["paragraphs"] == plan[number]["paragraphs"]
                assert title["paragraphs"][0] == plan[number]["title"]
                all_text = " ".join(node.text or "" for node in root.findall(".//a:t", NS))
                assert not BLANK.search(all_text), number
                assert len(root.findall(".//p:sp", NS)) == len(ET.fromstring(original.read(name)).findall(".//p:sp", NS))
            else:
                assert original.read(name) == filled.read(name), name
    assert report["original_preserved"] and not report["assumed_numeric_performance_results"]
    assert any(item["status"] == "Illustrative assumption only" for item in report["feature_gaps"])
    assert any(row["status"] == "Not implemented" for row in report["value_rows"])
    validation = {"status": "PASS", "report_sha256": file_fingerprint(config.REVIEW3_REPORT_FILE)["sha256"],
        "filled_pptx_sha256": file_fingerprint(config.REVIEW3_FILLED_FILE)["sha256"],
        "original_pptx_sha256": file_fingerprint(source)["sha256"], "original_preserved": True,
        "slide_count": 19, "blank_slots_resolved": report["original_blank_count"],
        "checks": ["Actual processed-window counts, department revenue, discounts and complete-week trend independently reconcile",
                   "Four RFM rule groups and two K-Means profiles are separately verified",
                   "Matched H1 MAPE/RMSE recomputed from held-out predictions; longer-horizon metrics stay separately labelled",
                   "CSV values and revised slide wording match checked numbers and explicit assumption statuses",
                   "PPTX parses/CRC passes; all original resources/unmodified slides remain byte-identical",
                   "No original blank slots remain; unimplemented ARIMA/interval/campaign metrics are not invented"],
        "powerpoint_rendering_verified": False, "human_usefulness_review_complete": False}
    write_json(config.REVIEW3_VALIDATION_FILE, validation)
    print(f"PASS: {report['original_blank_count']} blanks resolved; original preserved; numeric and PPT package checks passed.", flush=True)


if __name__ == "__main__":
    main()
