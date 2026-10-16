"""RFM scores and readable rule baseline. Scores are not clustering features."""
import numpy as np
import pandas as pd
from src import config


def check_feature_values(frame):
    if frame.empty or not set(config.SEGMENT_FEATURES).issubset(frame.columns):
        raise ValueError("Nonempty RFM feature data is required.")
    values = frame[config.SEGMENT_FEATURES]
    if not all(pd.api.types.is_numeric_dtype(values[column]) and not pd.api.types.is_bool_dtype(values[column]) for column in values) or not np.isfinite(values.to_numpy()).all() or values.lt(0).any().any():
        raise ValueError("RFM features must be numeric, finite and nonnegative; no records were removed.")
    return values


def percentile_scores(values, lower_is_better=False):
    """Tied values get identical scores, using average percentile rank rather than arbitrary order."""
    ranks = values.rank(method="average", pct=True, ascending=not lower_is_better)
    return np.ceil(ranks * config.RFM_SCORE_BINS).clip(1, config.RFM_SCORE_BINS).astype(int)


def build_rfm(households):
    check_feature_values(households)
    if households.household_key.isna().any() or households.household_key.duplicated().any():
        raise ValueError("Household IDs must be nonmissing and unique.")
    frame = households.sort_values("household_key").reset_index(drop=True).copy()
    frame["R_score"] = percentile_scores(frame.recency_days, lower_is_better=True)
    frame["F_score"] = percentile_scores(frame.baskets_per_week)
    frame["M_score"] = percentile_scores(frame.revenue_per_week)
    high, low, active = config.RFM_HIGH_SCORE, config.RFM_LOW_RECENCY_SCORE, config.RFM_ACTIVE_SCORE
    frame["rule_segment"] = np.select([
        (frame.R_score >= high) & (frame.F_score >= high) & (frame.M_score >= high),
        (frame.R_score <= low) & (frame.M_score >= high),
        frame.R_score <= low,
        frame.R_score >= active,
    ], ["Frequent recent higher-spend", "Long-gap higher-spend", "Long-gap lower-spend", "Recently active"], default="Intermediate activity")
    return frame

