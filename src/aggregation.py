"""Build reconciled aggregates ONLY after an explicit FMCG scope is configured."""
import numpy as np
import pandas as pd
from src import config
from src.scope import require_final_scope


def build_aggregate_frames(master):
    require_final_scope(master)
    scoped = master.loc[master.IN_SCOPE].copy()
    if scoped.empty:
        raise ValueError("Configured scope contains no transactions.")
    categories = sorted(scoped.COMMODITY_DESC.astype("string").unique())
    first_date, last_date = master.DATE.min(), master.DATE.max()
    dates = pd.date_range(first_date, last_date, freq="D")
    day_grid = pd.MultiIndex.from_product([categories, dates], names=["COMMODITY_DESC", "DATE"])
    daily = scoped.groupby(["COMMODITY_DESC", "DATE"], observed=True).agg(revenue=("SALES_VALUE", "sum"), quantity=("QUANTITY", "sum"), baskets=("BASKET_ID", "nunique"), households=("household_key", "nunique"), transaction_lines=("SOURCE_ROW_ID", "size")).reindex(day_grid, fill_value=0).reset_index()
    anchor = pd.Timestamp(config.CALENDAR_DAY_ONE)
    daily["DAY"] = (daily.DATE - anchor).dt.days + 1
    daily["WEEK_NO"] = (daily.DAY - 1 + anchor.weekday()) // config.DAYS_PER_WEEK + 1
    daily["in_window"] = config.in_analysis_window(daily)
    full_weeks = sorted(master.loc[master.IS_COMPLETE_WEEK, "WEEK_NO"].unique())
    if not full_weeks:
        raise ValueError("No complete observed weeks are available.")
    full_scoped = scoped.loc[scoped.IS_COMPLETE_WEEK]
    week_grid = pd.MultiIndex.from_product([categories, full_weeks], names=["COMMODITY_DESC", "WEEK_NO"])
    weekly = full_scoped.groupby(["COMMODITY_DESC", "WEEK_NO"], observed=True).agg(revenue=("SALES_VALUE", "sum"), quantity=("QUANTITY", "sum"), baskets=("BASKET_ID", "nunique"), households=("household_key", "nunique"), transaction_lines=("SOURCE_ROW_ID", "size")).reindex(week_grid, fill_value=0).reset_index()
    weekly["in_window"] = config.in_analysis_window(weekly)
    window_weeks = weekly.loc[weekly.in_window, "WEEK_NO"].unique()
    if not len(window_weeks):
        raise ValueError("No full weeks remain within the configured analysis window.")
    activity = weekly.loc[weekly.in_window].assign(sold=lambda frame: frame.revenue.gt(0)).groupby("COMMODITY_DESC").sold.mean()
    weekly["window_week_sale_share"] = weekly.COMMODITY_DESC.map(activity)
    weekly["forecastable"] = weekly.window_week_sale_share.ge(config.FORECASTABLE_WEEK_SHARE)
    window = scoped.loc[config.in_analysis_window(scoped)]
    if window.empty:
        raise ValueError("No in-scope transactions remain in the analysis window.")
    # End-of-observation reference is the master calendar's last selected day, not a customer's last visit.
    reference_day = int(master.loc[config.in_analysis_window(master), "DAY"].max())
    households = window.groupby("household_key").agg(first_day=("DAY", "min"), last_day=("DAY", "max"), first_window_week=("WEEK_NO", "min"), baskets=("BASKET_ID", "nunique"), revenue=("SALES_VALUE", "sum"), transaction_lines=("SOURCE_ROW_ID", "size")).reset_index()
    households["recency_days"] = reference_day - households.last_day
    households["observed_weeks"] = (reference_day - households.first_day + 1) / config.DAYS_PER_WEEK
    households["baskets_per_week"] = households.baskets / households.observed_weeks
    households["revenue_per_week"] = households.revenue / households.observed_weeks
    revenue = float(window.SALES_VALUE.sum())
    baskets = int(window.BASKET_ID.nunique())
    kpis = {
        "revenue": revenue, "baskets": baskets,
        "households": int(window.household_key.nunique()),
        "average_basket_value": revenue / baskets,
        "median_household_revenue_per_week": float(households.revenue_per_week.median()),
        "transaction_lines": int(len(window)), "currency": config.CURRENCY,
        "source_table": "transactions_master.parquet",
        "scope": f"IN_SCOPE=True; weeks {config.ANALYSIS_START_WEEK} through {int(window.WEEK_NO.max())}; partial terminal week included for KPIs",
        "analysis_start_week": config.ANALYSIS_START_WEEK,
        "analysis_end_week": int(window.WEEK_NO.max()),
        "reference_day": reference_day,
        "status": "Calculated from explicitly scoped processed data; aggregate validation required",
        "note": "Observed-period household rates are not verified customer tenure. Basket and household counts across commodities are non-additive. Review 3 field mapping is not available yet.",
    }
    benchmarks = {
        "daily_all_in_scope_revenue": float(scoped.SALES_VALUE.sum()),
        "weekly_full_weeks_in_scope_revenue": float(full_scoped.SALES_VALUE.sum()),
        "window_in_scope_revenue": revenue,
        "window_full_weeks_in_scope_revenue": float(window.loc[window.IS_COMPLETE_WEEK, "SALES_VALUE"].sum()),
    }
    pairs = [(daily.revenue.sum(), benchmarks["daily_all_in_scope_revenue"]),
             (weekly.revenue.sum(), benchmarks["weekly_full_weeks_in_scope_revenue"]),
             (households.revenue.sum(), revenue)]
    if not all(np.isclose(actual, expected, rtol=0, atol=config.REVENUE_TOLERANCE_USD) for actual, expected in pairs):
        raise ValueError("Aggregate revenue does not match its specific source benchmark.")
    return daily, weekly, households, kpis, benchmarks

