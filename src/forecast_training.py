"""Deterministic global gradient boosting, validation-only choice and fair baseline metrics."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from src import config
from src.forecast_features import training_rows, evaluation_rows


def make_model(params):
    return HistGradientBoostingRegressor(**params, early_stopping=False, random_state=config.RANDOM_STATE,
                  categorical_features=[config.FORECAST_FEATURES.index("commodity_code")])


def fit_model(panel, horizon, cutoff, params):
    rows = training_rows(panel, horizon, cutoff)
    if rows.empty or rows.target_week.max() > cutoff:
        raise ValueError("No valid chronological training rows.")
    model = make_model(params)
    with threadpool_limits(limits=1):
        model.fit(rows[config.FORECAST_FEATURES], rows.normalized_target)
    return model


def model_prediction(model, rows):
    with threadpool_limits(limits=1):
        raw = model.predict(rows[config.FORECAST_FEATURES]) * rows.scale.to_numpy()
    return np.maximum(raw, 0), int((raw < 0).sum())


def metrics(actual, predicted):
    a, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if not len(a) or not np.isfinite(a).all() or not np.isfinite(p).all():
        raise ValueError("Forecast metrics need finite, nonempty paired observations.")
    error = np.abs(a-p)
    nonzero = a != 0
    return {"MAE": float(error.mean()), "RMSE": float(np.sqrt(np.mean((a-p)**2))),
            "MAPE_pct": float(np.mean(error[nonzero]/np.abs(a[nonzero]))*100) if nonzero.any() else None,
            "WAPE_pct": float(error.sum()/np.abs(a).sum()*100) if np.abs(a).sum() else None,
            "MAPE_nonzero_weeks": int(nonzero.sum()), "prediction_pairs": len(a)}


def tune_models(panel, schedule):
    tuning, selections, validation_predictions = [], {}, []
    for horizon in range(1, config.FORECAST_HORIZON+1):
        candidate_predictions = []
        for candidate, params in enumerate(config.FORECAST_PARAMS):
            folds = []
            for fold in schedule["folds"]:
                model = fit_model(panel, horizon, fold["start"]-1, params)
                rows = evaluation_rows(panel, horizon, fold["start"], fold["end"])
                predicted, clipped = model_prediction(model, rows)
                evidence = rows[["COMMODITY_DESC", "origin_week", "target_week", "horizon", "actual_revenue", "naive", "seasonal_naive", "moving_average"]].copy()
                evidence["gradient_boosting"] = predicted
                evidence["fold"] = fold["fold"]
                evidence["training_cutoff"] = fold["start"]-1
                folds.append(evidence)
                tuning.append({"horizon": horizon, "candidate": candidate, "fold": fold["fold"],
                               "training_cutoff": fold["start"]-1, "clipped_predictions": clipped, **params,
                               **metrics(rows.actual_revenue, predicted)})
            all_folds = pd.concat(folds, ignore_index=True)
            score = metrics(all_folds.actual_revenue, all_folds.gradient_boosting)["WAPE_pct"]
            candidate_predictions.append((score, candidate, all_folds))
            print(f"Horizon {horizon}, candidate {candidate}: validation WAPE {score:.3f}%", flush=True)
        _, selected_candidate, selected_rows = min(candidate_predictions, key=lambda item: (item[0], item[1]))
        choices = []
        for name, column in config.FORECAST_METHODS.items():
            choices.append((metrics(selected_rows.actual_revenue, selected_rows[column])["WAPE_pct"], name))
        _, method = min(choices, key=lambda item: (item[0], item[1]))
        selections[horizon] = {"candidate": selected_candidate, "params": config.FORECAST_PARAMS[selected_candidate],
                               "serving_method": method, "validation_metrics": {name: metrics(selected_rows.actual_revenue, selected_rows[column]) for name, column in config.FORECAST_METHODS.items()}}
        selected_rows["selected_forecast"] = selected_rows[config.FORECAST_METHODS[method]]
        validation_predictions.append(selected_rows)
    return pd.DataFrame(tuning), selections, pd.concat(validation_predictions, ignore_index=True)


def prediction_frame(panel, models, selections, start=None, end=None, origin=None):
    frames, clipped = [], 0
    for horizon, model in models.items():
        rows = evaluation_rows(panel, horizon, start, end) if origin is None else panel.loc[panel.horizon.eq(horizon) & panel.origin_week.eq(origin)]
        result = rows[["COMMODITY_DESC", "origin_week", "target_week", "horizon", "actual_revenue", "naive", "seasonal_naive", "moving_average"]].copy()
        result["gradient_boosting"], n = model_prediction(model, rows)
        result["selected_method"] = selections[horizon]["serving_method"]
        result["selected_forecast"] = result[config.FORECAST_METHODS[selections[horizon]["serving_method"]]]
        clipped += n
        frames.append(result)
    return pd.concat(frames, ignore_index=True), clipped


def evaluation_tables(predictions):
    methods = {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}
    by_category, overall = [], []
    for (category, horizon), group in predictions.groupby(["COMMODITY_DESC", "horizon"]):
        for model, column in methods.items():
            by_category.append({"COMMODITY_DESC": category, "horizon": int(horizon), "model": model, **metrics(group.actual_revenue, group[column])})
    for horizon, group in predictions.groupby("horizon"):
        for model, column in methods.items():
            overall.append({"horizon": int(horizon), "model": model, **metrics(group.actual_revenue, group[column])})
    return pd.DataFrame(by_category), pd.DataFrame(overall)


def total_evaluation(predictions):
    complete = predictions.groupby(["COMMODITY_DESC", "origin_week"]).horizon.nunique()
    index = complete.loc[complete.eq(config.FORECAST_HORIZON)].index
    matched = predictions.set_index(["COMMODITY_DESC", "origin_week"]).loc[index].reset_index()
    columns = ["actual_revenue", *config.FORECAST_METHODS.values(), "selected_forecast"]
    totals = matched.groupby(["COMMODITY_DESC", "origin_week"])[columns].sum().reset_index()
    records = []
    for name, column in {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}.items():
        records.append({"model": name, **metrics(totals.actual_revenue, totals[column])})
    return totals, pd.DataFrame(records)
