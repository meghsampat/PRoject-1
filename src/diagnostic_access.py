"""Reject stale diagnostic evidence before serving a saved week analysis."""
import json
import math
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint
from src.scope import policy_fingerprint
from src.week_diagnostics import settings_fingerprint


def load_diagnostic_report(require_validation=True):
    report=json.loads(config.DIAG_REPORT_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint")!=policy_fingerprint() or report.get("settings_fingerprint")!=settings_fingerprint():
        raise ValueError("Week diagnostic scope/settings changed; rebuild and validate.")
    if report.get("master_sha256")!=file_fingerprint(config.MASTER_FILE)["sha256"] or report.get("weekly_sha256")!=file_fingerprint(config.PROCESSED_DIR/"commodity_weekly.parquet")["sha256"]:
        raise ValueError("Week diagnostic source changed; rebuild and validate.")
    names=set(config.DIAG_TABLE_FILES.values())|{config.DIAG_CHART_FILE}
    if {item["name"] for item in report["artifacts"]}!=names or len(report["artifacts"])!=len(names):
        raise ValueError("Incomplete week diagnostic artifact inventory.")
    for item in report["artifacts"]:
        if item!=file_fingerprint(config.OUTPUTS_DIR/item["name"]):
            raise ValueError("Week diagnostic artifact changed.")
    if require_validation:
        validation=json.loads(config.DIAG_VALIDATION_FILE.read_text(encoding="utf-8"))
        if validation.get("status")!="PASS" or validation.get("build_report_sha256")!=file_fingerprint(config.DIAG_REPORT_FILE)["sha256"]:
            raise ValueError("Week diagnosis has not passed current validation.")
    return report


def diagnostic_result(scoped,start_week,end_week):
    report=load_diagnostic_report()
    if (start_week,end_week)!=(report["start_week"],report["end_week"]):
        raise ValueError("Saved week diagnosis requires the full approved window.")
    if len(scoped)!=report["transaction_lines"] or not math.isclose(float(scoped.SALES_VALUE.sum()),report["window_revenue"],abs_tol=config.REVENUE_TOLERANCE_USD,rel_tol=0):
        raise ValueError("Requested rows differ from the validated diagnostic snapshot.")
    tables={name:pd.read_csv(config.OUTPUTS_DIR/path) for name,path in config.DIAG_TABLE_FILES.items()}
    records=lambda frame:frame.astype(object).where(pd.notna(frame),None).to_dict("records")
    return {"currency":config.CURRENCY,"source_table":config.DIAG_MODEL_SOURCE,
        "scope":f"IN_SCOPE=True; full snapshot weeks {start_week}-{end_week}; target {report['week']} against complete reference weeks {report['reference_weeks']}",
        "start_week":start_week,"end_week":end_week,"revenue_definition":"Sum of SALES_VALUE; no additional discount adjustment",
        "result_status":"Week source diagnosis passed arithmetic validation; cause unverified",
        "week":report["week"],"reference_weeks":report["reference_weeks"],"rows":records(tables["weekly"]),
        "department_rows":records(tables["department"]),"store_rows":records(tables["store"].head(config.DIAG_DISPLAY_N)),
        "macro":report["macro"],"breadth":report["breadth"],"flags":report["flags"],
        "revenue":report["macro"]["revenue"],"reference_revenue":report["macro"]["reference_revenue"],
        "revenue_change_pct":report["macro"]["revenue_change_pct"],
        "classification":report["classification"],"interpretation":report["interpretation"],"decision":report["decision"],
        "validation_passed":True,"cause_verified":False,"note":report["note"]}
