"""Promotion coverage and guarded observational comparisons; never causal lift."""
import numpy as np
import pandas as pd
from src import config

KEYS = ["PRODUCT_ID", "STORE_ID", "WEEK_NO"]


def summarize_matches(matches, grid):
    """One vote per observed sold product/store/week; absent records remain unknown."""
    data = matches.assign(matched=matches.source_records.gt(0))
    data["display_yes"] = data.display_mask.gt(1)
    data["mailer_yes"] = data.mailer_mask.gt(1)
    data["any_yes"] = data.display_yes | data.mailer_yes
    totals = data.groupby(["COMMODITY_DESC", "WEEK_NO"]).agg(
        sales_keys=("PRODUCT_ID", "size"), matched_keys=("matched", "sum"),
        display_keys=("display_yes", "sum"), mailer_keys=("mailer_yes", "sum"),
        any_promo_keys=("any_yes", "sum"))
    result = grid.merge(totals.reset_index(), how="left", on=["COMMODITY_DESC", "WEEK_NO"], validate="one_to_one")
    counts = ["sales_keys", "matched_keys", "display_keys", "mailer_keys", "any_promo_keys"]
    result[counts] = result[counts].fillna(0).astype("int64")
    result["coverage_share"] = result.matched_keys / result.sales_keys.replace(0, np.nan)
    for label, numerator in [("display", "display_keys"), ("mailer", "mailer_keys"), ("any_promo", "any_promo_keys")]:
        result[f"{label}_share"] = result[numerator] / result.matched_keys.replace(0, np.nan)
    return result


def guarded_contrast(revenue, high, low, stable):
    """Shrink a difference in weekly means by smaller-group sample support."""
    a, b = revenue[high], revenue[low]
    n = min(len(a), len(b))
    if not stable:
        return np.nan, np.nan, "unstable weekly revenue"
    if n < config.PROMO_MIN_GROUP_WEEKS:
        return np.nan, np.nan, "insufficient comparator weeks"
    if b.mean() <= 0:
        return np.nan, np.nan, "zero comparator revenue"
    raw = a.mean() / b.mean() - 1
    return float(raw), float(raw * n / (n + config.PROMO_SHRINK_WEEKS)), "eligible"


def promotion_diagnostics(weekly, exposure):
    joined = weekly.merge(exposure, on=["COMMODITY_DESC", "WEEK_NO"], validate="one_to_one")
    records = []
    for category, group in joined.groupby("COMMODITY_DESC", sort=True):
        group = group.sort_values("WEEK_NO")
        revenue = group.revenue
        cv = float(revenue.std(ddof=0) / revenue.mean()) if revenue.mean() > 0 else np.inf
        positive = float(revenue.gt(0).mean())
        stable = positive >= config.FORECASTABLE_WEEK_SHARE and cv <= config.PROMO_MAX_REVENUE_CV
        known = group.coverage_share.ge(config.PROMO_MIN_COVERAGE) & group.matched_keys.ge(config.PROMO_MIN_MATCHED_KEYS)
        row = {"COMMODITY_DESC": category, "weekly_revenue_cv": cv, "positive_week_share": positive,
               "stable_revenue": bool(stable), "usable_exposure_weeks": int(known.sum()),
               "sales_key_coverage": float(group.matched_keys.sum() / group.sales_keys.sum()) if group.sales_keys.sum() else np.nan}
        for label in ["display", "mailer", "any_promo"]:
            exposure_share = group[f"{label}_share"]
            high, low = known & exposure_share.gt(0), known & exposure_share.eq(0)
            raw, shrunk, reason = guarded_contrast(revenue, high, low, stable)
            row.update({f"{label}_with_weeks": int(high.sum()), f"{label}_without_weeks": int(low.sum()),
                        f"{label}_association_raw": raw, f"{label}_association_shrunk": shrunk,
                        f"{label}_reason": reason})
        # A separate diagnostic, clearly distinct from weeks with versus without.
        median = group.loc[known, "any_promo_share"].median()
        high = known & group.any_promo_share.gt(median)
        low = known & group.any_promo_share.le(median)
        raw, shrunk, reason = guarded_contrast(revenue, high, low, stable)
        row.update({"exposure_split_median": median, "higher_exposure_weeks": int(high.sum()),
                    "lower_exposure_weeks": int(low.sum()), "promotion_association_raw": raw,
                    "promotion_association": shrunk, "promotion_reason": reason})
        records.append(row)
    return pd.DataFrame(records)
