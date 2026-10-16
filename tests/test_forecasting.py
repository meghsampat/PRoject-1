"""Forecast leakage, horizon alignment, saved evidence, and chronology behavior."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from src import config
from src.forecast_features import build_feature_panel, split_schedule, training_rows, evaluation_rows, settings_fingerprint
from src.forecast_access import predict_from_bundle
from src.forecast_training import make_model, metrics


def weekly_fixture():
    rows=[]
    for category,scale in [("A",1.),("B",2.)]:
        for week in range(19,102):
            rows.append({"COMMODITY_DESC":category,"WEEK_NO":week,"revenue":scale*week})
    weekly=pd.DataFrame(rows)
    covariates=weekly[["COMMODITY_DESC","WEEK_NO"]].copy()
    covariates["loyalty_share"]=.2
    covariates["display_share"]=.3
    covariates["mailer_share"]=.4
    covariates["coverage_share"]=.8
    covariates["matched_keys"]=10
    return weekly,covariates


class ForecastTests(unittest.TestCase):
    def test_origin_features_ignore_future_revenue_and_promotions(self):
        weekly,covariates=weekly_fixture()
        before,categories,schedule=build_feature_panel(weekly,covariates)
        weekly.loc[weekly.WEEK_NO>89,"revenue"]*=100
        covariates.loc[covariates.WEEK_NO>89,"display_share"]=1
        after,again,_=build_feature_panel(weekly,covariates)
        self.assertEqual(categories,again)
        past=before.origin_week.le(89)
        pd.testing.assert_frame_equal(before.loc[past,config.FORECAST_FEATURES],after.loc[past,config.FORECAST_FEATURES])
        self.assertEqual(len(training_rows(before,4,89)),len(training_rows(after,4,89)))
        pd.testing.assert_series_equal(training_rows(before,4,89).normalized_target,training_rows(after,4,89).normalized_target)

    def test_direct_targets_training_cutoff_and_test_origin_counts(self):
        weekly,covariates=weekly_fixture()
        panel,_,schedule=build_feature_panel(weekly,covariates)
        self.assertEqual(schedule["eligibility_cutoff"],71)
        self.assertEqual(schedule["test_start"],90)
        for h in range(1,5):
            train=training_rows(panel,h,89)
            self.assertTrue((train.origin_week+h<=89).all())
            test=evaluation_rows(panel,h,90,101)
            self.assertEqual(len(test),2*(13-h))
            self.assertEqual(test.target_week.min(),89+h)
            self.assertEqual(test.target_week.max(),101)
        row=panel.loc[panel.COMMODITY_DESC.eq("A")&panel.origin_week.eq(89)&panel.horizon.eq(4)].iloc[0]
        self.assertEqual(row.actual_revenue,93)
        self.assertEqual(row.naive,89)
        self.assertEqual(row.seasonal_naive,41)
        self.assertEqual(row.moving_average,87.5)

    def test_eligibility_uses_only_initial_training_window(self):
        weekly,covariates=weekly_fixture()
        weekly.loc[weekly.COMMODITY_DESC.eq("B")&weekly.WEEK_NO.le(71),"revenue"]=0
        _,categories,_=build_feature_panel(weekly,covariates)
        self.assertEqual(categories,["A"])

    def test_unknown_promotions_are_not_zero_exposure(self):
        weekly,covariates=weekly_fixture()
        covariates["coverage_share"]=.1
        panel,_,_=build_feature_panel(weekly,covariates)
        self.assertTrue(panel.display_lag1.isna().all())
        self.assertTrue(panel.mailer_lag1.isna().all())
        self.assertTrue(panel.promo_unknown.eq(1).all())

    def test_no_sales_lines_preserve_unknown_discount_share(self):
        from src.build_forecasts import build_covariates
        complete=pd.DataFrame({"COMMODITY_DESC":["A"],"WEEK_NO":[19],"HAS_LOYALTY_DISC":[True]})
        weekly=pd.DataFrame({"COMMODITY_DESC":["A","B"],"WEEK_NO":[19,19]})
        exposure=weekly.copy()
        result=build_covariates(complete,weekly,exposure)
        self.assertEqual(result.loc[0,"loyalty_share"],1)
        self.assertTrue(pd.isna(result.loc[1,"loyalty_share"]))

    def test_saved_forecast_evidence_rejects_tampered_horizons_metrics_and_totals(self):
        from src.forecast_evidence import validate_saved_forecast
        holdout=[]
        methods={**config.FORECAST_METHODS,"Validation-selected forecast":"selected_forecast"}
        for h in range(1,5):
            for origin in range(89,102-h):
                holdout.append({"origin_week":origin,"target_week":origin+h,"horizon":h,"actual_revenue":10.,
                    "naive":11.,"seasonal_naive":11.,"moving_average":11.,"gradient_boosting":11.,
                    "selected_forecast":11.,"selected_method":"Gradient boosting"})
        evaluation=[]
        for h in range(1,5):
            rows=[row for row in holdout if row["horizon"]==h]
            evaluation.extend({"horizon":h,"model":name,**metrics([r["actual_revenue"] for r in rows],[r[column] for r in rows])} for name,column in methods.items())
        totals=[{"origin_week":origin,"actual_revenue":40.,**{column:44. for column in methods.values()}} for origin in range(89,98)]
        total_eval=[{"model":name,**metrics([r["actual_revenue"] for r in totals],[r[column] for r in totals])} for name,column in methods.items()]
        evidence={"model_validation_passed":True,"evaluation_protocol":{"test_start":90,"test_end":101,"evaluation_training_cutoff":89},
                  "origin_week":101,"holdout":holdout,"evaluation":evaluation,"four_week_totals":totals,
                  "four_week_evaluation":total_eval,"chosen_methods":{str(h):"Gradient boosting" for h in range(1,5)},
                  "rows":[{"horizon":h,"selected_method":"Gradient boosting","forecast_revenue":11.,"trained_revenue":11.} for h in range(1,5)]}
        self.assertEqual(validate_saved_forecast(evidence),[])
        for section,key in [("holdout","target_week"),("evaluation","WAPE_pct"),("four_week_totals","actual_revenue"),("rows","forecast_revenue")]:
            altered=copy.deepcopy(evidence)
            altered[section][0][key]+=1
            self.assertTrue(validate_saved_forecast(altered))

    def test_gap_and_invalid_horizon_rejected(self):
        with self.assertRaises(ValueError):
            split_schedule([week for week in range(19,102) if week!=50])
        for horizon in [0,5,True,1.5]:
            with self.assertRaises(ValueError):
                predict_from_bundle({"categories":["A"]},pd.DataFrame(),"A",horizon)

    def test_random_early_stopping_disabled_and_settings_tracked(self):
        model=make_model(config.FORECAST_PARAMS[0])
        self.assertIs(model.early_stopping,False)
        self.assertEqual(model.random_state,42)
        before=settings_fingerprint()
        with patch("src.config.FORECAST_VALIDATION_WEEKS",7):
            self.assertNotEqual(before,settings_fingerprint())

    def test_metrics_zero_denominators_and_nonfinite_inputs(self):
        result=metrics([0,0],[1,1])
        self.assertIsNone(result["WAPE_pct"])
        self.assertIsNone(result["MAPE_pct"])
        self.assertEqual(result["MAE"],1)
        with self.assertRaises(ValueError):
            metrics([1],[np.nan])


if __name__=="__main__":
    unittest.main()

