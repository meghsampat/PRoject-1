"""Descriptive segment profiles and revenue-share affinity, with explicit limitations."""
import numpy as np
import pandas as pd
from src import config


def build_profiles(segments):
    profiles = segments.groupby("segment").agg(
        households=("household_key", "size"), revenue=("revenue", "sum"),
        mean_recency_days=("recency_days", "mean"), mean_baskets_per_week=("baskets_per_week", "mean"),
        mean_revenue_per_week=("revenue_per_week", "mean"),
        median_recency_days=("recency_days", "median"), median_baskets_per_week=("baskets_per_week", "median"),
        median_revenue_per_week=("revenue_per_week", "median"),
        late_panel_households=("late_panel_entry", "sum"), demographic_households=("has_demographics", "sum"),
    ).reset_index()
    profiles["household_share_pct"] = profiles.households / len(segments) * 100
    total_revenue = float(segments.revenue.sum())
    if total_revenue <= 0:
        raise ValueError("Segment revenue shares require positive overall revenue.")
    profiles["revenue_share_pct"] = profiles.revenue / total_revenue * 100
    profiles["late_panel_share_pct"] = profiles.late_panel_households / profiles.households * 100
    profiles["demographic_coverage_pct"] = profiles.demographic_households / profiles.households * 100
    medians = segments[config.SEGMENT_FEATURES].median()
    for feature in config.SEGMENT_FEATURES:
        denominator = float(medians[feature])
        profiles[f"{feature}_median_index"] = profiles[f"median_{feature}"] / denominator if denominator else np.nan
    names, actions = [], []
    for row in profiles.itertuples():
        long_gap = row.median_recency_days >= config.PROFILE_LONG_GAP_DAYS
        frequent = row.median_baskets_per_week >= medians.baskets_per_week * config.PROFILE_HIGH_RATIO
        high_spend = row.median_revenue_per_week >= medians.revenue_per_week * config.PROFILE_HIGH_RATIO
        if long_gap:
            name = "Households with long purchase gaps"
            action = "Review purchase gaps and test re-engagement; measure response before claiming an effect."
        elif frequent and high_spend:
            name = "Frequent higher-spend households"
            action = "Test service or availability improvements for frequently purchased categories."
        elif high_spend:
            name = "Higher-spend occasional households"
            action = "Review basket mix and test relevant cross-category offers."
        elif frequent:
            name = "Frequent smaller-basket households"
            action = "Review essentials availability and test small-basket offers."
        else:
            name = "Lower-frequency recent households"
            action = "Review shopping frequency and test retention ideas using a measured comparison."
        names.append(f"{name} (group {row.segment})")
        actions.append(action)
    profiles["segment_name"], profiles["suggested_action"] = names, actions
    return profiles


def build_affinity(window, assignments):
    joined = window.merge(assignments[["household_key", "segment"]], on="household_key", how="left", validate="many_to_one")
    if joined.segment.isna().any() or len(joined) != len(window):
        raise ValueError("Every transaction must have exactly one household segment.")
    categories = sorted(joined.COMMODITY_DESC.astype("string").unique())
    grid = pd.MultiIndex.from_product([sorted(assignments.segment.unique()), categories], names=["segment", "COMMODITY_DESC"])
    affinity = joined.groupby(["segment", "COMMODITY_DESC"], observed=True).agg(revenue=("SALES_VALUE", "sum"), buyers=("household_key", "nunique")).reindex(grid, fill_value=0).reset_index()
    overall = joined.groupby("COMMODITY_DESC", observed=True).SALES_VALUE.sum()
    segment_totals = joined.groupby("segment").SALES_VALUE.sum()
    total = float(joined.SALES_VALUE.sum())
    affinity["overall_category_revenue"] = affinity.COMMODITY_DESC.map(overall)
    affinity["segment_total_revenue"] = affinity.segment.map(segment_totals)
    affinity["segment_category_share"] = affinity.revenue / affinity.segment_total_revenue.replace(0, np.nan)
    affinity["overall_category_share"] = affinity.overall_category_revenue / total
    affinity["affinity_index"] = affinity.segment_category_share / affinity.overall_category_share.replace(0, np.nan)
    return affinity


def demographic_profiles(segments, demographics):
    joined = segments[["household_key", "segment"]].merge(demographics, on="household_key", how="inner", validate="one_to_one")
    rows = []
    for attribute in demographics.columns:
        if attribute == "household_key":
            continue
        counts = joined.groupby(["segment", attribute], dropna=False).size().rename("households").reset_index()
        covered = joined.groupby("segment").size()
        for row in counts.to_dict("records"):
            count = int(row["households"])
            denominator = int(covered.loc[row["segment"]])
            rows.append({"segment": int(row["segment"]), "attribute": attribute,
                         "value": str(row[attribute]), "households": count,
                         "covered_households": denominator, "pct_of_covered_segment": count / denominator * 100})
    return pd.DataFrame(rows)
