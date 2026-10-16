"""Review III descriptive values, with consistent scope and explicit metric definitions."""
import math
import pandas as pd
from src import config


def calculate_values(data, rfm, scores, profiles, panel, forecast, master, readiness):
    if data.empty or not data.IN_SCOPE.all() or not config.in_analysis_window(data).all():
        raise ValueError("Review metrics require only approved analysis-window transactions.")
    revenue = float(data.SALES_VALUE.sum())
    households = int(data.household_key.nunique())
    baskets = int(data.BASKET_ID.nunique())
    if revenue <= 0 or households <= 0 or baskets <= 0:
        raise ValueError("Review denominators must be positive.")
    if not rfm.household_key.is_unique or set(rfm.household_key) != set(data.household_key):
        raise ValueError("Saved RFM households do not match the analysis snapshot.")
    departments = data.groupby("DEPARTMENT").SALES_VALUE.sum().sort_values(ascending=False)
    complete = data.loc[data.IS_COMPLETE_WEEK].groupby("WEEK_NO").SALES_VALUE.sum().sort_index()
    if len(complete) < 2 or complete.index.tolist() != list(range(int(complete.index.min()), int(complete.index.max()) + 1)):
        raise ValueError("Complete-week review trend is missing or gapped.")
    split = len(complete) // 2
    first_mean, second_mean = float(complete.iloc[:split].mean()), float(complete.iloc[split:].mean())
    discounted = data[["RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC"]].lt(0).any(axis=1)
    if not (discounted == (data.HAS_LOYALTY_DISC | data.HAS_COUPON)).all():
        raise ValueError("Prepared discount flags disagree with source-column semantics.")
    rules = rfm.groupby("rule_segment").agg(households=("household_key", "nunique"),
        revenue=("revenue", "sum"), mean_window_spend=("revenue", "mean")).reset_index()
    rules["revenue_share_pct"] = rules.revenue / revenue * 100
    rules["household_share_pct"] = rules.households / households * 100
    expected = set(config.REVIEW3_RULE_ORDER)
    if set(rules.rule_segment) != expected or not math.isclose(float(rules.revenue.sum()), revenue, abs_tol=config.REVENUE_TOLERANCE_USD, rel_tol=0):
        raise ValueError("Current four-rule baseline changed; review the presentation mapping.")
    rule_records = {row["rule_segment"]: row for row in rules.to_dict("records")}
    top_rule = rules.sort_values(["revenue", "rule_segment"], ascending=[False, True]).iloc[0]
    model_groups = profiles.copy()
    model_groups["mean_window_spend"] = model_groups.revenue / model_groups.households
    cohort = scores.sort_values("rank").head(config.REVIEW3_TOP_CATEGORY_COUNT)
    horizon = config.REVIEW3_METRIC_HORIZON
    h_metrics = {row["model"]: row for row in forecast["overall_metrics"] if row["horizon"] == horizon}
    train = panel.loc[panel.target_week.le(forecast["schedule"]["evaluation_training_cutoff"]) & panel.actual_revenue.notna()]
    starts = {str(h): int(rows.target_week.min()) for h, rows in train.groupby("horizon")}
    return {
        "revenue_usd": revenue, "baskets": baskets, "households": households,
        "average_basket_value_usd": revenue / baskets, "mean_baskets_per_household": baskets / households,
        "analysis_rows": len(data), "retained_master_rows": master["retained_transaction_lines"],
        "removed_joint_zero_rows": master["removed_zero_quantity_and_zero_sales_lines"],
        "raw_households": master["households_in_retained_unscoped_data"],
        "start_week": int(data.WEEK_NO.min()), "end_week": int(data.WEEK_NO.max()),
        "first_complete_week": int(complete.index.min()), "last_complete_week": int(complete.index.max()),
        "complete_weeks": len(complete), "weekly_mean_revenue_usd": float(complete.mean()),
        "peak_week": int(complete.idxmax()), "peak_week_revenue_usd": float(complete.max()),
        "first_half_weeks": [int(complete.index[0]), int(complete.index[split - 1])],
        "second_half_weeks": [int(complete.index[split]), int(complete.index[-1])],
        "first_half_mean_revenue_usd": first_mean, "second_half_mean_revenue_usd": second_mean,
        "second_half_mean_change_pct": (second_mean / first_mean - 1) * 100,
        "top_departments": [{"department": str(name), "revenue_usd": float(value)} for name, value in departments.head(config.REVIEW3_TOP_DEPARTMENT_COUNT).items()],
        "top_departments_revenue_share_pct": float(departments.head(config.REVIEW3_TOP_DEPARTMENT_COUNT).sum() / revenue * 100),
        "discounted_line_revenue_usd": float(data.loc[discounted, "SALES_VALUE"].sum()),
        "discounted_sales_share_pct": float(data.loc[discounted, "SALES_VALUE"].sum() / revenue * 100),
        "discounted_transaction_lines": int(discounted.sum()),
        "discount_definition": "Any negative RETAIL_DISC, COUPON_DISC or COUPON_MATCH_DISC; share of recorded SALES_VALUE, not causal promotion lift",
        "chosen_k": len(profiles), "rfm_rule_groups": rule_records,
        "largest_rule_group": str(top_rule.rule_segment),
        "largest_rule_household_share_pct": float(top_rule.household_share_pct),
        "largest_rule_revenue_share_pct": float(top_rule.revenue_share_pct),
        "kmeans_groups": model_groups.to_dict("records"),
        "top_categories": cohort[["COMMODITY_DESC", "rank", "score"]].to_dict("records"),
        "metric_horizon": horizon, "horizon_metrics": h_metrics,
        "forecast_categories": forecast["forecastable_categories"],
        "training_label_first_week_by_horizon": starts, "evaluation_training_cutoff": forecast["schedule"]["evaluation_training_cutoff"],
        "test_start": forecast["schedule"]["test_start"], "test_end": forecast["schedule"]["test_end"],
        "four_week_metrics": {row["model"]: row for row in forecast["four_week_total_metrics"]},
        "local_url": f"http://{config.LOCAL_SERVER_HOST}:{config.LOCAL_SERVER_PORT}",
        "verification": readiness["verification"],
        "note": "Four RFM rule groups are not four K-Means clusters. Mean spend is total selected-window revenue per household. No original unimplemented ARIMA or campaign-effect number is assumed."
    }
