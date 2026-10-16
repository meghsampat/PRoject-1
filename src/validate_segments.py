"""Independent checks of saved RFM, profiles, affinity and model reproduction."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from itertools import combinations
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from threadpoolctl import threadpool_limits
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_processed_master, load_validated_aggregate
from src.segment_access import load_segment_models
from src.segmentation import assign_segment


def main():
    scaler, model, report = load_segment_models(require_validation=False)
    households = load_validated_aggregate("household_summary").sort_values("household_key").reset_index(drop=True)
    segments = pd.read_parquet(config.HOUSEHOLD_SEGMENTS_FILE).sort_values("household_key").reset_index(drop=True)
    rfm = pd.read_parquet(config.PROCESSED_DIR / "household_rfm.parquet").sort_values("household_key").reset_index(drop=True)
    profiles = pd.read_parquet(config.SEGMENT_PROFILES_FILE)
    affinity = pd.read_parquet(config.PROCESSED_DIR / "segment_product_affinity.parquet")
    master = load_processed_master(require_scope=True)
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master)]
    checks = []
    assert segments.household_key.is_unique and np.array_equal(segments.household_key, households.household_key)
    for column in households.columns:
        pd.testing.assert_series_equal(segments[column], households[column], check_dtype=False)
    direct = window.groupby("household_key").agg(revenue=("SALES_VALUE", "sum"), baskets=("BASKET_ID", "nunique"), last_day=("DAY", "max"), first_day=("DAY", "min")).sort_index()
    assert np.allclose(direct.revenue, segments.revenue)
    assert np.array_equal(direct.baskets, segments.baskets)
    assert np.array_equal(report["reference_day"] - direct.last_day, segments.recency_days)
    assert np.allclose(segments.observed_weeks, (report["reference_day"] - direct.first_day + 1) / config.DAYS_PER_WEEK)
    assert np.allclose(segments.baskets_per_week, segments.baskets / segments.observed_weeks)
    assert np.allclose(segments.revenue_per_week, segments.revenue / segments.observed_weeks)
    checks.append("Household coverage and RFM arithmetic match processed transactions")
    for feature, score_column, reversed_score in [("recency_days", "R_score", True), ("baskets_per_week", "F_score", False), ("revenue_per_week", "M_score", False)]:
        assert rfm[score_column].between(1, config.RFM_SCORE_BINS).all()
        assert rfm.groupby(feature)[score_column].nunique().le(1).all()
        ordered = rfm.sort_values(feature)[score_column].to_numpy()
        assert (np.diff(ordered) <= 0).all() if reversed_score else (np.diff(ordered) >= 0).all()
    checks.append("Scores preserve ties and order; lower recency has higher scores")
    logged = np.log1p(segments[config.SEGMENT_FEATURES])
    scaled = scaler.transform(logged)
    assert np.allclose(scaler.inverse_transform(scaled), logged)
    assert np.allclose(scaler.mean_, logged.mean().to_numpy())
    expected_scale = logged.std(ddof=0).to_numpy()
    assert np.allclose(scaler.scale_, np.where(expected_scale == 0, 1, expected_scale))
    features = pd.read_parquet(config.PROCESSED_DIR / "clustering_features.parquet").sort_values("household_key").reset_index(drop=True)
    assert np.array_equal(features.household_key, segments.household_key)
    for index, name in enumerate(config.SEGMENT_FEATURES):
        assert np.allclose(features[f"log1p_{name}"], logged[name])
        assert np.allclose(features[f"scaled_{name}"], scaled[:, index])
    predictions = model.predict(scaled) + 1
    assert np.array_equal(predictions, segments.segment)
    for row in segments.head(10).itertuples():
        assert assign_segment(row.recency_days, row.baskets_per_week, row.revenue_per_week, scaler, model) == row.segment
    checks.append("Reloaded scaler/model reproduce every household assignment and single-household inference")
    evaluation = pd.read_csv(config.OUTPUTS_DIR / "clustering_evaluation.csv")
    selected = evaluation.loc[evaluation.k.eq(report["chosen_k"])].iloc[0]
    assert selected.eligible and np.isclose(selected.silhouette, evaluation.loc[evaluation.eligible, "silhouette"].max())
    actual_score = silhouette_score(scaled, predictions, sample_size=min(len(segments), config.SILHOUETTE_SAMPLE_SIZE), random_state=config.RANDOM_STATE)
    assert np.isclose(actual_score, report["silhouette"])
    assert np.isclose(model.inertia_, selected.inertia)
    assert model.random_state == config.RANDOM_STATE
    assert profiles.households.min() >= np.ceil(len(segments) * config.MIN_CLUSTER_SHARE)
    with threadpool_limits(limits=1):
        seed_labels = {seed: KMeans(n_clusters=report["chosen_k"], n_init=config.KMEANS_N_INIT, random_state=seed).fit_predict(scaled) for seed in config.STABILITY_SEEDS}
    pair_scores = [adjusted_rand_score(seed_labels[a], seed_labels[b]) for a, b in combinations(config.STABILITY_SEEDS, 2)]
    assert np.isclose(np.mean(pair_scores), report["stability_mean_ari"])
    assert report["stability_mean_ari"] >= config.MIN_STABILITY_MEAN_ARI
    assert np.array_equal(seed_labels[config.RANDOM_STATE] + 1, segments.segment)
    checks.append("Selected k, silhouette, minimum size and four-seed stability reproduce")
    assert profiles.households.sum() == len(segments)
    assert np.isclose(profiles.revenue.sum(), window.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    assert np.isclose(profiles.household_share_pct.sum(), 100) and np.isclose(profiles.revenue_share_pct.sum(), 100)
    demographics = pd.read_parquet(config.PROCESSED_DIR / "household_demographics.parquet")
    assert profiles.demographic_households.sum() == segments.household_key.isin(demographics.household_key).sum()
    assert np.array_equal(segments.has_demographics, segments.household_key.isin(demographics.household_key))
    first_weeks = master.groupby("household_key").WEEK_NO.min()
    assert np.array_equal(segments.first_observed_source_week, segments.household_key.map(first_weeks))
    assert np.array_equal(segments.late_panel_entry, segments.first_observed_source_week.gt(config.ANALYSIS_START_WEEK))
    for row in profiles.itertuples():
        members = segments.loc[segments.segment.eq(row.segment)]
        assert len(members) == row.households
        assert np.isclose(members.recency_days.median(), row.median_recency_days)
        assert np.isclose(members.baskets_per_week.median(), row.median_baskets_per_week)
        assert np.isclose(members.revenue_per_week.median(), row.median_revenue_per_week)
    checks.append("Profile counts, revenue shares, medians, late-entry and demographic coverage reconcile")
    assert not affinity.duplicated(["segment", "COMMODITY_DESC"]).any()
    assert len(affinity) == report["chosen_k"] * window.COMMODITY_DESC.nunique()
    assert np.isclose(affinity.revenue.sum(), window.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    joined = window.merge(segments[["household_key", "segment"]], on="household_key", validate="many_to_one")
    direct_affinity = joined.groupby(["segment", "COMMODITY_DESC"], observed=True).SALES_VALUE.sum()
    for row in affinity.itertuples():
        assert np.isclose(row.revenue, direct_affinity.get((row.segment, row.COMMODITY_DESC), 0))
        if row.overall_category_share > 0 and row.segment_total_revenue > 0:
            assert np.isclose(row.affinity_index, row.segment_category_share / row.overall_category_share)
        else:
            assert pd.isna(row.affinity_index)
    assert np.isclose(adjusted_rand_score(segments.rule_segment, segments.segment), report["rule_baseline_adjusted_rand_index"])
    checks.append("Affinity grid/arithmetic and rule-baseline agreement reproduce without causal claims")
    write_json(config.SEGMENT_VALIDATION_FILE, {"status": "PASS", "build_report_sha256": file_fingerprint(config.SEGMENT_BUILD_FILE)["sha256"],
        "master_sha256": report["master_sha256"], "policy_fingerprint": report["policy_fingerprint"],
        "households": len(segments), "chosen_k": report["chosen_k"], "silhouette": report["silhouette"],
        "stability_mean_ari": report["stability_mean_ari"], "checks": checks,
        "note": "Technical validation passed; business usefulness/human naming review and temporal/sample stability remain pending."})
    for check in checks:
        print(f"PASS: {check}", flush=True)


if __name__ == "__main__":
    main()

