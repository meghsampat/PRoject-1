"""Build fingerprinted week-92 source diagnosis without changing any models or data."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import plotly.express as px
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.data_access import load_analysis_transactions,load_validated_aggregate
from src.week_diagnostics import diagnose_week,settings_fingerprint
from src.scope import policy_fingerprint


def main():
    config.DIAG_VALIDATION_FILE.unlink(missing_ok=True)
    window=load_analysis_transactions()
    weekly_source=load_validated_aggregate("commodity_weekly")
    weekly,groups,report=diagnose_week(window)
    weekly.to_csv(config.OUTPUTS_DIR/config.DIAG_TABLE_FILES["weekly"],index=False)
    for name,frame in groups.items():
        frame.to_csv(config.OUTPUTS_DIR/config.DIAG_TABLE_FILES[name],index=False)
    figure=px.bar(groups["department"],x="DEPARTMENT",y="delta_revenue",
                  labels={"delta_revenue":"Revenue difference from neighbour mean (USD)"},
                  title=f"Dataset week {config.DIAG_TARGET_WEEK}: department revenue contribution")
    figure.write_html(config.OUTPUTS_DIR/config.DIAG_CHART_FILE,include_plotlyjs=True)
    report.update({"status":"BUILT_REQUIRES_VALIDATION","policy_fingerprint":policy_fingerprint(),
        "settings_fingerprint":settings_fingerprint(),"master_sha256":file_fingerprint(config.MASTER_FILE)["sha256"],
        "weekly_sha256":file_fingerprint(config.PROCESSED_DIR/"commodity_weekly.parquet")["sha256"],
        "start_week":int(window.WEEK_NO.min()),"end_week":int(window.WEEK_NO.max()),
        "transaction_lines":len(window),"window_revenue":float(window.SALES_VALUE.sum()),"households":int(window.household_key.nunique()),
        "artifacts":[file_fingerprint(config.OUTPUTS_DIR/name) for name in [*config.DIAG_TABLE_FILES.values(),config.DIAG_CHART_FILE]],
        "note":"Revenue is SALES_VALUE in USD. Reference is the mean of equal-length neighbouring complete weeks, not a causal counterfactual. Department/store positive shares divide by positive changes only, not net change. Group baskets/households must not be added. Breadth thresholds are descriptive engineering criteria. No verified holiday, demand cause, promotion effect or data corruption is inferred. Quantity is not interpreted as physical volume."})
    write_json(config.DIAG_REPORT_FILE,report)
    print(report["macro"],flush=True)
    print(report["breadth"],flush=True)
    print(report["interpretation"],flush=True)
    print("Run src/validate_week_diagnosis.py.",flush=True)


if __name__=="__main__":
    main()
