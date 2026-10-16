"""Serve current, independently validated recommendation evidence; no silent subset reuse."""
import json
import math
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint
from src.category_access import load_category_report
from src.forecast_access import load_forecast_report
from src.segment_access import load_segmentation_report
from src.recommendations import settings_fingerprint
from src.scope import policy_fingerprint


def load_recommendation_report(require_validation=True):
    load_category_report()
    load_forecast_report()
    load_segmentation_report()
    report = json.loads(config.REC_BUILD_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint")!=policy_fingerprint() or report.get("settings_fingerprint")!=settings_fingerprint():
        raise ValueError("Recommendation settings/scope changed; rebuild and validate.")
    if report.get("master_sha256")!=file_fingerprint(config.MASTER_FILE)["sha256"]:
        raise ValueError("Recommendation source snapshot changed.")
    for label,paths in [("upstream_builds",config.REC_UPSTREAM_BUILDS),("upstream_validations",config.REC_UPSTREAM_VALIDATIONS)]:
        if report.get(label)!={name:file_fingerprint(path)["sha256"] for name,path in paths.items()}:
            raise ValueError("Recommendation upstream evidence changed; rebuild and validate.")
    locations = {f"{name}.parquet":config.PROCESSED_DIR for name in config.REC_TABLES}
    locations.update({name:config.OUTPUTS_DIR for name in config.REC_OUTPUT_NAMES})
    if {item["name"] for item in report["artifacts"]}!=set(locations) or len(report["artifacts"])!=len(locations):
        raise ValueError("Incomplete recommendation artifact inventory.")
    for item in report["artifacts"]:
        if item!=file_fingerprint(locations[item["name"]]/item["name"]):
            raise ValueError("Recommendation artifact changed; rebuild and validate.")
    if require_validation:
        validation = json.loads(config.REC_VALIDATION_FILE.read_text(encoding="utf-8"))
        if validation.get("status")!="PASS" or validation.get("build_report_sha256")!=file_fingerprint(config.REC_BUILD_FILE)["sha256"]:
            raise ValueError("Recommendations lack current independent validation.")
    return report


def records(frame):
    return frame.astype(object).where(pd.notna(frame),None).to_dict("records")


def recommendation_result(scoped,start_week,end_week):
    report = load_recommendation_report()
    if (start_week,end_week)!=(report["start_week"],report["end_week"]):
        raise ValueError(f"Saved recommendations require the full approved window: weeks {report['start_week']}-{report['end_week']}. Reset the sidebar bounds.")
    if len(scoped)!=report["transaction_lines"] or scoped.household_key.nunique()!=report["households"] or not math.isclose(float(scoped.SALES_VALUE.sum()),report["revenue"],abs_tol=config.REVENUE_TOLERANCE_USD,rel_tol=0):
        raise ValueError("Requested transactions differ from the saved recommendation snapshot.")
    table = pd.read_parquet(config.PROCESSED_DIR/"recommendations.parquet")
    shown = table.loc[table.eligible & table["rank"].le(config.REC_DISPLAY_N)].sort_values(["candidate","rank"])
    counts = {method:int(shown.candidate.eq(method).sum()) for method in config.REC_METHODS}
    return {"currency":config.CURRENCY,"source_table":config.REC_MODEL_SOURCE,
        "scope":f"IN_SCOPE=True; saved weeks {start_week}-{end_week}; momentum uses complete weeks {report['previous_weeks'][0]}-{report['origin_week']}; target dataset weeks {report['forecast_weeks'][0]}-{report['forecast_weeks'][-1]}",
        "start_week":start_week,"end_week":end_week,"revenue_definition":"Sum of SALES_VALUE; no additional discount adjustment",
        "result_status":"Two descriptive recommendation rankings passed arithmetic validation; business plausibility review pending",
        "rows":records(shown),"forecast_candidates_shown":counts["forecast"],"segment_candidates_shown":counts["segment"],
        "top10_overlap_count":report["top10_overlap_count"],"shared_top10_categories":report["top10_shared_categories"],
        "candidate_counts":report["eligible_counts"],"weights":report["weights"],
        "target_segments":report["target_segments"],"target_households":report["target_households"],
        "forecast_weeks":report["forecast_weeks"],"origin_week":report["origin_week"],
        "recent_weeks":report["recent_weeks"],"previous_weeks":report["previous_weeks"],
        "as_of_week":report["as_of_week"],"partial_forecast_overlap":report["partial_forecast_overlap"],
        "validation_passed":True,"business_usefulness_review_complete":False,
        "arbitration":{"selected_candidate":None,"status":"Both lists shown for review; no automatic winner"},
        "note":"Scores compare priorities within each method, not across methods. Promote is a provisional hypothesis for a measured test, not campaign authorization. No incremental promotion revenue, ROI or recommendation accuracy is estimated. Promotion associations are unavailable for this cohort; unknown values remain blank. Target groups describe observed spending, not lifetime value. Snapshot/category/segment evidence includes partial terminal week 102; forecast origin is last complete week 101 and the target period overlaps partial week 102. This is a current-snapshot ranking, not a point-in-time recommendation backtest. Human plausibility review remains pending."}
