"""Structured analytics tools. All revenue uses SALES_VALUE in USD."""
import math
from numbers import Integral
import numpy as np
import pandas as pd
from src import config
from src.scope import require_final_scope
from src.config import (
    CATEGORY_ALIASES, CLUSTER_K_VALUES, CURRENCY, DAYS_PER_WEEK,
    FORECAST_HOLDOUT, FORECAST_HORIZON, FORECAST_MIN_WEEKS,
    KMEANS_N_INIT, MIN_CLUSTER_SHARE, MOVING_AVERAGE_WEEKS,
    RANDOM_STATE, REVENUE_COLUMN, SEASONAL_PERIOD,
    SILHOUETTE_SAMPLE_SIZE, TOP_PRODUCTS, TRANSACTION_FILE,
)


def scope_transactions(data, start_week, end_week):
    if not all(isinstance(week, Integral) and not isinstance(week, bool) for week in (start_week, end_week)):
        raise ValueError("Week bounds must be integers.")
    if start_week > end_week:
        raise ValueError("Start week must not exceed end week.")
    if data.empty:
        raise ValueError("No transactions are available.")
    require_final_scope(data)
    data = data.loc[data.IN_SCOPE & config.in_analysis_window(data)]
    if data.empty:
        raise ValueError("No in-scope transactions remain within the analysis window.")
    if start_week < data.WEEK_NO.min() or end_week > data.WEEK_NO.max():
        raise ValueError("Week bounds must be within the source data range.")
    scoped = data.loc[data.WEEK_NO.between(start_week, end_week)]
    if scoped.empty:
        raise ValueError("No transactions match the selected weeks.")
    return scoped


def metadata(start_week, end_week):
    return {
        "currency": CURRENCY,
        "source_table": config.MASTER_FILE.name,
        "scope": f"IN_SCOPE=True; analysis-window transaction lines in weeks {start_week} through {end_week}, inclusive",
        "start_week": int(start_week), "end_week": int(end_week),
        "revenue_definition": "Sum of SALES_VALUE; no additional discount adjustment",
        "result_status": "Exploratory processed-data calculation; Review 3 field mapping pending",
    }


def query_sales_kpis(data, start_week, end_week):
    scoped = scope_transactions(data, start_week, end_week)
    revenue = float(scoped[REVENUE_COLUMN].sum())
    baskets = int(scoped.BASKET_ID.nunique())
    if not math.isfinite(revenue) or baskets == 0:
        raise ValueError("Revenue or basket count is invalid.")
    return {
        **metadata(start_week, end_week),
        "revenue": revenue, "baskets": baskets,
        "households": int(scoped.household_key.nunique()),
        "average_basket_value": revenue / baskets,
        "transaction_lines": int(len(scoped)),
        "anomalies": {
            "negative_sales_lines": int((scoped[REVENUE_COLUMN] < 0).sum()),
            "zero_sales_lines": int((scoped[REVENUE_COLUMN] == 0).sum()),
            "nonpositive_quantity_lines": int((scoped.QUANTITY <= 0).sum()),
            "basket_ids_with_multiple_households": int((scoped.groupby("BASKET_ID").household_key.nunique() > 1).sum()),
        },
    }


def get_sales_trend(data, start_week, end_week):
    scoped = scope_transactions(data, start_week, end_week)
    weekly = scoped.groupby("WEEK_NO").agg(revenue=(REVENUE_COLUMN, "sum"), baskets=("BASKET_ID", "nunique"), first_day=("DAY", "min"), last_day=("DAY", "max")).reset_index()
    weekly["observed_day_span"] = weekly.last_day - weekly.first_day + 1
    return {**metadata(start_week, end_week), "rows": weekly.to_dict("records"),
            "revenue": float(scoped[REVENUE_COLUMN].sum()),
            "note": "Only observed weeks are shown. Edge weeks may be partial; missing weeks are not imputed. DAY is a dataset day index, not a calendar date."}


def get_product_performance(data, products, start_week, end_week):
    scoped = scope_transactions(data, start_week, end_week)
    summary = scoped.groupby("PRODUCT_ID").agg(revenue=(REVENUE_COLUMN, "sum"), quantity=("QUANTITY", "sum"), households=("household_key", "nunique")).reset_index()
    summary = summary.merge(products, on="PRODUCT_ID", how="left", validate="one_to_one")
    if summary.COMMODITY_DESC.isna().any():
        raise ValueError("Some transaction products have no lookup entry; product analysis needs reconciliation.")
    summary = summary.sort_values(["revenue", "PRODUCT_ID"], ascending=[False, True]).head(TOP_PRODUCTS)
    return {**metadata(start_week, end_week), "rows": summary.to_dict("records"),
            "source_table": "transactions_master.parquet + product_lookup.parquet", "products_shown": int(len(summary)),
            "note": "Products ranked by SALES_VALUE. Lookup supplies commodity descriptions rather than consumer product names."}


def _get_customer_segments_for_period(data, start_week, end_week):
    # Imports are local so basic analytics do not depend on ML startup.
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler
    from threadpoolctl import threadpool_limits

    scoped = scope_transactions(data, start_week, end_week)
    customers = scoped.groupby("household_key").agg(first_day=("DAY", "min"), last_day=("DAY", "max"), baskets=("BASKET_ID", "nunique"), revenue=(REVENUE_COLUMN, "sum")).reset_index()
    if len(customers) < 4 or (customers.revenue < 0).any():
        raise ValueError("Segmentation needs at least four households and nonnegative household revenue; records were not removed.")
    reference_day = int(scoped.DAY.max())
    customers["recency_days"] = reference_day - customers.last_day
    observed_weeks = (reference_day - customers.first_day + 1) / DAYS_PER_WEEK
    customers["baskets_per_week"] = customers.baskets / observed_weeks
    customers["revenue_per_week"] = customers.revenue / observed_weeks
    features = ["recency_days", "baskets_per_week", "revenue_per_week"]
    scaled = StandardScaler().fit_transform(np.log1p(customers[features]))
    unique_points = len(np.unique(scaled, axis=0))
    evaluation = []
    best = None
    minimum_size = max(2, math.ceil(len(customers) * MIN_CLUSTER_SHARE))
    with threadpool_limits(limits=1):
        for k in CLUSTER_K_VALUES:
            if k >= len(customers) or k > unique_points:
                continue
            model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=KMEANS_N_INIT)
            labels = model.fit_predict(scaled)
            counts = np.bincount(labels, minlength=k)
            score = float(silhouette_score(scaled, labels, sample_size=min(len(customers), SILHOUETTE_SAMPLE_SIZE), random_state=RANDOM_STATE))
            eligible = bool(counts.min() >= minimum_size)
            evaluation.append({"k": k, "inertia": float(model.inertia_), "silhouette": score, "minimum_cluster_size": int(counts.min()), "eligible": eligible})
            if eligible and (best is None or score > best[0]):
                best = (score, k, labels)
    if best is None:
        raise ValueError("No eligible cluster split was found; segmentation needs review rather than forced labels.")
    customers["segment"] = best[2] + 1
    profiles = customers.groupby("segment").agg(households=("household_key", "size"), revenue=("revenue", "sum"), mean_recency_days=("recency_days", "mean"), mean_baskets_per_week=("baskets_per_week", "mean"), mean_revenue_per_week=("revenue_per_week", "mean")).reset_index()
    return {**metadata(start_week, end_week), "rows": profiles.to_dict("records"),
            "evaluation": evaluation, "chosen_k": best[1], "silhouette": best[0],
            "households": int(len(customers)), "revenue": float(customers.revenue.sum()),
            "reference_day": reference_day,
            "method": "K-Means on log1p RFM features, StandardScaler, seed 42; highest silhouette among minimum-size-eligible candidates",
            "note": "Exploratory divisions of a customer continuum. Recency is measured from the last selected day (lower is more recent). Rates use each household's first observed purchase through that day, not known customer tenure. Silhouette is sampled at up to 1,000 households. Stability and business interpretation are pending; selected k is not a final validated result."}


def resolve_category(products, category):
    if not isinstance(category, str) or not category.strip():
        raise ValueError("Specify a commodity category for forecasting.")
    category = CATEGORY_ALIASES.get(category.strip().lower(), category.strip())
    values = sorted(products.COMMODITY_DESC.unique())
    exact = [value for value in values if value.lower() == category.lower()]
    if exact:
        return exact[0]
    matches = [value for value in values if category.lower() in value.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError("Category is ambiguous. Use an exact commodity: " + "; ".join(matches))
    raise ValueError(f"No matching commodity category: {category}")


def forecast_metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    errors = actual - predicted
    nonzero = actual != 0
    denominator = float(np.abs(actual).sum())
    return {
        "MAE": float(np.abs(errors).mean()),
        "RMSE": float(np.sqrt(np.square(errors).mean())),
        "MAPE_pct": float((np.abs(errors[nonzero] / actual[nonzero])).mean() * 100) if nonzero.any() else None,
        "WAPE_pct": float(np.abs(errors).sum() / denominator * 100) if denominator else None,
        "MAPE_nonzero_weeks": int(nonzero.sum()),
    }


def _forecast_baseline_for_period(data, products, start_week, end_week, category):
    scoped = scope_transactions(data, start_week, end_week)
    commodity = resolve_category(products, category)
    # Determine complete-week candidates using ALL in-scope transactions, not category purchase frequency.
    spans = scoped.groupby("WEEK_NO").DAY.agg(["min", "max", "nunique"])
    complete = spans.loc[(spans["max"] - spans["min"] == DAYS_PER_WEEK - 1) & (spans["nunique"] == DAYS_PER_WEEK)].index.astype(int).tolist()
    if len(complete) < FORECAST_MIN_WEEKS:
        raise ValueError(f"Forecasting needs at least {FORECAST_MIN_WEEKS} observed complete weeks; choose a wider window.")
    if any(right - left != 1 for left, right in zip(complete, complete[1:])):
        raise ValueError("Complete-week history has gaps; investigate before forecasting.")
    product_ids = products.loc[products.COMMODITY_DESC == commodity, "PRODUCT_ID"]
    category_rows = scoped.loc[scoped.PRODUCT_ID.isin(product_ids)]
    if category_rows.empty:
        raise ValueError("No sales for this commodity in the selected window.")
    # With complete all-retail weeks, no category purchases is explicitly treated as zero revenue.
    weekly = category_rows.groupby("WEEK_NO")[REVENUE_COLUMN].sum().reindex(complete, fill_value=0).astype(float)
    if (weekly < 0).any():
        raise ValueError("Negative weekly category revenue needs review before forecasting; no records were removed.")
    values = weekly.tolist()
    cutoff = len(values) - FORECAST_HOLDOUT
    predictions = {"Naive": [], "Four-week moving average": []}
    seasonal_available = cutoff >= SEASONAL_PERIOD
    if seasonal_available:
        predictions["Seasonal naive (52 weeks)"] = []
    holdout_rows = []
    for index in range(cutoff, len(values)):
        # Rolling one-step evaluation: only observations earlier than this target week are available.
        naive = values[index - 1]
        moving = float(np.mean(values[index - MOVING_AVERAGE_WEEKS:index]))
        predictions["Naive"].append(naive)
        predictions["Four-week moving average"].append(moving)
        row = {"week": int(weekly.index[index]), "actual_revenue": values[index], "naive": naive, "moving_average": moving}
        if seasonal_available:
            seasonal = values[index - SEASONAL_PERIOD]
            predictions["Seasonal naive (52 weeks)"].append(seasonal)
            row["seasonal_naive"] = seasonal
        holdout_rows.append(row)
    actual = values[cutoff:]
    evaluation = [{"model": name, **forecast_metrics(actual, predicted)} for name, predicted in predictions.items()]
    history = values.copy()
    future_rows = []
    origin_week = int(weekly.index[-1])
    for step in range(1, FORECAST_HORIZON + 1):
        forecast = float(np.mean(history[-MOVING_AVERAGE_WEEKS:]))
        history.append(forecast)
        future_rows.append({"week": origin_week + step, "forecast_revenue": forecast})
    excluded = [int(week) for week in sorted(set(scoped.WEEK_NO.astype(int).unique()) - set(complete))]
    return {**metadata(start_week, end_week), "source_table": "transactions_master.parquet + product_lookup.parquet",
            "scope": f"Commodity {commodity}; complete observed weeks {complete[0]} through {complete[-1]} within selected weeks {start_week} through {end_week}",
            "rows": future_rows, "history": [{"week": int(week), "revenue": float(value)} for week, value in weekly.items()],
            "evaluation": evaluation, "holdout": holdout_rows,
            "category": commodity, "origin_week": origin_week, "forecast_horizon": FORECAST_HORIZON,
            "forecast_total": float(sum(row["forecast_revenue"] for row in future_rows)),
            "model": "Recursive four-week moving average baseline (not a trained ML forecasting model)",
            "excluded_partial_weeks": excluded,
            "note": "Target is weekly revenue in USD, not units. Four dataset weeks are a next-month proxy, not a calendar month. Last 12 complete weeks are evaluated with rolling one-step predictions; these metrics do not measure four-step forecast accuracy. Complete weeks require seven observed day indices; source coverage is not independently certified. Category weeks without purchases are treated as zero. Forecast starts after the last complete week and may overlap a partial source week. Seasonal baseline unavailable unless training history spans 52 weeks.",
            "seasonal_baseline_available": seasonal_available}




def get_customer_segments(data, start_week, end_week):
    """Use validated saved profiles for the full approved window; refit explicit subperiods."""
    scoped = scope_transactions(data, start_week, end_week)
    if config.SEGMENT_BUILD_FILE.is_file() and "SOURCE_ROW_ID" in scoped and start_week == config.ANALYSIS_START_WEEK and end_week == int(config.ANALYSIS_END_WEEK or data.WEEK_NO.max()):
        from src.segment_access import saved_segment_result
        saved = saved_segment_result(scoped, start_week, end_week)
        if saved is not None:
            return saved
    result = _get_customer_segments_for_period(data, start_week, end_week)
    result["mode"] = "period_refit"
    result["note"] = "Recomputed exploratory clustering for the selected period; saved full-window models are not used. " + result["note"]
    return result



def get_category_intelligence(data, start_week, end_week):
    """Return only validated full-window category scores; never reinterpret a subset."""
    from src.category_access import category_result
    scoped = scope_transactions(data, start_week, end_week)
    return category_result(scoped, start_week, end_week)



def forecast_demand(data, products, start_week, end_week, category):
    """Use validated saved forecasts for the full real snapshot; label subperiod baselines."""
    scoped = scope_transactions(data, start_week, end_week)
    commodity = resolve_category(products, category)
    if config.FORECAST_BUILD_FILE.is_file() and "SOURCE_ROW_ID" in scoped and start_week == config.ANALYSIS_START_WEEK and end_week == int(config.ANALYSIS_END_WEEK or data.WEEK_NO.max()):
        from src.forecast_access import saved_forecast_result
        return saved_forecast_result(scoped, start_week, end_week, commodity)
    result = _forecast_baseline_for_period(data, products, start_week, end_week, category)
    result["mode"] = "period_baseline"
    result["note"] = "Recomputed baseline for this selected period; saved full-window trained forecasts are not used. " + result["note"]
    return result



def get_recommendations(data, start_week, end_week):
    """Show two validated, separate recommendation hypotheses for the full saved snapshot."""
    from src.recommendation_access import recommendation_result
    scoped = scope_transactions(data, start_week, end_week)
    return recommendation_result(scoped, start_week, end_week)



def get_week_diagnosis(data, start_week, end_week):
    """Serve only current validated diagnostic evidence for the full approved snapshot."""
    from src.diagnostic_access import diagnostic_result
    return diagnostic_result(scope_transactions(data,start_week,end_week),start_week,end_week)
