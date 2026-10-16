"""Independent arithmetic, promotion safeguards, ranking and sensitivity verification."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.category_access import load_category_report
from src.data_access import load_analysis_transactions, load_validated_aggregate


def main():
    report = load_category_report(require_validation=False)
    window = load_analysis_transactions()
    components = pd.read_parquet(config.PROCESSED_DIR / "category_components.parquet").set_index("COMMODITY_DESC").sort_index()
    scores = pd.read_parquet(config.PROCESSED_DIR / "product_scores.parquet")
    promo = pd.read_parquet(config.PROCESSED_DIR / "promo_lift.parquet").set_index("COMMODITY_DESC")
    weekly = load_validated_aggregate("commodity_weekly")
    weekly = weekly.loc[weekly.in_window]
    daily = load_validated_aggregate("commodity_daily")
    daily = daily.loc[daily.in_window]
    exposure = pd.read_parquet(config.PROCESSED_DIR / "promo_category_weekly.parquet")
    checks = []
    assert components.index.is_unique and scores.COMMODITY_DESC.is_unique
    direct = window.groupby("COMMODITY_DESC").agg(revenue=("SALES_VALUE", "sum"), buyers=("household_key", "nunique"), baskets=("BASKET_ID", "nunique"))
    assert components.index.equals(direct.index)
    for name in direct:
        assert np.allclose(components[name], direct[name])
    repeated = window[["COMMODITY_DESC", "household_key", "WEEK_NO"]].drop_duplicates().groupby(["COMMODITY_DESC", "household_key"]).size()
    repeat_buyers = repeated.gt(1).groupby(level=0).sum()
    assert np.array_equal(components.repeat_buyers, repeat_buyers)
    assert np.allclose(components.repeat_purchase_rate, repeat_buyers / direct.buyers)
    assert np.allclose(components.household_penetration, direct.buyers / window.household_key.nunique())
    assert np.allclose(components.revenue_share, direct.revenue / window.SALES_VALUE.sum())
    assert np.allclose(components.revenue_per_buyer, direct.revenue / direct.buyers)
    assert np.isclose(components.revenue.sum(), report["revenue"], rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    eligible_categories = direct.sort_values(["revenue", "COMMODITY_DESC"], ascending=[False, True]).head(config.CATEGORY_TOP_N).index
    assert set(scores.COMMODITY_DESC) == set(eligible_categories)
    weeks = sorted(weekly.WEEK_NO.unique())
    split = len(weeks) // 2
    first = weekly.loc[weekly.WEEK_NO.isin(weeks[:split])].groupby("COMMODITY_DESC").revenue.sum() / split
    second = weekly.loc[weekly.WEEK_NO.isin(weeks[split:])].groupby("COMMODITY_DESC").revenue.sum() / (len(weeks) - split)
    assert np.allclose(components.first_half_weekly_revenue, first.reindex(components.index))
    assert np.allclose(components.second_half_weekly_revenue, second.reindex(components.index))
    expected_growth = second / first.replace(0, np.nan) - 1
    assert np.allclose(components.loc[eligible_categories, "growth"], expected_growth.loc[eligible_categories], equal_nan=True)
    assert components.loc[~components.index.isin(eligible_categories), "growth"].isna().all()
    # Independently build complete paired synthetic months from daily dates.
    date_days = pd.to_datetime(daily.DATE)
    grouped = daily.assign(year=date_days.dt.year, month=date_days.dt.month).groupby(["COMMODITY_DESC", "year", "month"])
    calendars = {}
    for (cat, year, month), g in grouped:
        if g.DAY.nunique() == pd.Timestamp(year=year, month=month, day=1).days_in_month:
            calendars.setdefault(cat, {})[(year, month)] = (g.revenue.sum(), g.DAY.nunique())
    for category, row in components.iterrows():
        calendar = calendars.get(category, {})
        years = sorted({year for year, _ in calendar})
        pairs = [month for month in range(1, 13) if len(years) == 2 and all((year, month) in calendar for year in years)]
        expected = np.nan
        if len(pairs) >= config.CATEGORY_YOY_MIN_MONTH_PAIRS:
            a = sum(calendar[(years[0], month)][0] for month in pairs) / sum(calendar[(years[0], month)][1] for month in pairs)
            b = sum(calendar[(years[1], month)][0] for month in pairs) / sum(calendar[(years[1], month)][1] for month in pairs)
            expected = b / a - 1 if a > 0 else np.nan
        assert row.yoy_month_pairs == len(pairs) and np.isclose(row.yoy_growth, expected, equal_nan=True)
        assert row.growth_sign_disagrees_yoy == (pd.notna(row.growth) and pd.notna(expected) and ((row.growth > 0) != (expected > 0)))
    checks.append("Revenue, distinct buyers/baskets, repeat weeks, penetration, half-week rates and paired complete-month YoY reconcile")

    joined = weekly.merge(exposure, on=["COMMODITY_DESC", "WEEK_NO"], validate="one_to_one")
    for category, g in joined.groupby("COMMODITY_DESC"):
        row = promo.loc[category]
        cv = g.revenue.std(ddof=0) / g.revenue.mean() if g.revenue.mean() > 0 else np.inf
        stable = g.revenue.gt(0).mean() >= config.FORECASTABLE_WEEK_SHARE and cv <= config.PROMO_MAX_REVENUE_CV
        known = g.coverage_share.ge(config.PROMO_MIN_COVERAGE) & g.matched_keys.ge(config.PROMO_MIN_MATCHED_KEYS)
        assert np.isclose(row.weekly_revenue_cv, cv)
        assert row.stable_revenue == stable and row.usable_exposure_weeks == known.sum()
        for label in ["display", "mailer", "any_promo", "promotion"]:
            share = g.any_promo_share if label == "promotion" else g[label + "_share"]
            boundary = share[known].median() if label == "promotion" else 0
            high = known & share.gt(boundary)
            low = known & (share.le(boundary) if label == "promotion" else share.eq(0))
            if label == "promotion":
                assert row.higher_exposure_weeks == high.sum() and row.lower_exposure_weeks == low.sum()
                raw_field, shrunk_field, reason_field = "promotion_association_raw", "promotion_association", "promotion_reason"
            else:
                assert row[label + "_with_weeks"] == high.sum() and row[label + "_without_weeks"] == low.sum()
                raw_field, shrunk_field, reason_field = label + "_association_raw", label + "_association_shrunk", label + "_reason"
            support = min(int(high.sum()), int(low.sum()))
            reason = "eligible"
            if not stable:
                reason = "unstable weekly revenue"
            elif support < config.PROMO_MIN_GROUP_WEEKS:
                reason = "insufficient comparator weeks"
            elif g.loc[low, "revenue"].mean() <= 0:
                reason = "zero comparator revenue"
            assert row[reason_field] == reason
            raw = g.loc[high, "revenue"].mean() / g.loc[low, "revenue"].mean() - 1 if reason == "eligible" else np.nan
            shrunk = raw * support / (support + config.PROMO_SHRINK_WEEKS)
            assert np.isclose(row[raw_field], raw, equal_nan=True)
            assert np.isclose(row[shrunk_field], shrunk, equal_nan=True)
    assert np.allclose(components.promotion_association, promo.loc[components.index, "promotion_association"], equal_nan=True)
    checks.append("Coverage, comparator support, revenue seasonality guards and sample shrinkage independently reproduce all promotion diagnostics")

    assert np.isclose(sum(config.CATEGORY_WEIGHTS.values()), 1)
    score_sum = np.zeros(len(scores))
    for name, weight in config.CATEGORY_WEIGHTS.items():
        known = scores[name].dropna()
        expected = pd.Series(config.CATEGORY_NEUTRAL_COMPONENT, index=scores.index)
        if len(known) > 1 and known.nunique() > 1:
            expected.loc[known.index] = (known.rank(method="average") - 1) / (len(known) - 1)
        assert np.allclose(scores["normalized_" + name], expected)
        assert np.array_equal(scores["missing_" + name], scores[name].isna())
        score_sum += expected.to_numpy() * weight * config.CATEGORY_SCORE_SCALE
    assert np.allclose(scores.score, score_sum)
    assert np.array_equal(scores["rank"], np.arange(1, len(scores) + 1))
    assert scores.equals(scores.sort_values(["score", "COMMODITY_DESC"], ascending=[False, True]).reset_index(drop=True))
    checks.append("Scoring cohort, tied percentile ranks, neutral missingness, weighted scores and deterministic ordering reproduce")
    sensitivity = pd.read_csv(config.OUTPUTS_DIR / "category_weight_sensitivity.csv")
    ranges = pd.read_csv(config.OUTPUTS_DIR / "category_rank_ranges.csv").set_index("COMMODITY_DESC").loc[scores.COMMODITY_DESC]
    assert len(sensitivity) == config.CATEGORY_SENSITIVITY_RUNS
    rng = np.random.default_rng(config.RANDOM_STATE)
    all_ranks, rhos, top_rhos, overlaps = [], [], [], []
    base_rank = scores.score.rank(method="average", ascending=False)
    top = scores["rank"].le(config.CATEGORY_DISPLAY_N)
    base_set = set(scores.loc[top, "COMMODITY_DESC"])
    for _, run in sensitivity.iterrows():
        expected_weights = np.array(list(config.CATEGORY_WEIGHTS.values())) * rng.uniform(1-config.CATEGORY_WEIGHT_PERTURBATION, 1+config.CATEGORY_WEIGHT_PERTURBATION, len(config.CATEGORY_WEIGHTS))
        expected_weights /= expected_weights.sum()
        actual_weights = [run["weight_" + name] for name in config.CATEGORY_WEIGHTS]
        assert np.allclose(expected_weights, actual_weights)
        values = sum(scores["normalized_" + name] * weight for name, weight in zip(config.CATEGORY_WEIGHTS, actual_weights))
        changed_ranks = values.rank(method="average", ascending=False)
        order = pd.DataFrame({"value": values, "category": scores.COMMODITY_DESC}).sort_values(["value", "category"], ascending=[False, True])
        ranks = pd.Series(np.arange(1, len(scores)+1), index=order.index).reindex(scores.index)
        all_ranks.append(ranks.to_numpy())
        rho, top_rho = base_rank.corr(changed_ranks), base_rank[top].corr(changed_ranks[top])
        overlap = len(base_set & set(order.head(config.CATEGORY_DISPLAY_N).category)) / len(base_set)
        assert np.isclose(run.spearman_all, rho) and np.isclose(run.spearman_baseline_top20, top_rho)
        assert np.isclose(run.top20_overlap_share, overlap)
        rhos.append(rho); top_rhos.append(top_rho); overlaps.append(overlap)
    matrix = np.array(all_ranks)
    assert np.array_equal(ranges.minimum_rank, matrix.min(axis=0))
    assert np.allclose(ranges.median_rank, np.median(matrix, axis=0))
    assert np.array_equal(ranges.maximum_rank, matrix.max(axis=0))
    for label, values in [("spearman_all", rhos), ("spearman_baseline_top20", top_rhos), ("top20_overlap", overlaps)]:
        assert np.isclose(report["sensitivity"][label+"_min"], np.min(values))
        assert np.isclose(report["sensitivity"][label+"_median"], np.median(values))
    assert report["sensitivity"]["engineering_stability_gate_passed"] == (min(rhos) >= config.CATEGORY_MIN_SPEARMAN and min(overlaps) >= config.CATEGORY_MIN_TOP20_OVERLAP)
    checks.append("All seeded weight perturbations, Spearman correlations, top-20 membership and category rank ranges reproduce")
    write_json(config.CATEGORY_VALIDATION_FILE, {"status": "PASS", "checks": checks,
               "build_report_sha256": file_fingerprint(config.CATEGORY_BUILD_FILE)["sha256"],
               "scored_categories": len(scores), "sensitivity": report["sensitivity"],
               "business_usefulness_review_complete": False})
    print("PASS: independent category intelligence validation", flush=True)


if __name__ == "__main__":
    main()

