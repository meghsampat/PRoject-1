"""Origin-time features and chronological splits for direct weekly revenue forecasting."""
import hashlib
import json
import numpy as np
import pandas as pd
from src import config


def forecast_settings():
    names = ["FORECAST_HORIZON", "FORECAST_HOLDOUT", "FORECAST_MIN_WEEKS", "FORECASTABLE_WEEK_SHARE",
             "MOVING_AVERAGE_WEEKS", "SEASONAL_PERIOD", "RANDOM_STATE", "FORECAST_LAGS",
             "FORECAST_ROLLING_WINDOWS", "FORECAST_VALIDATION_FOLDS", "FORECAST_VALIDATION_WEEKS",
             "FORECAST_SCALE_FLOOR", "FORECAST_PARAMS", "FORECAST_FEATURES", "FORECAST_METHODS",
             "FORECAST_PROMO_MIN_COVERAGE", "FORECAST_PROMO_MIN_KEYS", "FORECAST_CALENDAR_MONTHS", "FORECAST_VOLATILITY_THRESHOLD"]
    return {name: getattr(config, name) for name in names}


def settings_fingerprint():
    return hashlib.sha256(json.dumps(forecast_settings(), sort_keys=True).encode()).hexdigest()


def split_schedule(weeks):
    weeks = sorted(int(week) for week in weeks)
    if len(weeks) < config.FORECAST_MIN_WEEKS + config.FORECAST_HOLDOUT + config.FORECAST_VALIDATION_FOLDS * config.FORECAST_VALIDATION_WEEKS:
        raise ValueError("Insufficient complete weeks for chronological training, validation and test.")
    if weeks != list(range(weeks[0], weeks[-1]+1)):
        raise ValueError("Weekly forecasting panel has gaps.")
    test_start = weeks[-config.FORECAST_HOLDOUT]
    validation_start = test_start - config.FORECAST_VALIDATION_FOLDS * config.FORECAST_VALIDATION_WEEKS
    folds = [{"fold": fold+1, "start": validation_start + fold*config.FORECAST_VALIDATION_WEEKS,
              "end": validation_start + (fold+1)*config.FORECAST_VALIDATION_WEEKS-1}
             for fold in range(config.FORECAST_VALIDATION_FOLDS)]
    return {"eligibility_cutoff": validation_start-1, "test_start": test_start,
            "test_end": weeks[-1], "evaluation_training_cutoff": test_start-1, "folds": folds}


def build_feature_panel(weekly, covariates):
    """At origin t, lag1 and all rolling summaries include completed week t."""
    weekly = weekly.sort_values(["COMMODITY_DESC", "WEEK_NO"]).reset_index(drop=True)
    if weekly.duplicated(["COMMODITY_DESC", "WEEK_NO"]).any() or weekly.revenue.isna().any() or not np.isfinite(weekly.revenue).all() or weekly.revenue.lt(0).any():
        raise ValueError("Invalid weekly keys/revenue; no source observations removed.")
    schedule = split_schedule(weekly.WEEK_NO.unique())
    initial = weekly.loc[weekly.WEEK_NO.le(schedule["eligibility_cutoff"])]
    activity = initial.groupby("COMMODITY_DESC").revenue.apply(lambda values: values.gt(0).mean())
    categories = sorted(activity.loc[activity.ge(config.FORECASTABLE_WEEK_SHARE)].index.tolist())
    if not categories:
        raise ValueError("No forecastable categories in the initial training window.")
    base = weekly.loc[weekly.COMMODITY_DESC.isin(categories)].merge(covariates, on=["COMMODITY_DESC", "WEEK_NO"], how="left", validate="one_to_one")
    group = base.groupby("COMMODITY_DESC", sort=False)
    means = {}
    for size in config.FORECAST_ROLLING_WINDOWS:
        means[size] = group.revenue.transform(lambda values: values.rolling(size, min_periods=size).mean())
    base["scale"] = means[max(config.FORECAST_ROLLING_WINDOWS)].clip(lower=config.FORECAST_SCALE_FLOOR)
    for lag in config.FORECAST_LAGS:
        base[f"revenue_lag{lag}"] = group.revenue.shift(lag-1) / base.scale
    for size in config.FORECAST_ROLLING_WINDOWS:
        base[f"rolling_mean{size}"] = means[size] / base.scale
        base[f"rolling_std{size}"] = group.revenue.transform(lambda values: values.rolling(size, min_periods=size).std(ddof=0)) / base.scale
    base["log_scale"] = np.log1p(base.scale)
    base["commodity_code"] = base.COMMODITY_DESC.map({name: index for index, name in enumerate(categories)})
    base["loyalty_lag1"] = base.loyalty_share
    usable = base.coverage_share.ge(config.FORECAST_PROMO_MIN_COVERAGE) & base.matched_keys.ge(config.FORECAST_PROMO_MIN_KEYS)
    base["display_lag1"] = base.display_share.where(usable)
    base["mailer_lag1"] = base.mailer_share.where(usable)
    base["promo_coverage"] = base.coverage_share
    base["promo_unknown"] = (~usable).astype(float)
    monday_one = pd.Timestamp(config.CALENDAR_DAY_ONE) - pd.Timedelta(days=pd.Timestamp(config.CALENDAR_DAY_ONE).weekday())
    records = []
    indexed = base.set_index(["COMMODITY_DESC", "WEEK_NO"]).revenue
    for horizon in range(1, config.FORECAST_HORIZON+1):
        frame = base.copy()
        frame["origin_week"] = frame.WEEK_NO.astype(int)
        frame["horizon"] = horizon
        frame["target_week"] = frame.origin_week + horizon
        frame["actual_revenue"] = group.revenue.shift(-horizon)
        frame["normalized_target"] = frame.actual_revenue / frame.scale
        target_dates = monday_one + pd.to_timedelta((frame.target_week-1)*config.DAYS_PER_WEEK, unit="D")
        angle = target_dates.dt.isocalendar().week.astype(float) * 2*np.pi/config.SEASONAL_PERIOD
        frame["week_sin"], frame["week_cos"] = np.sin(angle), np.cos(angle)
        month_angle = target_dates.dt.month.astype(float)*2*np.pi/config.FORECAST_CALENDAR_MONTHS
        frame["month_sin"], frame["month_cos"] = np.sin(month_angle), np.cos(month_angle)
        seasonal_index = pd.MultiIndex.from_arrays([frame.COMMODITY_DESC, frame.target_week-config.SEASONAL_PERIOD])
        frame["seasonal_naive"] = indexed.reindex(seasonal_index).to_numpy()
        frame["naive"] = frame.revenue
        frame["moving_average"] = means[config.MOVING_AVERAGE_WEEKS]
        frame = frame.loc[frame.scale.notna()].copy()
        records.append(frame[["COMMODITY_DESC", "origin_week", "target_week", "horizon", "scale",
                             "actual_revenue", "normalized_target", "naive", "seasonal_naive", "moving_average"] + config.FORECAST_FEATURES])
    panel = pd.concat(records, ignore_index=True).sort_values(["horizon", "COMMODITY_DESC", "origin_week"]).reset_index(drop=True)
    return panel, categories, schedule


def training_rows(panel, horizon, cutoff):
    return panel.loc[panel.horizon.eq(horizon) & panel.target_week.le(cutoff) & panel.actual_revenue.notna()].copy()


def evaluation_rows(panel, horizon, start, end):
    # All horizons share first origin start-1. Longer horizons have fewer evaluable origins.
    return panel.loc[panel.horizon.eq(horizon) & panel.origin_week.ge(start-1) & panel.target_week.le(end) & panel.actual_revenue.notna()].copy()

