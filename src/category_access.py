"""Reject stale category/promotion artifacts before serving saved intelligence."""
import json
import math
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint
from src.scope import policy_fingerprint
from src.category_scoring import settings_fingerprint


def load_promotion_report():
    report = json.loads(config.PROMOTION_BUILD_FILE.read_text(encoding="utf-8"))
    validation = json.loads(config.PROMOTION_VALIDATION_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint") != policy_fingerprint() or report.get("master_sha256") != file_fingerprint(config.MASTER_FILE)["sha256"]:
        raise ValueError("Promotion source/scope changed; prepare and validate promotions again.")
    if report.get("weekly_sha256") != file_fingerprint(config.PROCESSED_DIR / "commodity_weekly.parquet")["sha256"]:
        raise ValueError("Weekly source changed; prepare and validate promotions again.")
    if report.get("settings") != {"display_codes": list(config.DISPLAY_CODES), "mailer_codes": list(config.MAILER_CODES)}:
        raise ValueError("Promotion code interpretation changed; rebuild and validate.")
    expected_names = {f"{name}.parquet" for name in config.PROMOTION_TABLES}
    if {item["name"] for item in report["artifacts"]} != expected_names or len(report["artifacts"]) != len(expected_names):
        raise ValueError("Incomplete promotion artifact inventory.")
    for item in report["artifacts"]:
        if item != file_fingerprint(config.PROCESSED_DIR / item["name"]):
            raise ValueError("Promotion artifact changed since preparation.")
    if validation.get("status") != "PASS" or validation.get("build_report_sha256") != file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"]:
        raise ValueError("Promotion preparation has not passed current validation.")
    return report


def load_category_report(require_validation=True):
    load_promotion_report()
    report = json.loads(config.CATEGORY_BUILD_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint") != policy_fingerprint() or report.get("settings_fingerprint") != settings_fingerprint():
        raise ValueError("Category settings/scope changed; rebuild and validate scores.")
    if report.get("master_sha256") != file_fingerprint(config.MASTER_FILE)["sha256"]:
        raise ValueError("Category source changed; rebuild and validate scores.")
    for name in ["commodity_daily", "commodity_weekly"]:
        if report["sources"][name] != file_fingerprint(config.PROCESSED_DIR / f"{name}.parquet")["sha256"]:
            raise ValueError("Category aggregate source changed.")
    if report.get("promotion_build_sha256") != file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"]:
        raise ValueError("Promotion preparation changed; rebuild category scores.")
    names = {f"{name}.parquet": config.PROCESSED_DIR for name in config.CATEGORY_TABLES}
    names.update({name: config.OUTPUTS_DIR for name in config.CATEGORY_OUTPUT_NAMES})
    if {item["name"] for item in report["artifacts"]} != set(names) or len(report["artifacts"]) != len(names):
        raise ValueError("Incomplete category artifact inventory.")
    for item in report["artifacts"]:
        if item != file_fingerprint(names[item["name"]] / item["name"]):
            raise ValueError("Category artifact changed; rebuild and validate.")
    if require_validation:
        validation = json.loads(config.CATEGORY_VALIDATION_FILE.read_text(encoding="utf-8"))
        if validation.get("status") != "PASS" or validation.get("build_report_sha256") != file_fingerprint(config.CATEGORY_BUILD_FILE)["sha256"]:
            raise ValueError("Category intelligence has not passed current independent validation.")
    return report


def category_result(scoped, start_week, end_week):
    report = load_category_report()
    if (start_week, end_week) != (report["start_week"], report["end_week"]):
        raise ValueError(f"Saved category intelligence requires the full approved window: weeks {report['start_week']}-{report['end_week']}. Reset the sidebar bounds.")
    if len(scoped) != report["transaction_lines"] or scoped.household_key.nunique() != report["households"] or not math.isclose(float(scoped.SALES_VALUE.sum()), report["revenue"], rel_tol=0, abs_tol=config.REVENUE_TOLERANCE_USD):
        raise ValueError("Requested transactions differ from the saved category scoring scope.")
    scores = pd.read_parquet(config.PROCESSED_DIR / "product_scores.parquet")
    rows = scores.head(config.CATEGORY_DISPLAY_N)
    records = rows.astype(object).where(pd.notna(rows), None).to_dict("records")
    return {"currency": config.CURRENCY, "source_table": config.CATEGORY_MODEL_SOURCE,
        "scope": f"IN_SCOPE=True; category score cohort for weeks {start_week}-{end_week}; temporal and promotion indicators use complete weeks {report['first_complete_week']}-{report['last_complete_week']}",
        "start_week": start_week, "end_week": end_week, "revenue_definition": "Sum of SALES_VALUE; no additional discount adjustment",
        "result_status": "Saved descriptive category scores passed arithmetic validation; business usefulness review pending",
        "rows": records, "categories_shown": len(rows), "categories_scored": len(scores),
        "top_score": float(scores.score.max()), "weights": config.CATEGORY_WEIGHTS,
        "scoring_validation_passed": True, "sensitivity": report["sensitivity"],
        "promotion_coverage_share": report["promotion_coverage_share"],
        "promotion_associations_available": report["scored_eligible_promotion_associations"],
        "note": "Scores are analyst-weighted percentile indices, not profitability or causal promotion impact. Growth compares average weekly revenue in unequal-length halves. Missing promotion associations receive a neutral normalized value; raw values remain unknown. Promotion comparisons condition on matched sold product/store/week keys, with support, coverage, revenue-stability and shrinkage guards. Synthetic-calendar YoY is diagnostic only; segment/forecast recommendations are a later stage."}

