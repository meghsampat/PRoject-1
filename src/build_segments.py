"""Train and save segmentation artifacts from the approved processed-data snapshot."""
from pathlib import Path
import pickle
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sklearn
from sklearn.metrics import adjusted_rand_score
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.build_master import save_parquet
from src.data_access import load_processed_master, load_validated_aggregate
from src.rfm import build_rfm
from src.scope import policy_fingerprint
from src.segmentation import fit_segmentation, segmentation_settings, settings_fingerprint
from src.segment_profiles import build_affinity, build_profiles, demographic_profiles


def main():
    households = load_validated_aggregate("household_summary")
    master = load_processed_master(require_scope=True)
    demographics = pd.read_parquet(config.PROCESSED_DIR / "household_demographics.parquet")
    rfm = build_rfm(households)
    first_observed = master.groupby("household_key").WEEK_NO.min()
    rfm["first_observed_source_week"] = rfm.household_key.map(first_observed)
    rfm["late_panel_entry"] = rfm.first_observed_source_week.gt(config.ANALYSIS_START_WEEK)
    rfm["has_demographics"] = rfm.household_key.isin(demographics.household_key)
    fit = fit_segmentation(rfm)
    segments = rfm.assign(segment=fit["labels"] + 1)
    profiles = build_profiles(segments)
    segments = segments.merge(profiles[["segment", "segment_name"]], on="segment", validate="many_to_one")
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master)]
    affinity = build_affinity(window, segments)
    demographic_table = demographic_profiles(segments, demographics)
    comparison = pd.crosstab(segments.segment, segments.rule_segment).reset_index()
    rule_ari = float(adjusted_rand_score(segments.rule_segment, segments.segment))
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in [("scaler", fit["scaler"]), ("kmeans_model", fit["model"])]:
        (config.MODELS_DIR / f"{name}.pkl").write_bytes(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))
    tables = {
        "household_rfm": rfm, "clustering_features": fit["features"],
        "household_clusters": segments[["household_key", "segment"]], "household_segments": segments,
        "segment_profiles": profiles, "segment_product_affinity": affinity,
        "segment_demographic_profiles": demographic_table,
    }
    for name, frame in tables.items():
        save_parquet(frame, config.PROCESSED_DIR / f"{name}.parquet")
    fit["evaluation"].to_csv(config.OUTPUTS_DIR / "clustering_evaluation.csv", index=False)
    fit["stability"].to_csv(config.OUTPUTS_DIR / "clustering_stability.csv", index=False)
    comparison.to_csv(config.OUTPUTS_DIR / "rfm_cluster_comparison.csv", index=False)
    save_parquet(fit["seed_assignments"], config.OUTPUTS_DIR / "clustering_seed_assignments.parquet")
    figures = make_subplots(rows=2, cols=2, subplot_titles=("Inertia / elbow", "Sampled silhouette", "Initialization stability: mean ARI", "PCA projection of saved assignments"))
    evaluation = fit["evaluation"]
    for row, col, field in [(1, 1, "inertia"), (1, 2, "silhouette"), (2, 1, "stability_mean_ari")]:
        figures.add_trace(go.Scatter(x=evaluation.k, y=evaluation[field], mode="lines+markers", name=field), row=row, col=col)
        figures.update_xaxes(title_text="Candidate k", row=row, col=col)
    features = fit["features"]
    figures.add_trace(go.Scatter(x=features.pca_1, y=features.pca_2, mode="markers", name="Households", marker={"color": segments.segment, "size": 4, "opacity": 0.5}), row=2, col=2)
    figures.update_layout(title="Approved-scope RFM clustering diagnostics; groups are practical divisions, not proven natural types", height=800)
    figures.write_html(config.OUTPUTS_DIR / "clustering_diagnostics.html", include_plotlyjs=True)
    artifacts = [file_fingerprint(config.PROCESSED_DIR / f"{name}.parquet") for name in tables]
    artifacts += [file_fingerprint(config.MODELS_DIR / f"{name}.pkl") for name in ["scaler", "kmeans_model"]]
    artifacts += [file_fingerprint(config.OUTPUTS_DIR / name) for name in ["clustering_evaluation.csv", "clustering_stability.csv", "rfm_cluster_comparison.csv", "clustering_seed_assignments.parquet", "clustering_diagnostics.html"]]
    report = {
        "status": "BUILT_REQUIRES_INDEPENDENT_VALIDATION", "policy_fingerprint": policy_fingerprint(),
        "settings_fingerprint": settings_fingerprint(), "settings": segmentation_settings(),
        "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"],
        "household_summary_sha256": file_fingerprint(config.PROCESSED_DIR / "household_summary.parquet")["sha256"],
        "demographic_lookup_sha256": file_fingerprint(config.PROCESSED_DIR / "household_demographics.parquet")["sha256"],
        "households": int(len(segments)), "revenue": float(segments.revenue.sum()),
        "transaction_lines": int(len(window)), "start_week": int(window.WEEK_NO.min()), "end_week": int(window.WEEK_NO.max()),
        "reference_day": int(window.DAY.max()), "chosen_k": int(fit["chosen_k"]),
        "silhouette": fit["silhouette"], "stability_mean_ari": fit["stability_mean_ari"],
        "rule_baseline_adjusted_rand_index": rule_ari,
        "pca_explained_variance_ratio": fit["pca_explained_variance_ratio"],
        "sklearn_version": sklearn.__version__, "numpy_version": np.__version__,
        "python_version": sys.version.split()[0], "artifacts": artifacts,
        "selection": "Highest sampled silhouette among candidates with minimum 5% cluster share and mean initialization ARI at least 0.80; final model seed 42",
        "limitations": ["Practical divisions of a customer continuum; not proof of natural classes", "Stability changes initialization seeds, not time periods or customer samples", "Business names and actions are provisional descriptions of medians and need human usefulness review", "Rates use first observed in-window purchase through the end day, not known tenure", "Late panel entry uses first retained source transaction, not a verified enrollment date", "Demographics describe covered households only and are not clustering inputs", "Affinity is category revenue share within a segment divided by overall category revenue share; association is not causation", "Rule-baseline ARI measures agreement, not classification accuracy"],
    }
    write_json(config.SEGMENT_BUILD_FILE, report)
    print(f"Saved RFM and models for {len(segments):,} households; chosen k={fit['chosen_k']}, sampled silhouette={fit['silhouette']:.4f}, mean seed ARI={fit['stability_mean_ari']:.4f}.", flush=True)
    print("Run python src/validate_segments.py before serving the saved models.", flush=True)


if __name__ == "__main__":
    main()

