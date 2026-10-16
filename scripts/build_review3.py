"""Fill the supplied Review III PPT with measured local values and labelled assumptions."""
from pathlib import Path
import argparse
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_analysis_transactions
from src.category_access import load_category_report
from src.forecast_access import load_forecast_report
from src.segment_access import load_segmentation_report
from src.recommendation_access import load_recommendation_report
from src.diagnostic_access import load_diagnostic_report
from src.scope import policy_fingerprint
from src.review3_values import calculate_values
from src.review3_slide_text import slide_plan
from src.review3_presentation import build_deck, inspect_slide, NS, BLANK


def source_paths(source):
    return {"presentation": source, "master": config.MASTER_FILE,
        "master_build": config.MASTER_REPORT_FILE, "master_validation": config.OUTPUTS_DIR / "master_validation.json",
        "aggregate_validation": config.OUTPUTS_DIR / "aggregate_validation.json",
        "rfm": config.PROCESSED_DIR / "household_rfm.parquet", "segment_profiles": config.PROCESSED_DIR / "segment_profiles.parquet",
        "scores": config.PROCESSED_DIR / "product_scores.parquet", "forecast_panel": config.PROCESSED_DIR / "forecast_panel.parquet",
        "segment_build": config.SEGMENT_BUILD_FILE, "segment_validation": config.SEGMENT_VALIDATION_FILE,
        "category_build": config.CATEGORY_BUILD_FILE, "category_validation": config.CATEGORY_VALIDATION_FILE,
        "forecast_build": config.FORECAST_BUILD_FILE, "forecast_validation": config.FORECAST_VALIDATION_FILE,
        "recommendation_build": config.REC_BUILD_FILE, "recommendation_validation": config.REC_VALIDATION_FILE,
        "diagnosis_build": config.DIAG_REPORT_FILE, "diagnosis_validation": config.DIAG_VALIDATION_FILE,
        "readiness": config.OUTPUTS_DIR / "local_readiness.json"}


def value_rows(v, segment):
    rows = []
    def add(slide, field, value, basis, status="Measured"):
        rows.append({"slide": slide, "field": field, "value_to_use": value, "status": status, "basis_or_caution": basis})
    add(6, "Clean retained master rows", f"{v['retained_master_rows']:,}", "Retained transactions_master; not a SQL fact_sales table")
    add(6, "Approved analysis rows", f"{v['analysis_rows']:,}", "IN_SCOPE=True, weeks 19-102; partial week 102 included")
    add(7, "Weekly trend", f"Peak week {v['peak_week']}: USD {v['peak_week_revenue_usd']:,.2f}; second-half mean {v['second_half_mean_change_pct']:+.2f}%", "Complete weeks 19-59 vs 60-101; descriptive, no holiday cause")
    add(7, "Top three departments", ", ".join(row["department"] for row in v["top_departments"]), "Approved-window department revenue ranking")
    add(7, "Top-three revenue share", f"{v['top_departments_revenue_share_pct']:.2f}%", "Sum of the three department revenues / approved-window revenue")
    add(7, "Average basket value", f"USD {v['average_basket_value_usd']:.2f}", "Recorded revenue / distinct baskets")
    add(7, "Mean baskets per household", f"{v['mean_baskets_per_household']:.2f}", "Distinct baskets / households across the whole selected window")
    add(7, "Discounted-sales share", f"{v['discounted_sales_share_pct']:.2f}%", v["discount_definition"])
    add(7, "Analysis/forecast history starts", str(v["start_week"]), "Configured dataset week, not a verified calendar date")
    add(8, "Selected K-Means k", str(v["chosen_k"]), "Saved StandardScaler + K-Means; not four clusters")
    add(8, "Silhouette / initialization ARI", f"{segment['silhouette']:.4f} / {segment['stability_mean_ari']:.4f}", "Initialization agreement does not establish temporal stability")
    for name in config.REVIEW3_RULE_ORDER:
        row = v["rfm_rule_groups"][name]
        add(9, name, f"{row['households']:,} households; {row['revenue_share_pct']:.2f}% revenue; USD {row['mean_window_spend']:,.2f} mean window spend", "Existing RFM rule baseline, NOT K-Means cluster counts or validated Champions/Loyal/At-Risk labels")
    add(9, "Highest-revenue rule group's household / revenue shares", f"{v['largest_rule_household_share_pct']:.2f}% / {v['largest_rule_revenue_share_pct']:.2f}%", v["largest_rule_group"])
    add(10, "History start / H1 training-label start", f"{v['first_complete_week']} / {v['training_label_first_week_by_horizon']['1']}", "History starts 19; rolling-window warm-up means H1 labels start 27")
    add(10, "Frozen training cutoff / held-out targets", f"{v['evaluation_training_cutoff']} / {v['test_start']}-{v['test_end']}", "No shuffled split; horizon-specific usable origins")
    gb, naive = v["horizon_metrics"]["Gradient boosting"], v["horizon_metrics"]["Naive"]
    add(10, "H1 boosting MAPE / naive MAPE", f"{gb['MAPE_pct']:.2f}% / {naive['MAPE_pct']:.2f}%", "201 categories, matched H1 test; zero actuals excluded. These are not ARIMA metrics")
    add(10, "H1 boosting RMSE / naive RMSE", f"USD {gb['RMSE']:.2f} / USD {naive['RMSE']:.2f}", "Matched H1 category/origin/target rows; recorded-revenue error")
    for name in ("Validation-selected forecast", "Gradient boosting", "Seasonal naive (52 weeks)", "Naive", "Four-week moving average (fixed origin)"):
        add(10, "Four-week-total WAPE: " + name, f"{v['four_week_metrics'][name]['WAPE_pct']:.2f}%", "Nine common held-out origins; WAPE is error, not accuracy")
    add(10, "Original ARIMA_PLUS / eight-week interval fields", "N/A — not implemented", "Future research assumption only; no ARIMA result or interval coverage invented", "Not implemented")
    add(11, "Highest scored commodities", ", ".join(row["COMMODITY_DESC"] for row in v["top_categories"]), "Ranked category index; not consumer SKU names")
    add(11, "At-risk coupon / cross-sell example", v["top_categories"][0]["COMMODITY_DESC"] + " reactivation coupon (illustrative future test)", "No verified lapsing subgroup/action outcome, promotion lift or ROI; not executed", "Assumption — illustrative")
    add(14, "Live URL", v["local_url"] + " (start with VS Code F5)", "Loopback address only; no public Cloud Run deployment", "Implemented local; public deployment excluded")
    add(17, "Window start week", str(v["start_week"]), "Configured analysis history cutoff")
    return rows


def gaps():
    return [
        {"feature": "Four trained customer clusters / Champions taxonomy", "status": "Not implemented", "replacement": "K-Means k=2; separately show the measured four-rule RFM baseline"},
        {"feature": "BigQuery ML / ARIMA_PLUS", "status": "Not implemented", "replacement": "Saved local gradient boosting with matched naive/seasonal/moving-average comparisons"},
        {"feature": "Eight-week forecasts / 90% intervals", "status": "Assumption for future work", "replacement": "Four direct revenue horizons; no interval coverage asserted"},
        {"feature": "Cross-sell / at-risk coupon effectiveness", "status": "Illustrative assumption only", "replacement": "Review a future measured test; do not invent gain, campaign approval or ROI"},
        {"feature": "Google ADK AgentTools / Gemini", "status": "Excluded from active local workflow", "replacement": "Local Supervisor, three specialists and deterministic evidence Judge"},
        {"feature": "Arbitrary read-only SQL / billing caps", "status": "Not applicable", "replacement": "Registered Python tools over validated local Parquet data"},
        {"feature": "Automatic Judge retry loop", "status": "Not implemented", "replacement": "Rejected output is withheld"},
        {"feature": "Cloud Run live URL / production deployment", "status": "Excluded by user", "replacement": "VS Code integrated browser at 127.0.0.1:8501"},
        {"feature": "100% complete / human usefulness / causal recommendation accuracy", "status": "Not established", "replacement": "Local workflow ready; academic/business review and effectiveness remain open"},
        {"feature": "Proactive alerts / Hindi and Marathi", "status": "Assumption for future work", "replacement": "Supported English analytical requests only"},
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation", type=Path, default=config.REVIEW3_SOURCE_FILE)
    args = parser.parse_args()
    source = args.presentation.resolve()
    if source == config.REVIEW3_FILLED_FILE.resolve():
        raise ValueError("The original source and filled output must be different files.")
    config.REVIEW3_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.REVIEW3_VALIDATION_FILE.unlink(missing_ok=True)
    segment, category = load_segmentation_report(), load_category_report()
    forecast, recommendation = load_forecast_report(), load_recommendation_report()
    load_diagnostic_report()
    data = load_analysis_transactions()
    rfm = pd.read_parquet(config.PROCESSED_DIR / "household_rfm.parquet")
    scores = pd.read_parquet(config.PROCESSED_DIR / "product_scores.parquet")
    profiles = pd.read_parquet(config.PROCESSED_DIR / "segment_profiles.parquet")
    panel = pd.read_parquet(config.PROCESSED_DIR / "forecast_panel.parquet")
    master = json.loads(config.MASTER_REPORT_FILE.read_text(encoding="utf-8"))
    readiness = json.loads((config.OUTPUTS_DIR / "local_readiness.json").read_text(encoding="utf-8"))
    values = calculate_values(data, rfm, scores, profiles, panel, forecast, master, readiness)
    paths = source_paths(source)
    fingerprints = {name: file_fingerprint(path) for name, path in paths.items()}
    original_slides = []
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            import re
            match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
            if match:
                _, body, title = inspect_slide(archive.read(name).decode("utf-8"))
                original_slides.append({"slide": int(match.group(1)), "title": title["paragraphs"][0] if title else "",
                                        "body": body["paragraphs"]})
    original_slides.sort(key=lambda item: item["slide"])
    write_json(config.REVIEW3_OUTPUT_DIR / "original_slide_text.json", original_slides)
    plan = slide_plan(values, segment, category, recommendation)
    audit = build_deck(source, config.REVIEW3_FILLED_FILE, plan)
    if file_fingerprint(source) != fingerprints["presentation"]:
        raise ValueError("Original presentation changed during preparation.")
    rows = value_rows(values, segment)
    pd.DataFrame(rows).to_csv(config.REVIEW3_OUTPUT_DIR / "blank_values.csv", index=False)
    pd.DataFrame(values["rfm_rule_groups"].values()).to_csv(config.REVIEW3_OUTPUT_DIR / "rfm_rule_baseline.csv", index=False)
    pd.DataFrame(values["kmeans_groups"]).to_csv(config.REVIEW3_OUTPUT_DIR / "kmeans_profiles.csv", index=False)
    lines = ["# Review III: verified blank values", "", "Client date: " + config.REVIEW3_CLIENT_DATE,
             "", "These values use approved weeks 19-102; weekly comparisons use complete weeks 19-101. USD revenue is SALES_VALUE.",
             "", "**Use the revised PPT.** Its RFM rule rows are not four K-Means clusters; ARIMA fields were replaced with correctly labelled gradient-boosting metrics. No unimplemented performance value is invented.",
             "", "| Slide | Field | Value | Status |", "| --- | --- | --- | --- |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[key]).replace("|", "/") for key in ("slide", "field", "value_to_use", "status")) + " |")
    lines += ["", "## Measured K-Means profiles (separate from the four-rule baseline)", "",
              "| Group | Households | Revenue share | Mean selected-window spend |", "| --- | ---: | ---: | ---: |"]
    for row in values["kmeans_groups"]:
        lines.append(f"| {row['segment_name']} | {row['households']:,} | {row['revenue_share_pct']:.2f}% | USD {row['mean_window_spend']:,.2f} |")
    lines += ["", "## Definitions", "",
        "- Discounted-sales share counts recorded revenue on lines with any negative retail/coupon/coupon-match discount. It is descriptive, not promotion exposure, responsiveness or causal lift.",
        "- Average window spend is group revenue divided by its distinct households, not weekly spend or average transaction size.",
        "- Forecast H1 MAPE excludes zero actuals and compares identical category/origin/target rows. First usable training labels are 27/28/29/30 for horizons 1/2/3/4 after eight-week feature warm-up.",
        "- Second-half weekly means compare complete weeks 19-59 (41 weeks) against 60-101 (42 weeks). Peak week 92 does not establish a holiday/demand cause.",
        "- Rule names/actions are provisional; original Champions/Loyal/Occasional/At-Risk semantic names are not validated.",
        "", "## Missing features and explicit assumptions", ""]
    for item in gaps():
        lines.append(f"- **{item['feature']} — {item['status']}:** {item['replacement']}.")
    lines += ["", "Original PPT preserved. Source/metrics/corrections are recorded in review3_report.json; separate review3_validation.json must PASS. Layout retains source shapes/styles, with body text adjusted to 18pt and normal autofit. No actual PowerPoint rendering has been performed."]
    (config.REVIEW3_OUTPUT_DIR / "blank_values.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    preview = ["# Revised Review III slide text", ""]
    for slide in original_slides:
        content = plan.get(slide["slide"], {"title": slide["title"], "paragraphs": slide["body"]})
        preview += [f"## Slide {slide['slide']}: {content['title']}", ""] + ["- " + paragraph for paragraph in content["paragraphs"]] + [""]
    (config.REVIEW3_OUTPUT_DIR / "revised_slide_text.md").write_text("\n".join(preview), encoding="utf-8")
    artifacts = [config.REVIEW3_FILLED_FILE, *[config.REVIEW3_OUTPUT_DIR / name for name in
                 ("original_slide_text.json", "blank_values.csv", "blank_values.md", "rfm_rule_baseline.csv", "kmeans_profiles.csv", "revised_slide_text.md")]]
    report = {"status": "BUILT_REQUIRES_VALIDATION", "client_date": config.REVIEW3_CLIENT_DATE,
              "source_presentation": str(source), "policy_fingerprint": policy_fingerprint(),
              "sources": fingerprints, "values": values, "value_rows": rows, "feature_gaps": gaps(),
              "slide_count": len(original_slides), "slides_revised": len(audit),
              "original_blank_count": sum(change["original_blank_count"] for slide in audit for change in slide["changes"]),
              "text_changes": audit, "expected_slide_text": {str(number): content for number, content in plan.items()},
              "original_preserved": True, "assumed_numeric_performance_results": False,
              "powerpoint_rendering_verified": False, "artifacts": [file_fingerprint(path) for path in artifacts]}
    write_json(config.REVIEW3_REPORT_FILE, report)
    print(f"Prepared {len(rows)} value entries; filled {report['original_blank_count']} blank slots across {len(audit)} revised slides.", flush=True)
    print("Saved", config.REVIEW3_FILLED_FILE, flush=True)


if __name__ == "__main__":
    main()
