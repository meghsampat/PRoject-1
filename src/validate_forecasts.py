"""Independent source features, chronological refits, matched metrics and saved inference checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_processed_master, load_validated_aggregate
from src.forecast_access import load_forecast_models, predict_from_bundle


def direct_metrics(a, p):
    a, p = np.asarray(a, dtype=float), np.asarray(p, dtype=float)
    difference = np.abs(a-p)
    mask = a != 0
    return {"MAE": float(difference.mean()), "RMSE": float(np.sqrt(np.mean((a-p)**2))),
            "WAPE_pct": float(difference.sum()/np.abs(a).sum()*100) if np.abs(a).sum() else None,
            "MAPE_pct": float(np.mean(difference[mask]/np.abs(a[mask]))*100) if mask.any() else None,
            "MAPE_nonzero_weeks": int(mask.sum()), "prediction_pairs": len(a)}


def assert_metrics(row, actual, predicted):
    for name, value in direct_metrics(actual, predicted).items():
        if value is None:
            assert pd.isna(row[name])
        else:
            assert np.isclose(row[name], value)


def independent_fit(panel, horizon, cutoff, params):
    rows = panel.loc[panel.horizon.eq(horizon) & panel.target_week.le(cutoff) & panel.actual_revenue.notna()]
    assert not rows.empty and rows.origin_week.max()+horizon <= cutoff
    model = HistGradientBoostingRegressor(**params, early_stopping=False, random_state=config.RANDOM_STATE,
                  categorical_features=[config.FORECAST_FEATURES.index("commodity_code")])
    with threadpool_limits(limits=1):
        model.fit(rows[config.FORECAST_FEATURES], rows.actual_revenue/rows.scale)
    return model


def independent_predict(model, rows):
    with threadpool_limits(limits=1):
        return np.maximum(model.predict(rows[config.FORECAST_FEATURES])*rows.scale.to_numpy(), 0)


def main():
    production, evaluation, report = load_forecast_models(require_validation=False)
    panel = pd.read_parquet(config.PROCESSED_DIR / "forecast_panel.parquet")
    covariates = pd.read_parquet(config.PROCESSED_DIR / "forecast_covariates.parquet")
    backtest = pd.read_parquet(config.PROCESSED_DIR / "forecast_backtest.parquet")
    validation = pd.read_parquet(config.PROCESSED_DIR / "forecast_validation_predictions.parquet")
    future = pd.read_parquet(config.PROCESSED_DIR / "forecast_next_weeks.parquet")
    totals = pd.read_parquet(config.PROCESSED_DIR / "forecast_total_backtest.parquet")
    tuning = pd.read_csv(config.OUTPUTS_DIR / "forecast_tuning.csv")
    category_metrics = pd.read_csv(config.OUTPUTS_DIR / "forecast_metrics_by_category.csv")
    overall = pd.read_csv(config.OUTPUTS_DIR / "forecast_metrics_overall.csv")
    total_metrics = pd.read_csv(config.OUTPUTS_DIR / "forecast_total_metrics.csv")
    master = load_processed_master()
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master)]
    complete = window.loc[window.IS_COMPLETE_WEEK]
    weekly = load_validated_aggregate("commodity_weekly")
    weekly = weekly.loc[weekly.in_window]
    schedule = report["schedule"]
    assert schedule["test_start"] == weekly.WEEK_NO.max()-config.FORECAST_HOLDOUT+1
    assert schedule["evaluation_training_cutoff"] == schedule["test_start"]-1
    assert schedule["eligibility_cutoff"] == schedule["test_start"]-config.FORECAST_VALIDATION_FOLDS*config.FORECAST_VALIDATION_WEEKS-1
    assert len(schedule["folds"]) == config.FORECAST_VALIDATION_FOLDS
    for index, fold in enumerate(schedule["folds"]):
        assert fold == {"fold": index+1, "start": schedule["eligibility_cutoff"]+1+index*config.FORECAST_VALIDATION_WEEKS,
                       "end": schedule["eligibility_cutoff"]+(index+1)*config.FORECAST_VALIDATION_WEEKS}
        assert fold["end"] < schedule["test_start"]
    initial = weekly.loc[weekly.WEEK_NO.le(schedule["eligibility_cutoff"])]
    activity = initial.groupby("COMMODITY_DESC").revenue.apply(lambda values: (values>0).mean())
    categories = sorted(activity[activity>=config.FORECASTABLE_WEEK_SHARE].index)
    assert categories == report["categories"] == production["categories"] == evaluation["categories"]
    assert production["features"] == evaluation["features"] == config.FORECAST_FEATURES
    assert production["training_cutoff"] == schedule["test_end"]
    assert evaluation["training_cutoff"] == schedule["evaluation_training_cutoff"]
    assert set(production["models"]) == set(evaluation["models"]) == set(range(1,config.FORECAST_HORIZON+1))
    assert panel[["COMMODITY_DESC","horizon","origin_week"]].duplicated().sum() == 0
    loyalty = complete.groupby(["COMMODITY_DESC","WEEK_NO"]).HAS_LOYALTY_DISC.mean()
    observed = covariates.set_index(["COMMODITY_DESC","WEEK_NO"])
    assert np.allclose(observed.loyalty_share, loyalty.reindex(observed.index), equal_nan=True)
    exposure = pd.read_parquet(config.PROCESSED_DIR / "promo_category_weekly.parquet").set_index(["COMMODITY_DESC","WEEK_NO"])
    for name in ["sales_keys","matched_keys","display_share","mailer_share","coverage_share"]:
        assert np.allclose(observed[name], exposure.loc[observed.index,name], equal_nan=True)
    direct = complete.groupby(["COMMODITY_DESC","WEEK_NO"]).SALES_VALUE.sum()
    assert np.allclose(weekly.revenue, direct.reindex(pd.MultiIndex.from_frame(weekly[["COMMODITY_DESC","WEEK_NO"]])).fillna(0))
    monday = pd.Timestamp(config.CALENDAR_DAY_ONE)-pd.Timedelta(days=pd.Timestamp(config.CALENDAR_DAY_ONE).weekday())
    # Build each origin's features directly from an explicitly truncated historical array.
    panel_index = panel.set_index(["COMMODITY_DESC","origin_week","horizon"])
    for code, category in enumerate(categories):
        g = weekly.loc[weekly.COMMODITY_DESC.eq(category)].sort_values("WEEK_NO")
        values, weeks = g.revenue.to_numpy(), g.WEEK_NO.to_numpy()
        for offset in range(max(config.FORECAST_ROLLING_WINDOWS)-1,len(g)):
            origin = int(weeks[offset])
            history = values[:offset+1]
            scale = max(float(np.mean(history[-max(config.FORECAST_ROLLING_WINDOWS):])),config.FORECAST_SCALE_FLOOR)
            cov = observed.loc[(category,origin)]
            known = cov.coverage_share >= config.FORECAST_PROMO_MIN_COVERAGE and cov.matched_keys >= config.FORECAST_PROMO_MIN_KEYS
            for horizon in range(1,config.FORECAST_HORIZON+1):
                row = panel_index.loc[(category,origin,horizon)]
                assert row.target_week == origin+horizon and row.commodity_code == code and np.isclose(row.scale,scale)
                for lag in config.FORECAST_LAGS:
                    assert np.isclose(row[f"revenue_lag{lag}"],history[-lag]/scale)
                for size in config.FORECAST_ROLLING_WINDOWS:
                    assert np.isclose(row[f"rolling_mean{size}"],np.mean(history[-size:])/scale)
                    assert np.isclose(row[f"rolling_std{size}"],np.std(history[-size:],ddof=0)/scale,atol=1e-7)
                assert np.isclose(row.log_scale,np.log1p(scale))
                assert np.isclose(row.loyalty_lag1,cov.loyalty_share,equal_nan=True)
                assert np.isclose(row.display_lag1,cov.display_share if known else np.nan,equal_nan=True)
                assert np.isclose(row.mailer_lag1,cov.mailer_share if known else np.nan,equal_nan=True)
                assert np.isclose(row.promo_coverage,cov.coverage_share,equal_nan=True)
                assert row.promo_unknown == float(not known)
                date = monday+pd.Timedelta(weeks=int(origin+horizon-1))
                week_angle = date.isocalendar().week*2*np.pi/config.SEASONAL_PERIOD
                month_angle = date.month*2*np.pi/config.FORECAST_CALENDAR_MONTHS
                for name, expected in [("week_sin",np.sin(week_angle)),("week_cos",np.cos(week_angle)),
                                       ("month_sin",np.sin(month_angle)),("month_cos",np.cos(month_angle))]:
                    assert np.isclose(row[name],expected)
                actual = values[offset+horizon] if offset+horizon<len(values) else np.nan
                assert np.isclose(row.actual_revenue,actual,equal_nan=True)
                assert np.isclose(row.normalized_target,actual/scale,equal_nan=True)
                assert np.isclose(row.naive,history[-1]) and np.isclose(row.moving_average,np.mean(history[-config.MOVING_AVERAGE_WEEKS:]))
                seasonal_week = origin+horizon-config.SEASONAL_PERIOD
                seasonal = g.loc[g.WEEK_NO.eq(seasonal_week),"revenue"]
                assert np.isclose(row.seasonal_naive,float(seasonal.iloc[0]) if len(seasonal) else np.nan,equal_nan=True)
                assert seasonal_week <= origin
    checks = ["All processed origin features and covariates reconcile with explicit past-only histories; future targets and cohort eligibility checked"]

    for horizon in range(1,config.FORECAST_HORIZON+1):
        candidate_scores = []
        for candidate, params in enumerate(config.FORECAST_PARAMS):
            predictions, actuals = [], []
            for fold in schedule["folds"]:
                rows = panel.loc[panel.horizon.eq(horizon) & panel.origin_week.ge(fold["start"]-1) & panel.target_week.le(fold["end"]) & panel.actual_revenue.notna()]
                model = independent_fit(panel,horizon,fold["start"]-1,params)
                predicted = independent_predict(model,rows)
                record = tuning.loc[tuning.horizon.eq(horizon)&tuning.candidate.eq(candidate)&tuning.fold.eq(fold["fold"])]
                assert len(record)==1 and record.iloc[0].training_cutoff==fold["start"]-1
                assert_metrics(record.iloc[0],rows.actual_revenue,predicted)
                if candidate == report["selections"][str(horizon)]["candidate"]:
                    saved = validation.loc[validation.horizon.eq(horizon)&validation.fold.eq(fold["fold"])]
                    assert np.array_equal(saved[["COMMODITY_DESC","origin_week","target_week"]],rows[["COMMODITY_DESC","origin_week","target_week"]])
                    assert np.allclose(saved.gradient_boosting,predicted)
                predictions.extend(predicted); actuals.extend(rows.actual_revenue)
            candidate_scores.append(direct_metrics(actuals,predictions)["WAPE_pct"])
        selection = report["selections"][str(horizon)]
        assert selection["candidate"] == int(np.argmin(candidate_scores))
        assert selection["params"] == config.FORECAST_PARAMS[selection["candidate"]]
        selected = validation.loc[validation.horizon.eq(horizon)]
        method_scores = {}
        for method,column in config.FORECAST_METHODS.items():
            expected = direct_metrics(selected.actual_revenue,selected[column])
            for name,value in expected.items():
                actual = selection["validation_metrics"][method][name]
                assert actual is None if value is None else np.isclose(actual,value)
            method_scores[method]=expected["WAPE_pct"]
        assert selection["serving_method"]==min(method_scores,key=lambda name:(method_scores[name],name))
        assert production["selections"][horizon] == evaluation["selections"][horizon] == selection
        for bundle, cutoff in [(evaluation,schedule["evaluation_training_cutoff"]),(production,schedule["test_end"])]:
            model = bundle["models"][horizon]
            assert model.early_stopping is False and model.random_state == config.RANDOM_STATE
            assert model.feature_names_in_.tolist()==config.FORECAST_FEATURES
            refit=independent_fit(panel,horizon,cutoff,selection["params"])
            rows=panel.loc[panel.horizon.eq(horizon)&panel.origin_week.eq(cutoff)]
            assert np.allclose(independent_predict(model,rows),independent_predict(refit,rows))
        rows=panel.loc[panel.horizon.eq(horizon)&panel.origin_week.ge(schedule["test_start"]-1)&panel.target_week.le(schedule["test_end"])&panel.actual_revenue.notna()]
        saved=backtest.loc[backtest.horizon.eq(horizon)]
        assert np.array_equal(saved[["COMMODITY_DESC","origin_week","target_week"]],rows[["COMMODITY_DESC","origin_week","target_week"]])
        assert saved.groupby("COMMODITY_DESC").size().eq(config.FORECAST_HOLDOUT-horizon+1).all()
        assert np.allclose(saved.actual_revenue,rows.actual_revenue)
        assert np.allclose(saved.gradient_boosting,independent_predict(evaluation["models"][horizon],rows))
        for column in ["naive","seasonal_naive","moving_average"]:
            assert np.allclose(saved[column],rows[column])
        assert np.allclose(saved.selected_forecast,saved[config.FORECAST_METHODS[selection["serving_method"]]])
        assert saved.selected_method.eq(selection["serving_method"]).all()
        print(f"Validated horizon {horizon}: all tuning refits, frozen test models and production refit",flush=True)
    checks.append("Every validation candidate refit; hyperparameter/serving selection uses validation only; frozen test and production models reproduce")
    methods={**config.FORECAST_METHODS,"Validation-selected forecast":"selected_forecast"}
    for _,row in category_metrics.iterrows():
        pairs=backtest.loc[backtest.COMMODITY_DESC.eq(row.COMMODITY_DESC)&backtest.horizon.eq(row.horizon)]
        assert_metrics(row,pairs.actual_revenue,pairs[methods[row.model]])
    for _,row in overall.iterrows():
        pairs=backtest.loc[backtest.horizon.eq(row.horizon)]
        assert_metrics(row,pairs.actual_revenue,pairs[methods[row.model]])
    for row in totals.itertuples():
        pairs=backtest.loc[backtest.COMMODITY_DESC.eq(row.COMMODITY_DESC)&backtest.origin_week.eq(row.origin_week)]
        assert len(pairs)==config.FORECAST_HORIZON
        for column in ["actual_revenue",*methods.values()]:
            assert np.isclose(getattr(row,column),pairs[column].sum())
    assert totals.groupby("COMMODITY_DESC").size().eq(config.FORECAST_HOLDOUT-config.FORECAST_HORIZON+1).all()
    for _,row in total_metrics.iterrows():
        assert_metrics(row,totals.actual_revenue,totals[methods[row.model]])
    improvements = pd.read_csv(config.OUTPUTS_DIR / "forecast_improvement.csv")
    combined = pd.concat([category_metrics,overall.assign(COMMODITY_DESC="ALL_CATEGORIES")],ignore_index=True)
    for row in improvements.itertuples():
        group = combined.loc[combined.COMMODITY_DESC.eq(row.COMMODITY_DESC)&combined.horizon.eq(row.horizon)]
        learned = group.loc[group.model.eq("Gradient boosting"),"WAPE_pct"].iloc[0]
        baseline = group.loc[group.model.eq(row.baseline),"WAPE_pct"].iloc[0]
        assert np.isclose(row.model_WAPE_pct,learned) and np.isclose(row.baseline_WAPE_pct,baseline)
        assert np.isclose(row.relative_WAPE_improvement_pct,(baseline-learned)/baseline*100 if baseline>0 else np.nan,equal_nan=True)
    assert len(improvements)==(len(categories)+1)*config.FORECAST_HORIZON*3
    volatility = weekly.loc[weekly.WEEK_NO.le(schedule["evaluation_training_cutoff"])].groupby("COMMODITY_DESC").revenue.agg(lambda values: values.std(ddof=0)/values.mean())
    volatility_errors=pd.read_csv(config.OUTPUTS_DIR / "forecast_error_by_volatility.csv")
    for _,row in volatility_errors.iterrows():
        eligible = volatility.loc[volatility.le(config.FORECAST_VOLATILITY_THRESHOLD) if row.volatility=="CV <= threshold" else volatility.gt(config.FORECAST_VOLATILITY_THRESHOLD)].index
        pairs=backtest.loc[backtest.COMMODITY_DESC.isin(eligible)&backtest.horizon.eq(row.horizon)]
        assert_metrics(row,pairs.actual_revenue,pairs[methods[row.model]])
        assert row.categories==pairs.COMMODITY_DESC.nunique()
    errors_by_week=pd.read_csv(config.OUTPUTS_DIR / "forecast_error_by_week.csv")
    for _,row in errors_by_week.iterrows():
        pairs=backtest.loc[backtest.target_week.eq(row.target_week)]
        assert_metrics(row,pairs.actual_revenue,pairs[methods[row.model]])
    for category in categories:
        predicted=predict_from_bundle(production,panel,category,config.FORECAST_HORIZON)
        saved=future.loc[future.COMMODITY_DESC.eq(category)].sort_values("horizon")
        assert np.allclose(predicted.forecast_revenue,saved.selected_forecast)
        assert np.allclose(predicted.trained_revenue,saved.gradient_boosting)
        assert np.array_equal(predicted.week,saved.target_week)
    assert schedule["test_end"] in set(backtest.target_week) and 92 in set(backtest.target_week)
    checks.append("All category/horizon/overall/four-week-total metrics independently recomputed; every saved-model future prediction reproduced; week 92 retained")
    write_json(config.FORECAST_VALIDATION_FILE,{"status":"PASS","checks":checks,
               "build_report_sha256":file_fingerprint(config.FORECAST_BUILD_FILE)["sha256"],
               "forecastable_categories":len(categories),"holdout_target_block":[schedule["test_start"],schedule["test_end"]],
               "test_prediction_pairs":len(backtest),"model_reload_reproduced":True,
               "business_value_or_future_accuracy_certified":False})
    print("PASS: independent trained forecasting validation",flush=True)


if __name__=="__main__":
    main()

