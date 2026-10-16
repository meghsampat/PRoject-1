"""Calendar, cleaning and joins for the reproducible master table."""
import numpy as np
import pandas as pd
from src import config
from src.scope import apply_scope_policy, scope_pending_reasons

from src.config import RAW_TRANSACTION_COLUMNS, LOOKUP_COLUMNS



def prepare_master(raw, products, policy):
    """Keep unusual lines; remove ONLY lines where quantity AND sales are both zero."""
    if raw.empty or products.empty:
        raise ValueError("Raw transactions and product lookup must be nonempty.")
    if not set(RAW_TRANSACTION_COLUMNS).issubset(raw.columns) or not set(LOOKUP_COLUMNS).issubset(products.columns):
        raise ValueError("A source is missing required columns.")
    if raw[RAW_TRANSACTION_COLUMNS].isna().any().any() or products[LOOKUP_COLUMNS].isna().any().any():
        raise ValueError("Required source fields have missing values; investigate before building.")
    for column in RAW_TRANSACTION_COLUMNS:
        if not pd.api.types.is_numeric_dtype(raw[column]) or not np.isfinite(raw[column]).all():
            raise ValueError(f"Raw field {column} must be numeric and finite.")
    for column in ["household_key", "BASKET_ID", "DAY", "PRODUCT_ID", "STORE_ID", "WEEK_NO"]:
        if (raw[column] % 1 != 0).any():
            raise ValueError(f"Raw field {column} must contain integer values.")
    if products.PRODUCT_ID.duplicated().any():
        raise ValueError("Duplicate lookup product IDs would multiply transaction rows.")
    if (raw.DAY < 1).any():
        raise ValueError("Dataset DAY indices must start at one or later.")
    anchor = pd.Timestamp(policy["calendar_day_one"])
    derived_week = ((raw.DAY - 1 + anchor.weekday()) // config.DAYS_PER_WEEK + 1).astype(int)
    mismatches = int((derived_week != raw.WEEK_NO).sum())
    if mismatches:
        raise ValueError(f"Synthetic calendar does not match source WEEK_NO: {mismatches} line mismatches.")
    raw = raw.copy()
    raw["SOURCE_ROW_ID"] = np.arange(len(raw), dtype=np.int64)
    removed_mask = raw.QUANTITY.eq(0) & raw.SALES_VALUE.eq(0)
    removed = raw.loc[removed_mask].copy()
    retained = raw.loc[~removed_mask].copy()
    raw_revenue = float(raw.SALES_VALUE.sum())
    lookup = products[LOOKUP_COLUMNS].copy()
    for column in LOOKUP_COLUMNS:
        if column != "PRODUCT_ID":
            lookup[column] = lookup[column].astype("category")
    master = retained.merge(lookup, on="PRODUCT_ID", how="left", validate="many_to_one", indicator="PRODUCT_JOIN_STATUS")
    if not master.PRODUCT_JOIN_STATUS.eq("both").all():
        raise ValueError("Some transactions lack a product lookup row; no unmatched transactions were deleted.")
    master = master.drop(columns="PRODUCT_JOIN_STATUS")
    if len(master) != len(retained) or not np.isclose(master.SALES_VALUE.sum(), retained.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD):
        raise ValueError("Product join changed transaction count or revenue.")
    master["DATE"] = anchor + pd.to_timedelta(master.DAY - 1, unit="D")
    master["IN_ANALYSIS_WINDOW"] = master.WEEK_NO.ge(policy["analysis_start_week"])
    if policy["analysis_end_week"] is not None:
        master["IN_ANALYSIS_WINDOW"] &= master.WEEK_NO.le(policy["analysis_end_week"])
    # Completeness uses the source extent and seven distinct observed day indices, not category sales.
    spans = raw.groupby("WEEK_NO").DAY.agg(["min", "max", "nunique"])
    full_weeks = spans.index[(spans["max"] - spans["min"] == config.DAYS_PER_WEEK - 1) & (spans["nunique"] == config.DAYS_PER_WEEK)]
    master["IS_COMPLETE_WEEK"] = master.WEEK_NO.isin(full_weeks)
    master["IS_FREE_ITEM"] = master.QUANTITY.gt(0) & master.SALES_VALUE.eq(0)
    master["HAS_LOYALTY_DISC"] = master.RETAIL_DISC.lt(0)
    master["HAS_COUPON"] = master.COUPON_DISC.lt(0) | master.COUPON_MATCH_DISC.lt(0)
    master["ZERO_QTY_NONZERO_SALES"] = master.QUANTITY.eq(0) & master.SALES_VALUE.ne(0)
    master["NEGATIVE_QUANTITY"] = master.QUANTITY.lt(0)
    master["NEGATIVE_SALES"] = master.SALES_VALUE.lt(0)
    master["POSITIVE_DISCOUNT_VALUE"] = master[["RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC"]].gt(0).any(axis=1)
    master["IN_SCOPE"], master["DRUG_GM_REVIEW"] = apply_scope_policy(master, policy, products)
    weighted_values = policy.get("weighted_commodities")
    if weighted_values is None:
        master["IS_WEIGHTED"] = pd.Series(pd.NA, index=master.index, dtype="boolean")
    else:
        from src.scope import normalize_names
        known = set(products.COMMODITY_DESC.astype("string").str.strip().str.upper())
        if set(normalize_names(weighted_values)) - known:
            raise ValueError("Weighted commodity rule contains unknown commodity names.")
        master["IS_WEIGHTED"] = master.COMMODITY_DESC.astype("string").str.strip().str.upper().isin(normalize_names(weighted_values)).astype("boolean")
    master["UNIT_PRICE_PAID"] = np.nan
    priceable = master.IN_SCOPE.fillna(False) & master.QUANTITY.gt(0)
    master.loc[priceable, "UNIT_PRICE_PAID"] = master.loc[priceable, "SALES_VALUE"] / master.loc[priceable, "QUANTITY"]
    flags = ["IS_FREE_ITEM", "HAS_LOYALTY_DISC", "HAS_COUPON", "ZERO_QTY_NONZERO_SALES", "NEGATIVE_QUANTITY", "NEGATIVE_SALES", "POSITIVE_DISCOUNT_VALUE"]
    report = {
        "status": "SCOPE_PENDING" if scope_pending_reasons(policy) else "SCOPE_CONFIGURED",
        "scope_pending": scope_pending_reasons(policy),
        "raw_transaction_lines": int(len(raw)), "retained_transaction_lines": int(len(master)),
        "removed_zero_quantity_and_zero_sales_lines": int(len(removed)),
        "raw_sales_value_usd": raw_revenue,
        "retained_unscoped_sales_value_usd": float(master.SALES_VALUE.sum()),
        "removed_sales_value_usd": float(removed.SALES_VALUE.sum()),
        "households_in_retained_unscoped_data": int(master.household_key.nunique()),
        "calendar_week_line_mismatches": mismatches,
        "source_day_min": int(raw.DAY.min()), "source_day_max": int(raw.DAY.max()),
        "calendar_first_date": str(master.DATE.min().date()), "calendar_last_date": str(master.DATE.max().date()),
        "calendar_note": "Synthetic anchor from user guide. These are not verified purchase dates or holiday labels.",
        "complete_week_min": int(min(full_weeks)) if len(full_weeks) else None,
        "complete_week_max": int(max(full_weeks)) if len(full_weeks) else None,
        "flag_counts": {flag: int(master[flag].sum()) for flag in flags},
        "weighted_flag_status": "UNKNOWN: verified classification rule missing" if weighted_values is None else "Configured commodity-level rule",
        "unit_price_note": "SALES_VALUE/QUANTITY only on positive-quantity in-scope lines, in native recorded quantity units. Physical unit-price interpretation is unverified.",
        "scope_policy": policy,
        "result_note": "Audit totals are unscoped source reconciliation, not final FMCG results or Review 3 values.",
    }
    return master, removed, report

