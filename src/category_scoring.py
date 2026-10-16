"""Transparent category indicators, ordinal composite scores and weight sensitivity."""
import hashlib
import json
import numpy as np
import pandas as pd
from src import config


def settings_fingerprint():
    names = ["CATEGORY_TOP_N", "CATEGORY_DISPLAY_N", "CATEGORY_WEIGHTS", "CATEGORY_SENSITIVITY_RUNS",
             "CATEGORY_WEIGHT_PERTURBATION", "CATEGORY_MIN_SPEARMAN", "CATEGORY_MIN_TOP20_OVERLAP",
             "CATEGORY_YOY_MIN_MONTH_PAIRS", "CATEGORY_NEUTRAL_COMPONENT", "CATEGORY_LABEL_TOP_N",
             "CATEGORY_SCORE_SCALE", "RANDOM_STATE", "PROMO_MIN_GROUP_WEEKS", "PROMO_SHRINK_WEEKS",
             "PROMO_MIN_COVERAGE", "PROMO_MIN_MATCHED_KEYS", "PROMO_MAX_REVENUE_CV", "FORECASTABLE_WEEK_SHARE"]
    return hashlib.sha256(json.dumps({name: getattr(config, name) for name in names}, sort_keys=True).encode()).hexdigest()


def category_indicators(window, weekly, daily):
    totals = window.groupby("COMMODITY_DESC").agg(revenue=("SALES_VALUE", "sum"),
              buyers=("household_key", "nunique"), baskets=("BASKET_ID", "nunique"))
    buyer_weeks = window.groupby(["COMMODITY_DESC", "household_key"]).WEEK_NO.nunique()
    repeated = buyer_weeks.ge(2).groupby(level=0).sum()
    totals["repeat_buyers"] = repeated
    totals["revenue_share"] = totals.revenue / window.SALES_VALUE.sum()
    totals["household_penetration"] = totals.buyers / window.household_key.nunique()
    totals["repeat_purchase_rate"] = totals.repeat_buyers / totals.buyers
    totals["revenue_per_buyer"] = totals.revenue / totals.buyers
    weeks = sorted(weekly.WEEK_NO.unique())
    first = weeks[:len(weeks) // 2]
    second = weeks[len(weeks) // 2:]
    halves = weekly.assign(half=np.where(weekly.WEEK_NO.isin(first), "first", "second"))
    rates = halves.groupby(["COMMODITY_DESC", "half"]).revenue.mean().unstack()
    totals["first_half_weekly_revenue"] = rates["first"]
    totals["second_half_weekly_revenue"] = rates["second"]
    totals["growth"] = rates["second"] / rates["first"].replace(0, np.nan) - 1

    # Complete synthetic-calendar months only, matching month number in two years.
    dates = pd.to_datetime(daily.DATE)
    months = daily.assign(year=dates.dt.year, month=dates.dt.month, month_days=dates.dt.days_in_month)
    monthly = months.groupby(["COMMODITY_DESC", "year", "month"]).agg(
        revenue=("revenue", "sum"), days=("DAY", "nunique"), expected_days=("month_days", "first")).reset_index()
    full = monthly.loc[monthly.days.eq(monthly.expected_days)]
    yoy = []
    years = sorted(full.year.unique())
    for category in totals.index:
        group = full.loc[full.COMMODITY_DESC.eq(category)]
        pair = group.pivot(index="month", columns="year", values="revenue")
        days = group.pivot(index="month", columns="year", values="days")
        if len(years) == 2 and all(year in pair for year in years):
            paired = pair.dropna()
            n = len(paired)
            before = paired[years[0]].sum() / days.loc[paired.index, years[0]].sum() if n else np.nan
            after = paired[years[1]].sum() / days.loc[paired.index, years[1]].sum() if n else np.nan
            value = after / before - 1 if n >= config.CATEGORY_YOY_MIN_MONTH_PAIRS and before > 0 else np.nan
        else:
            n, value = 0, np.nan
        yoy.append({"COMMODITY_DESC": category, "yoy_month_pairs": n, "yoy_growth": value})
    result = totals.reset_index().merge(pd.DataFrame(yoy), on="COMMODITY_DESC", validate="one_to_one")
    result = result.sort_values(["revenue", "COMMODITY_DESC"], ascending=[False, True]).reset_index(drop=True)
    result["revenue_rank"] = np.arange(1, len(result) + 1)
    result["score_eligible"] = result.revenue_rank.le(config.CATEGORY_TOP_N)
    # Growth is deliberately not used for tiny categories outside the scoring cohort.
    result.loc[~result.score_eligible, "growth"] = np.nan
    result["growth_sign_disagrees_yoy"] = result.growth.notna() & result.yoy_growth.notna() & ((result.growth > 0) != (result.yoy_growth > 0))
    return result


def rank_normalize(values):
    known = values.dropna()
    result = pd.Series(config.CATEGORY_NEUTRAL_COMPONENT, index=values.index, dtype=float)
    if len(known) > 1 and known.nunique() > 1:
        result.loc[known.index] = (known.rank(method="average") - 1) / (len(known) - 1)
    return result


def weighted_scores(normalized, weights):
    if set(weights) != set(config.CATEGORY_WEIGHTS) or any(not np.isfinite(value) or value < 0 for value in weights.values()) or not np.isclose(sum(weights.values()), 1):
        raise ValueError("Category weights must be finite, nonnegative and sum to one.")
    if normalized.isna().any().any() or not np.isfinite(normalized.to_numpy()).all() or not normalized.ge(0).all().all() or not normalized.le(1).all().all():
        raise ValueError("Normalized components must be finite within [0,1].")
    return normalized[list(weights)].mul(pd.Series(weights)).sum(axis=1) * config.CATEGORY_SCORE_SCALE


def score_categories(components):
    scores = components.loc[components.score_eligible].copy()
    for name in config.CATEGORY_WEIGHTS:
        scores[f"normalized_{name}"] = rank_normalize(scores[name])
        scores[f"missing_{name}"] = scores[name].isna()
    normalized = scores[[f"normalized_{name}" for name in config.CATEGORY_WEIGHTS]].rename(columns=lambda name: name.removeprefix("normalized_"))
    scores["score"] = weighted_scores(normalized, config.CATEGORY_WEIGHTS)
    scores = scores.sort_values(["score", "COMMODITY_DESC"], ascending=[False, True]).reset_index(drop=True)
    scores["rank"] = np.arange(1, len(scores) + 1)
    scores["label"] = np.where(scores["rank"].le(config.CATEGORY_LABEL_TOP_N), "Higher composite score", "Other scored category")
    return scores


def weight_sensitivity(scores):
    normalized = scores[[f"normalized_{name}" for name in config.CATEGORY_WEIGHTS]].rename(columns=lambda name: name.removeprefix("normalized_"))
    rng = np.random.default_rng(config.RANDOM_STATE)
    base_weights = np.array(list(config.CATEGORY_WEIGHTS.values()))
    baseline_ranks = scores.score.rank(method="average", ascending=False)
    top = scores["rank"].le(config.CATEGORY_DISPLAY_N)
    baseline_set = set(scores.loc[top, "COMMODITY_DESC"])
    runs, ranks = [], []
    for run in range(config.CATEGORY_SENSITIVITY_RUNS):
        perturbed = base_weights * rng.uniform(1 - config.CATEGORY_WEIGHT_PERTURBATION, 1 + config.CATEGORY_WEIGHT_PERTURBATION, len(base_weights))
        perturbed /= perturbed.sum()
        weights = dict(zip(config.CATEGORY_WEIGHTS, perturbed))
        values = weighted_scores(normalized, weights)
        order = pd.DataFrame({"score": values, "COMMODITY_DESC": scores.COMMODITY_DESC}).sort_values(["score", "COMMODITY_DESC"], ascending=[False, True])
        ordinal = pd.Series(np.arange(1, len(scores) + 1), index=order.index).reindex(scores.index)
        ranks.append(ordinal.to_numpy())
        changed_ranks = values.rank(method="average", ascending=False)
        changed_set = set(order.head(config.CATEGORY_DISPLAY_N).COMMODITY_DESC)
        runs.append({"run": run + 1, "spearman_all": float(baseline_ranks.corr(changed_ranks)),
                     "spearman_baseline_top20": float(baseline_ranks[top].corr(changed_ranks[top])),
                     "top20_overlap_share": len(baseline_set & changed_set) / len(baseline_set),
                     **{f"weight_{name}": float(value) for name, value in weights.items()}})
    matrix = np.asarray(ranks)
    ranges = pd.DataFrame({"COMMODITY_DESC": scores.COMMODITY_DESC, "base_rank": scores["rank"],
                          "minimum_rank": matrix.min(axis=0), "median_rank": np.median(matrix, axis=0),
                          "maximum_rank": matrix.max(axis=0)})
    return pd.DataFrame(runs), ranges

