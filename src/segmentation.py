"""Evaluate K-Means and initialization stability without forcing a target cluster count."""
from itertools import combinations
import hashlib
import json
import math
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from src import config
from src.rfm import check_feature_values


def segmentation_settings():
    return {"features": config.SEGMENT_FEATURES, "transform": "log1p", "scaler": "StandardScaler",
            "candidate_k": list(config.CLUSTER_K_VALUES), "random_state": config.RANDOM_STATE,
            "n_init": config.KMEANS_N_INIT, "stability_seeds": list(config.STABILITY_SEEDS),
            "minimum_cluster_share": config.MIN_CLUSTER_SHARE,
            "minimum_households": config.SEGMENT_MIN_HOUSEHOLDS,
            "minimum_stability_mean_ari": config.MIN_STABILITY_MEAN_ARI,
            "silhouette_sample_size": config.SILHOUETTE_SAMPLE_SIZE,
            "rfm_score_bins": config.RFM_SCORE_BINS,
            "rfm_rule_thresholds": [config.RFM_HIGH_SCORE, config.RFM_LOW_RECENCY_SCORE, config.RFM_ACTIVE_SCORE],
            "profile_thresholds": [config.PROFILE_HIGH_RATIO, config.PROFILE_LONG_GAP_DAYS]}


def settings_fingerprint():
    return hashlib.sha256(json.dumps(segmentation_settings(), sort_keys=True).encode()).hexdigest()


def fit_segmentation(rfm):
    raw_features = check_feature_values(rfm)
    if len(rfm) < 4:
        raise ValueError("Segmentation requires at least four households.")
    logged = np.log1p(raw_features)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(logged)
    unique_points = len(np.unique(scaled, axis=0))
    minimum_size = max(config.SEGMENT_MIN_HOUSEHOLDS, math.ceil(len(rfm) * config.MIN_CLUSTER_SHARE))
    rows, stability_rows, assignments = [], [], []
    best = None
    with threadpool_limits(limits=1):
        for k in config.CLUSTER_K_VALUES:
            if k >= len(rfm) or k > unique_points:
                continue
            models, labels_by_seed = {}, {}
            for seed in config.STABILITY_SEEDS:
                model = KMeans(n_clusters=k, random_state=seed, n_init=config.KMEANS_N_INIT)
                labels = model.fit_predict(scaled)
                models[seed], labels_by_seed[seed] = model, labels
                assignments.append(pd.DataFrame({"household_key": rfm.household_key, "k": k, "seed": seed, "cluster": labels}))
            pair_scores = []
            for left, right in combinations(config.STABILITY_SEEDS, 2):
                ari = float(adjusted_rand_score(labels_by_seed[left], labels_by_seed[right]))
                pair_scores.append(ari)
                stability_rows.append({"k": k, "seed_a": left, "seed_b": right, "adjusted_rand_index": ari})
            base = models[config.RANDOM_STATE]
            labels = labels_by_seed[config.RANDOM_STATE]
            sizes = np.bincount(labels, minlength=k)
            score = float(silhouette_score(scaled, labels, sample_size=min(len(rfm), config.SILHOUETTE_SAMPLE_SIZE), random_state=config.RANDOM_STATE))
            mean_ari = float(np.mean(pair_scores))
            eligible = bool(sizes.min() >= minimum_size and mean_ari >= config.MIN_STABILITY_MEAN_ARI)
            rows.append({"k": k, "inertia": float(base.inertia_), "silhouette": score,
                         "minimum_cluster_size": int(sizes.min()), "minimum_cluster_share": float(sizes.min() / len(rfm)),
                         "stability_mean_ari": mean_ari, "stability_min_ari": float(min(pair_scores)), "eligible": eligible})
            if eligible and (best is None or score > best["silhouette"]):
                best = {"model": base, "labels": labels, "chosen_k": k, "silhouette": score, "stability_mean_ari": mean_ari}
    if best is None:
        raise ValueError("No cluster candidate meets size and initialization-stability checks; no artificial split was selected.")
    pca = PCA(n_components=2, svd_solver="full")
    projection = pca.fit_transform(scaled)
    features = pd.DataFrame({"household_key": rfm.household_key})
    for index, name in enumerate(config.SEGMENT_FEATURES):
        features[f"log1p_{name}"] = logged[name].to_numpy()
        features[f"scaled_{name}"] = scaled[:, index]
    features["pca_1"], features["pca_2"] = projection[:, 0], projection[:, 1]
    return {**best, "scaler": scaler, "features": features, "evaluation": pd.DataFrame(rows),
            "stability": pd.DataFrame(stability_rows), "seed_assignments": pd.concat(assignments, ignore_index=True),
            "pca_explained_variance_ratio": [float(value) for value in pca.explained_variance_ratio_]}


def assign_segment(recency_days, baskets_per_week, revenue_per_week, scaler, model):
    """Apply the fitted transform/model to one household's nonnegative RFM features."""
    features = pd.DataFrame([[recency_days, baskets_per_week, revenue_per_week]], columns=config.SEGMENT_FEATURES)
    logged = np.log1p(check_feature_values(features))
    return int(model.predict(scaler.transform(logged))[0]) + 1
