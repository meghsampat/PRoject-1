"""Consolidate actual validated ML evidence and freeze processed-table schemas."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from importlib import metadata
import platform
import pandas as pd
import pyarrow.parquet as pq
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.category_access import load_category_report
from src.diagnostic_access import load_diagnostic_report
from src.forecast_access import load_forecast_report
from src.recommendation_access import load_recommendation_report
from src.segment_access import load_segmentation_report
from src.scope import policy_fingerprint


def input_reports():
    return {"segmentation":config.SEGMENT_BUILD_FILE,"segmentation_validation":config.SEGMENT_VALIDATION_FILE,
        "category":config.CATEGORY_BUILD_FILE,"category_validation":config.CATEGORY_VALIDATION_FILE,
        "forecast":config.FORECAST_BUILD_FILE,"forecast_validation":config.FORECAST_VALIDATION_FILE,
        "recommendations":config.REC_BUILD_FILE,"recommendation_validation":config.REC_VALIDATION_FILE,
        "week_diagnosis":config.DIAG_REPORT_FILE,"week_diagnosis_validation":config.DIAG_VALIDATION_FILE}


def schema_snapshot():
    tables=[]
    for path in sorted(config.PROCESSED_DIR.glob("*.parquet")):
        parquet=pq.ParquetFile(path)
        tables.append({"name":path.name,"rows":parquet.metadata.num_rows,"fingerprint":file_fingerprint(path),
                       "columns":[{"name":field.name,"type":str(field.type),"nullable":field.nullable} for field in parquet.schema_arrow]})
    return {"policy_fingerprint":policy_fingerprint(),"table_count":len(tables),"tables":tables,
            "note":"Names/types/order and artifact hashes frozen for the current local snapshot. Arrow nullability is schema metadata, not a count of missing values. Changes require a new manifest and validation."}


def main():
    config.ML_EVALUATION_VALIDATION_FILE.unlink(missing_ok=True)
    segment=load_segmentation_report(); category=load_category_report()
    forecast=load_forecast_report(); recommendations=load_recommendation_report(); diagnosis=load_diagnostic_report()
    snapshot=schema_snapshot()
    write_json(config.SCHEMA_MANIFEST_FILE,snapshot)
    versions={"python":platform.python_version()}
    for package in ["pandas","numpy","scikit-learn","streamlit","plotly","pyarrow","google-genai"]:
        try:versions[package]=metadata.version(package)
        except metadata.PackageNotFoundError:versions[package]=None
    report={"status":"BUILT_REQUIRES_VALIDATION","policy_fingerprint":policy_fingerprint(),
        "master_sha256":file_fingerprint(config.MASTER_FILE)["sha256"],
        "sources":{name:file_fingerprint(path) for name,path in input_reports().items()},
        "schema_manifest":file_fingerprint(config.SCHEMA_MANIFEST_FILE),
        "environment_versions":versions,
        "segmentation":{"households":segment["households"],"chosen_k":segment["chosen_k"],
                        "silhouette":segment["silhouette"],"initialization_mean_ari":segment["stability_mean_ari"],
                        "business_usefulness_review_complete":False},
        "category":{"scored_categories":category["scored_categories"],"weights":category["weights"],
                    "sensitivity":category["sensitivity"],"available_promotion_associations":category["scored_eligible_promotion_associations"]},
        "forecast":{"categories":forecast["forecastable_categories"],"schedule":forecast["schedule"],
                    "overall_metrics":forecast["overall_metrics"],"four_week_total_metrics":forecast["four_week_total_metrics"],
                    "wins_by_horizon":forecast["model_beats_all_three_baselines_categories_by_horizon"],
                    "serving_methods":{h:selection["serving_method"] for h,selection in forecast["selections"].items()}},
        "recommendations":{"eligible_counts":recommendations["eligible_counts"],"weights":recommendations["weights"],
                           "top10_overlap_count":recommendations["top10_overlap_count"],"shared_categories":recommendations["top10_shared_categories"],
                           "priority_counts":recommendations["priority_counts"],"business_usefulness_review_complete":False,
                           "recommendation_accuracy_evaluated":False},
        "week_diagnosis":{"week":diagnosis["week"],"reference_weeks":diagnosis["reference_weeks"],
                          "macro":diagnosis["macro"],"breadth":diagnosis["breadth"],"decision":diagnosis["decision"],"cause_verified":False},
        "limitations":["Unverified synthetic calendar and physical unit interpretation","Promotion signal coverage is sparse; scored association components unavailable",
                       "Human usefulness review pending; initialization stability is not temporal stability","Short chronological test block and overlapping four-week totals",
                       "Recommendation effectiveness/ROI and business arbitration not evaluated","Python 3.11 target, ADK integration, actual cloud proof/deployment and Review 3 pending"]}
    forecast_table=pd.DataFrame(forecast["overall_metrics"])
    csv_path=config.OUTPUTS_DIR/"evaluation_forecast_comparison.csv"
    forecast_table.to_csv(csv_path,index=False)
    lines=["# Consolidated ML evaluation","",
           "Generated 13 October 2026 (client date) from current fingerprint-validated artifacts. This is a technical evaluation, not a claim of final business approval or cloud deployment.","",
           "## Data and environment","",f"Approved scope: core_consumables_v1; master SHA256 {report['master_sha256']}. Analysis weeks 19-102; full time-series weeks 19-101. {snapshot['table_count']} processed Parquet schemas captured. Current Python {versions['python']} is provisional; target 3.11 remains pending.","",
           "## Segmentation","",f"Households {segment['households']:,}; selected k={segment['chosen_k']}; sampled silhouette {segment['silhouette']:.6f}; mean four-seed initialization ARI {segment['stability_mean_ari']:.4f}. Saved model reload reproduces assignments. Human usefulness and temporal/sample stability remain open.","",
           "## Category intelligence","",f"Scored categories {category['scored_categories']}; weights {category['weights']}. 100 weight perturbations: minimum full-ranking Spearman {category['sensitivity']['spearman_all_min']:.6f}, baseline-top-20 Spearman {category['sensitivity']['spearman_baseline_top20_min']:.6f}, minimum top-20 retention {category['sensitivity']['top20_overlap_min']:.0%}. Supported scored promotion comparisons: {category['scored_eligible_promotion_associations']}; missing terms are explicitly neutral, not zero effect.","",
           "## Forecasting","",f"Categories {forecast['forecastable_categories']}; validation windows 72-77/78-83/84-89; frozen test labels 90-101; per-horizon origins 12/11/10/9. Production refits through full week 101. Methods are selected on validation, not test errors.","",
           "| Horizon | Model/method | MAE USD | RMSE USD | MAPE % | WAPE % | Pairs |","| --- | --- | --- | --- | --- | --- | --- |"]
    for row in forecast["overall_metrics"]:
        lines.append(f"| {row['horizon']} | {row['model']} | {row['MAE']:.2f} | {row['RMSE']:.2f} | {row['MAPE_pct']:.2f} | {row['WAPE_pct']:.2f} | {row['prediction_pairs']} |")
    lines.extend(["","### Four-week totals","","| Method | MAE USD | RMSE USD | WAPE % | Paired totals |","| --- | --- | --- | --- | --- |"])
    for row in forecast["four_week_total_metrics"]:
        lines.append(f"| {row['model']} | {row['MAE']:.2f} | {row['RMSE']:.2f} | {row['WAPE_pct']:.2f} | {row['prediction_pairs']} |")
    lines.extend(["",f"Trained model beats all three baselines for {forecast['model_beats_all_three_baselines_categories_by_horizon']} categories by horizon, out of {forecast['forecastable_categories']}. It does not win uniformly; seasonal naive has better overall RMSE at every horizon. WAPE is an error measure, not an accuracy percentage or guarantee. Overlapping totals are dependent observations.","",
                  "## Recommendation hypotheses","",f"Eligible counts {recommendations['eligible_counts']}; weights {recommendations['weights']}; top-ten overlap {recommendations['top10_overlap_count']}, shared category {recommendations['top10_shared_categories']}. Labels {recommendations['priority_counts']}. All rows require review; no causal promotion lift, ROI, recommendation precision or automatic winner is claimed. Snapshot includes partial 102 while forecasts span 102-105 after full origin 101.","",
                  "## Week 92 source diagnosis","",f"Revenue ${diagnosis['macro']['revenue']:,.2f} versus neighbour mean ${diagnosis['macro']['reference_revenue']:,.2f}: {diagnosis['macro']['revenue_change_pct']:+.2f}%. {diagnosis['breadth']['positive_eligible_stores']} of {diagnosis['breadth']['eligible_stores']} eligible stores and {diagnosis['breadth']['positive_major_departments']} of {diagnosis['breadth']['major_departments']} major departments have positive changes. Largest store positive-change share {diagnosis['breadth']['top_store_positive_delta_share']:.2%}. {diagnosis['interpretation']} {diagnosis['decision']}. No models or data changed.","",
                  "## Limitations and remaining gates","",*["- "+item for item in report["limitations"]],"",
                  "Source manifests and machine-readable values: evaluation_ml.json. Schema inventory: processed_schema_manifest.json. Independent consolidated validation: evaluation_ml_validation.json. Full per-category forecast comparisons and losses remain in the existing forecast metric/improvement CSVs. No guide target numbers were copied as results.",""])
    markdown_path=config.OUTPUTS_DIR/"evaluation_ml.md"
    markdown_path.write_text("\n".join(lines),encoding="utf-8")
    report["artifacts"]=[file_fingerprint(csv_path),file_fingerprint(markdown_path)]
    write_json(config.ML_EVALUATION_FILE,report)
    print(f"Consolidated five technical stages and {snapshot['table_count']} processed schemas. Run scripts/validate_ml_evaluation.py.",flush=True)


if __name__=="__main__":
    main()
