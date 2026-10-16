"""Serve only current, independently validated local forecast artifacts and models."""
import json
import math
from numbers import Integral
import pickle
import pandas as pd
import sklearn
from src import config
from src.artifact_io import file_fingerprint
from src.category_access import load_promotion_report
from src.forecast_features import settings_fingerprint
from src.forecast_training import model_prediction, metrics
from src.scope import policy_fingerprint


def artifact_locations():
    names = {f"{name}.parquet": config.PROCESSED_DIR for name in config.FORECAST_TABLES}
    names.update({name: config.OUTPUTS_DIR for name in config.FORECAST_OUTPUT_NAMES})
    names.update({name: config.MODELS_DIR for name in config.FORECAST_MODEL_NAMES})
    return names


def load_forecast_report(require_validation=True):
    load_promotion_report()
    report = json.loads(config.FORECAST_BUILD_FILE.read_text(encoding="utf-8"))
    if report.get("policy_fingerprint") != policy_fingerprint() or report.get("settings_fingerprint") != settings_fingerprint():
        raise ValueError("Forecast settings/scope changed; retrain and validate saved models.")
    if report.get("master_sha256") != file_fingerprint(config.MASTER_FILE)["sha256"] or report.get("weekly_sha256") != file_fingerprint(config.PROCESSED_DIR / "commodity_weekly.parquet")["sha256"]:
        raise ValueError("Forecast source changed; rebuild and validate.")
    if report.get("promotion_build_sha256") != file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"]:
        raise ValueError("Promotion preparation changed; rebuild forecasts.")
    if report.get("sklearn_version") != sklearn.__version__:
        raise ValueError("scikit-learn version changed; retrain models.")
    names = artifact_locations()
    if {item["name"] for item in report["artifacts"]} != set(names) or len(report["artifacts"]) != len(names):
        raise ValueError("Incomplete forecast artifact inventory.")
    for item in report["artifacts"]:
        if item != file_fingerprint(names[item["name"]] / item["name"]):
            raise ValueError("Forecast artifact changed since training.")
    if require_validation:
        validation = json.loads(config.FORECAST_VALIDATION_FILE.read_text(encoding="utf-8"))
        if validation.get("status") != "PASS" or validation.get("build_report_sha256") != file_fingerprint(config.FORECAST_BUILD_FILE)["sha256"]:
            raise ValueError("Forecasting has not passed current independent validation.")
    return report


def load_forecast_models(require_validation=True):
    report = load_forecast_report(require_validation)
    # Exact local inventory and fingerprints are checked before unpickling.
    bundle = pickle.loads((config.MODELS_DIR / "forecast_model.pkl").read_bytes())
    evaluation = pickle.loads((config.MODELS_DIR / "forecast_evaluation_models.pkl").read_bytes())
    return bundle, evaluation, report


def predict_from_bundle(bundle, panel, commodity, horizon):
    if not isinstance(horizon, Integral) or isinstance(horizon, bool) or not 1 <= horizon <= config.FORECAST_HORIZON:
        raise ValueError("Forecast horizon must be an integer from 1 through 4.")
    if commodity not in bundle["categories"]:
        raise ValueError("Commodity was not forecastable in the initial training window.")
    records = []
    for h in range(1, horizon+1):
        rows = panel.loc[panel.COMMODITY_DESC.eq(commodity) & panel.origin_week.eq(bundle["training_cutoff"]) & panel.horizon.eq(h)]
        if len(rows) != 1:
            raise ValueError("Missing/duplicated production forecast features.")
        trained, _ = model_prediction(bundle["models"][h], rows)
        method = bundle["selections"][h]["serving_method"]
        values = {name: float(rows.iloc[0][column]) for name, column in config.FORECAST_METHODS.items() if name != "Gradient boosting"}
        values["Gradient boosting"] = float(trained[0])
        records.append({"week": int(rows.iloc[0].target_week), "horizon": h,
                        "forecast_revenue": values[method], "trained_revenue": values["Gradient boosting"],
                        "selected_method": method, "naive": values["Naive"],
                        "seasonal_naive": values["Seasonal naive (52 weeks)"],
                        "moving_average": values["Four-week moving average (fixed origin)"]})
    return pd.DataFrame(records)


def predict_next_weeks(commodity, h=config.FORECAST_HORIZON):
    """Load validated saved models and predict direct horizons 1..h for an exact commodity."""
    bundle, _, _ = load_forecast_models()
    panel = pd.read_parquet(config.PROCESSED_DIR / "forecast_panel.parquet")
    return predict_from_bundle(bundle, panel, commodity, h)


def records(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def saved_forecast_result(scoped, start_week, end_week, commodity):
    bundle, _, report = load_forecast_models()
    if (start_week, end_week) != (report["start_week"], report["end_week"]):
        raise ValueError("Saved forecasts require the full approved analysis window.")
    if len(scoped) != report["transaction_lines"] or scoped.household_key.nunique() != report["households"] or not math.isclose(float(scoped.SALES_VALUE.sum()), report["revenue"], abs_tol=config.REVENUE_TOLERANCE_USD, rel_tol=0):
        raise ValueError("Requested transactions differ from the saved forecasting snapshot.")
    panel = pd.read_parquet(config.PROCESSED_DIR / "forecast_panel.parquet")
    future = predict_from_bundle(bundle, panel, commodity, config.FORECAST_HORIZON)
    holdout = pd.read_parquet(config.PROCESSED_DIR / "forecast_backtest.parquet")
    holdout = holdout.loc[holdout.COMMODITY_DESC.eq(commodity)].sort_values(["horizon", "origin_week"]).drop(columns="COMMODITY_DESC")
    evaluation = pd.read_csv(config.OUTPUTS_DIR / "forecast_metrics_by_category.csv")
    evaluation = evaluation.loc[evaluation.COMMODITY_DESC.eq(commodity)].drop(columns="COMMODITY_DESC")
    totals = pd.read_parquet(config.PROCESSED_DIR / "forecast_total_backtest.parquet")
    totals = totals.loc[totals.COMMODITY_DESC.eq(commodity)].drop(columns="COMMODITY_DESC")
    total_metrics = [{"model": name, **metrics(totals.actual_revenue, totals[column])}
                     for name, column in {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}.items()]
    weekly = pd.read_parquet(config.PROCESSED_DIR / "commodity_weekly.parquet")
    history = weekly.loc[weekly.in_window & weekly.COMMODITY_DESC.eq(commodity), ["WEEK_NO", "revenue"]].rename(columns={"WEEK_NO": "week"})
    return {"mode": "saved_direct_model", "currency": config.CURRENCY, "source_table": config.FORECAST_MODEL_SOURCE,
            "scope": f"Commodity {commodity}; approved weeks {start_week}-{end_week}; model history uses complete weeks {report['first_complete_week']}-{report['last_complete_week']}",
            "start_week": start_week, "end_week": end_week, "revenue_definition": "Sum of SALES_VALUE; no additional discount adjustment",
            "result_status": "Saved direct-horizon models and chronological baseline comparison passed independent validation",
            "category": commodity, "rows": records(future), "history": records(history),
            "holdout": records(holdout), "evaluation": records(evaluation),
            "four_week_totals": records(totals), "four_week_evaluation": total_metrics,
            "origin_week": report["last_complete_week"], "forecast_horizon": config.FORECAST_HORIZON,
            "forecast_total": float(future.forecast_revenue.sum()),
            "chosen_methods": {str(h): selection["serving_method"] for h, selection in bundle["selections"].items()},
            "model": "Direct horizons 1-4; method selected per horizon on earlier validation only; saved gradient boosting compared with three baselines",
            "model_validation_passed": True, "evaluation_protocol": report["schedule"],
            "excluded_partial_weeks": report["excluded_partial_weeks"], "seasonal_baseline_available": True,
            "note": "Revenue in USD, not physical unit demand. Four dataset weeks are a month proxy. Production models refit through the last complete week; reported accuracy comes from separate frozen pretest models. Test block 90-101 has 12/11/10/9 rolling origins at horizons 1/2/3/4; four-week totals use nine common origins. Baselines and model use identical forecast origins/targets. Validation selects methods without using held-out test errors; a baseline can be served where its validation result is better. Partial terminal week is excluded from training and can overlap the first forecast week. Synthetic calendar, short history, observed-sales promotion coverage and lack of uncertainty intervals limit interpretation."}
