"""Train/evaluate and persist the direct-horizon forecasting stage from processed data."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pickle
import numpy as np
import pandas as pd
import plotly.express as px
import sklearn
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.category_access import load_promotion_report
from src.data_access import load_processed_master, load_validated_aggregate
from src.forecast_features import build_feature_panel, settings_fingerprint
from src.forecast_training import fit_model, tune_models, prediction_frame, evaluation_tables, total_evaluation, metrics
from src.scope import policy_fingerprint


def build_covariates(complete, weekly, exposure):
    loyalty = complete.groupby(["COMMODITY_DESC", "WEEK_NO"]).HAS_LOYALTY_DISC.mean().rename("loyalty_share").reset_index()
    covariates = weekly[["COMMODITY_DESC", "WEEK_NO"]].merge(loyalty, how="left", validate="one_to_one")
    # No transaction lines means an undefined share, preserved as NaN for the model.
    return covariates.merge(exposure, on=["COMMODITY_DESC", "WEEK_NO"], validate="one_to_one")


def main():
    config.FORECAST_VALIDATION_FILE.unlink(missing_ok=True)
    promotion = load_promotion_report()
    master = load_processed_master()
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master)]
    complete = window.loc[window.IS_COMPLETE_WEEK]
    weekly = load_validated_aggregate("commodity_weekly")
    weekly = weekly.loc[weekly.in_window].copy()
    exposure = pd.read_parquet(config.PROCESSED_DIR / "promo_category_weekly.parquet")
    covariates = build_covariates(complete, weekly, exposure)
    panel, categories, schedule = build_feature_panel(weekly, covariates)
    tuning, selections, validation_predictions = tune_models(panel, schedule)
    print("Validation settings frozen. Computing frozen held-out predictions; test metrics are excluded from all choices.", flush=True)
    evaluation_models = {h: fit_model(panel, h, schedule["evaluation_training_cutoff"], selection["params"]) for h, selection in selections.items()}
    predictions, clipped_test = prediction_frame(panel, evaluation_models, selections, schedule["test_start"], schedule["test_end"])
    category_metrics, horizon_metrics = evaluation_tables(predictions)
    totals, total_metrics = total_evaluation(predictions)
    origin = int(weekly.WEEK_NO.max())
    production = {h: fit_model(panel, h, origin, selection["params"]) for h, selection in selections.items()}
    future, clipped_future = prediction_frame(panel, production, selections, origin=origin)
    bundle = {"models": production, "categories": categories, "features": config.FORECAST_FEATURES,
              "selections": selections, "training_cutoff": origin, "settings_fingerprint": settings_fingerprint(),
              "sklearn_version": sklearn.__version__}
    eval_bundle = {**bundle, "models": evaluation_models, "training_cutoff": schedule["evaluation_training_cutoff"]}
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (config.MODELS_DIR / "forecast_model.pkl").write_bytes(pickle.dumps(bundle))
    (config.MODELS_DIR / "forecast_evaluation_models.pkl").write_bytes(pickle.dumps(eval_bundle))
    frames = {"forecast_panel": panel, "forecast_covariates": covariates,
              "forecast_backtest": predictions, "forecast_validation_predictions": validation_predictions,
              "forecast_next_weeks": future, "forecast_total_backtest": totals}
    for name, frame in frames.items():
        frame.to_parquet(config.PROCESSED_DIR / f"{name}.parquet", index=False, compression=config.PARQUET_COMPRESSION)
    tuning.to_csv(config.OUTPUTS_DIR / "forecast_tuning.csv", index=False)
    category_metrics.to_csv(config.OUTPUTS_DIR / "forecast_metrics_by_category.csv", index=False)
    horizon_metrics.to_csv(config.OUTPUTS_DIR / "forecast_metrics_overall.csv", index=False)
    total_metrics.to_csv(config.OUTPUTS_DIR / "forecast_total_metrics.csv", index=False)
    improvement_records = []
    combined_metrics = pd.concat([category_metrics, horizon_metrics.assign(COMMODITY_DESC="ALL_CATEGORIES")], ignore_index=True)
    for (category, horizon), group in combined_metrics.groupby(["COMMODITY_DESC", "horizon"]):
        learned = float(group.loc[group.model.eq("Gradient boosting"), "WAPE_pct"].iloc[0])
        for baseline in [name for name in config.FORECAST_METHODS if name != "Gradient boosting"]:
            value = float(group.loc[group.model.eq(baseline), "WAPE_pct"].iloc[0])
            improvement_records.append({"COMMODITY_DESC": category, "horizon": int(horizon), "baseline": baseline,
                "model_WAPE_pct": learned, "baseline_WAPE_pct": value,
                "relative_WAPE_improvement_pct": (value-learned)/value*100 if value>0 else np.nan})
    pd.DataFrame(improvement_records).to_csv(config.OUTPUTS_DIR / "forecast_improvement.csv", index=False)
    pretest = weekly.loc[weekly.WEEK_NO.le(schedule["evaluation_training_cutoff"]) & weekly.COMMODITY_DESC.isin(categories)]
    volatility = pretest.groupby("COMMODITY_DESC").revenue.agg(lambda values: values.std(ddof=0)/values.mean())
    volatility_rows = predictions.copy()
    volatility_rows["volatility"] = np.where(volatility_rows.COMMODITY_DESC.map(volatility).le(config.FORECAST_VOLATILITY_THRESHOLD), "CV <= threshold", "CV > threshold")
    volatility_metrics = []
    for (band, horizon), group in volatility_rows.groupby(["volatility", "horizon"]):
        for name,column in {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}.items():
            volatility_metrics.append({"volatility": band, "horizon": int(horizon), "model": name,
                                      "categories": int(group.COMMODITY_DESC.nunique()), **metrics(group.actual_revenue,group[column])})
    pd.DataFrame(volatility_metrics).to_csv(config.OUTPUTS_DIR / "forecast_error_by_volatility.csv", index=False)
    errors = []
    for target, group in predictions.groupby("target_week"):
        for name, column in {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}.items():
            errors.append({"target_week": int(target), "model": name, **metrics(group.actual_revenue, group[column])})
    pd.DataFrame(errors).to_csv(config.OUTPUTS_DIR / "forecast_error_by_week.csv", index=False)
    figure = px.bar(horizon_metrics, x="horizon", y="WAPE_pct", color="model", barmode="group",
                    title="Held-out weekly revenue: horizons 1-4, identical origin/target pairs per horizon")
    figure.write_html(config.OUTPUTS_DIR / "forecast_diagnostics.html", include_plotlyjs=True)
    wins = {}
    for horizon in range(1, config.FORECAST_HORIZON+1):
        table = category_metrics.loc[category_metrics.horizon.eq(horizon)].pivot(index="COMMODITY_DESC", columns="model", values="WAPE_pct")
        baselines = [name for name in config.FORECAST_METHODS if name != "Gradient boosting"]
        wins[str(horizon)] = int(table["Gradient boosting"].lt(table[baselines].min(axis=1)).sum())
    paths = [config.PROCESSED_DIR / f"{name}.parquet" for name in config.FORECAST_TABLES]
    paths += [config.OUTPUTS_DIR / name for name in config.FORECAST_OUTPUT_NAMES]
    paths += [config.MODELS_DIR / name for name in config.FORECAST_MODEL_NAMES]
    write_json(config.FORECAST_BUILD_FILE, {
        "status": "BUILT_REQUIRES_VALIDATION", "policy_fingerprint": policy_fingerprint(),
        "settings_fingerprint": settings_fingerprint(), "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"],
        "weekly_sha256": file_fingerprint(config.PROCESSED_DIR / "commodity_weekly.parquet")["sha256"],
        "promotion_build_sha256": file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"],
        "sklearn_version": sklearn.__version__, "features": config.FORECAST_FEATURES,
        "categories": categories, "forecastable_categories": len(categories), "schedule": schedule,
        "selections": selections, "start_week": int(window.WEEK_NO.min()), "end_week": int(window.WEEK_NO.max()),
        "first_complete_week": int(weekly.WEEK_NO.min()), "last_complete_week": origin,
        "complete_weeks": int(weekly.WEEK_NO.nunique()), "transaction_lines": len(window),
        "revenue": float(window.SALES_VALUE.sum()), "households": int(window.household_key.nunique()),
        "excluded_partial_weeks": [int(w) for w in sorted(set(window.WEEK_NO)-set(weekly.WEEK_NO))],
        "panel_rows": len(panel), "test_prediction_pairs": len(predictions),
        "model_beats_all_three_baselines_categories_by_horizon": wins,
        "overall_metrics": horizon_metrics.to_dict("records"), "four_week_total_metrics": total_metrics.to_dict("records"),
        "clipped_negative_test_predictions": clipped_test, "clipped_negative_future_predictions": clipped_future,
        "note": "Cohort selected before first validation window; early stopping disabled; no shuffled splits. Target scaled by origin-only eight-week mean. Synthetic calendar cyclic features, no holiday attribution, no lag52 model feature. Lagged promotion signals keep unknown values/missingness. Baselines use the same origin, category, horizon and actual targets. Serving method selected globally per horizon using validation only. Test training frozen before week 90; production refit includes observed outcomes through last complete week. Longer horizons have fewer evaluable origins inside the 12-week test block. No prediction intervals or causal effects claimed.",
        "artifacts": [file_fingerprint(path) for path in paths]})
    print(horizon_metrics.to_string(index=False), flush=True)
    print("Model beats all three baselines by horizon:", wins, flush=True)
    print(f"Saved four trained direct models for {len(categories)} categories; run src/validate_forecasts.py.", flush=True)


if __name__ == "__main__":
    main()

