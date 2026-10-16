"""Check consolidated numbers and every frozen schema/hash against current sources."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.build_ml_evaluation import input_reports
from src.category_access import load_category_report
from src.diagnostic_access import load_diagnostic_report
from src.forecast_access import load_forecast_report
from src.recommendation_access import load_recommendation_report
from src.segment_access import load_segmentation_report
from src.scope import policy_fingerprint


def main():
    report=json.loads(config.ML_EVALUATION_FILE.read_text(encoding="utf-8"))
    source={"segmentation":load_segmentation_report(),"category":load_category_report(),
            "forecast":load_forecast_report(),"recommendations":load_recommendation_report(),"week":load_diagnostic_report()}
    assert report["policy_fingerprint"]==policy_fingerprint()
    assert report["master_sha256"]==file_fingerprint(config.MASTER_FILE)["sha256"]
    assert report["sources"]=={name:file_fingerprint(path) for name,path in input_reports().items()}
    assert report["schema_manifest"]==file_fingerprint(config.SCHEMA_MANIFEST_FILE)
    manifest=json.loads(config.SCHEMA_MANIFEST_FILE.read_text(encoding="utf-8"))
    paths={path.name:path for path in config.PROCESSED_DIR.glob("*.parquet")}
    assert manifest["table_count"]==len(paths) and {table["name"] for table in manifest["tables"]}==set(paths)
    for table in manifest["tables"]:
        path=paths[table["name"]]
        parquet=pq.ParquetFile(path)
        assert table["fingerprint"]==file_fingerprint(path)
        assert table["rows"]==parquet.metadata.num_rows
        assert table["columns"]==[{"name":field.name,"type":str(field.type),"nullable":field.nullable} for field in parquet.schema_arrow]
    segment=source["segmentation"]
    assert report["segmentation"]["chosen_k"]==segment["chosen_k"] and report["segmentation"]["households"]==segment["households"]
    assert np.isclose(report["segmentation"]["silhouette"],segment["silhouette"])
    assert np.isclose(report["segmentation"]["initialization_mean_ari"],segment["stability_mean_ari"])
    category=source["category"]
    assert report["category"]["weights"]==category["weights"] and report["category"]["sensitivity"]==category["sensitivity"]
    assert report["category"]["available_promotion_associations"]==category["scored_eligible_promotion_associations"]
    forecast=source["forecast"]
    assert report["forecast"]["overall_metrics"]==forecast["overall_metrics"]
    assert report["forecast"]["four_week_total_metrics"]==forecast["four_week_total_metrics"]
    assert report["forecast"]["schedule"]==forecast["schedule"]
    assert report["forecast"]["serving_methods"]=={h:selection["serving_method"] for h,selection in forecast["selections"].items()}
    assert report["forecast"]["wins_by_horizon"]==forecast["model_beats_all_three_baselines_categories_by_horizon"]
    csv=pd.read_csv(config.OUTPUTS_DIR/"evaluation_forecast_comparison.csv")
    pd.testing.assert_frame_equal(csv,pd.DataFrame(forecast["overall_metrics"]),check_dtype=False)
    rec=source["recommendations"]
    for field in ["eligible_counts","weights","priority_counts","top10_overlap_count"]:
        assert report["recommendations"][field]==rec[field]
    assert report["recommendations"]["shared_categories"]==rec["top10_shared_categories"]
    assert report["week_diagnosis"]["macro"]==source["week"]["macro"] and report["week_diagnosis"]["breadth"]==source["week"]["breadth"]
    assert report["week_diagnosis"]["cause_verified"] is False
    for item in report["artifacts"]:
        assert item==file_fingerprint(config.OUTPUTS_DIR/item["name"])
    write_json(config.ML_EVALUATION_VALIDATION_FILE,{"status":"PASS","evaluation_sha256":file_fingerprint(config.ML_EVALUATION_FILE)["sha256"],
        "schema_manifest_sha256":file_fingerprint(config.SCHEMA_MANIFEST_FILE)["sha256"],"processed_tables":len(paths),
        "checks":["All five stage summaries equal fingerprint-validated source reports","Every processed table schema, row count and SHA256 matches the frozen manifest","Exported forecast comparisons and consolidated artifact hashes match"],
        "business_usefulness_review_complete":False,"cloud_access_or_deployment_verified":False})
    print(f"PASS: consolidated ML evaluation and {len(paths)} processed schemas",flush=True)


if __name__=="__main__":
    main()
