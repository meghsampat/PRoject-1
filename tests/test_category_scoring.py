"""Checks of category denominators, missingness and promotion support behavior."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from src import config
from src.category_scoring import category_indicators, rank_normalize, weighted_scores, score_categories, weight_sensitivity
from src.promotion_support import summarize_matches, guarded_contrast
from src.judge import validate_answer
from src.supervisor import route_question


class CategoryTests(unittest.TestCase):
    def test_normalization_preserves_ties_and_unknown_values(self):
        values = pd.Series([1., 1., 3., np.nan])
        np.testing.assert_allclose(rank_normalize(values), [.25, .25, 1, .5])
        np.testing.assert_allclose(rank_normalize(pd.Series([7., 7., np.nan])), [.5, .5, .5])

    def test_settings_fingerprint_tracks_score_policy(self):
        from src.category_scoring import settings_fingerprint
        before = settings_fingerprint()
        with patch("src.config.CATEGORY_NEUTRAL_COMPONENT", .25):
            self.assertNotEqual(before, settings_fingerprint())
        self.assertEqual(before, settings_fingerprint())

    def test_invalid_weights_and_normalized_values_are_rejected(self):
        normalized = pd.DataFrame({name: [.5] for name in config.CATEGORY_WEIGHTS})
        weights = dict(config.CATEGORY_WEIGHTS)
        weights["growth"] += .1
        with self.assertRaises(ValueError):
            weighted_scores(normalized, weights)
        normalized.iloc[0, 0] = np.nan
        with self.assertRaises(ValueError):
            weighted_scores(normalized, config.CATEGORY_WEIGHTS)

    def test_exposure_unknown_denominator_and_multiple_codes(self):
        matches = pd.DataFrame({"COMMODITY_DESC": ["A"]*3, "WEEK_NO": [1]*3,
                    "PRODUCT_ID": [1,2,3], "source_records": [2,1,0],
                    "display_mask": [1|2, 1, 0], "mailer_mask": [1,2,0]})
        grid = pd.DataFrame({"COMMODITY_DESC": ["A","A"], "WEEK_NO": [1,2]})
        result = summarize_matches(matches, grid)
        self.assertEqual(result.iloc[0].sales_keys, 3)
        self.assertAlmostEqual(result.iloc[0].coverage_share, 2/3)
        self.assertEqual(result.iloc[0].display_share, .5)
        self.assertEqual(result.iloc[0].any_promo_share, 1)
        self.assertTrue(pd.isna(result.iloc[1].any_promo_share))

    def test_repeat_requires_distinct_weeks_and_growth_uses_weekly_means(self):
        window = pd.DataFrame({"COMMODITY_DESC":["A"]*4, "household_key":[1,1,2,2],
                  "WEEK_NO":[1,1,1,2], "BASKET_ID":[1,2,3,4], "SALES_VALUE":[10.]*4})
        weekly = pd.DataFrame({"COMMODITY_DESC":["A"]*3, "WEEK_NO":[1,2,3], "revenue":[30.,10.,20.]})
        daily = pd.DataFrame({"COMMODITY_DESC":["A"]*3, "DATE":pd.date_range("2016-01-01",periods=3),
                  "DAY":[1,2,3], "revenue":[30.,10.,20.]})
        row = category_indicators(window, weekly, daily).iloc[0]
        self.assertEqual(row.repeat_buyers, 1)
        self.assertEqual(row.repeat_purchase_rate, .5)
        self.assertEqual(row.first_half_weekly_revenue, 30)
        self.assertEqual(row.second_half_weekly_revenue, 15)
        self.assertEqual(row.growth, -.5)

    def test_shrinkage_and_seasonal_or_sparse_comparators(self):
        revenue = pd.Series([10.]*8 + [20.]*8)
        high = pd.Series([False]*8 + [True]*8)
        raw, shrunk, reason = guarded_contrast(revenue, high, ~high, True)
        self.assertEqual(raw, 1)
        self.assertEqual(shrunk, .4)
        self.assertEqual(reason, "eligible")
        self.assertTrue(np.isnan(guarded_contrast(revenue, high, ~high, False)[1]))
        self.assertTrue(np.isnan(guarded_contrast(revenue.head(4), high.head(4), ~high.head(4), True)[1]))

    def test_seeded_sensitivity_is_reproducible(self):
        components = pd.DataFrame({"COMMODITY_DESC":[f"C{i}" for i in range(30)],
                                 "score_eligible":[True]*30})
        for name in config.CATEGORY_WEIGHTS:
            components[name] = np.arange(30, dtype=float)
        scores = score_categories(components)
        runs, ranges = weight_sensitivity(scores)
        again, again_ranges = weight_sensitivity(scores)
        pd.testing.assert_frame_equal(runs, again)
        pd.testing.assert_frame_equal(ranges, again_ranges)
        np.testing.assert_allclose(runs.spearman_all, 1)
        np.testing.assert_allclose(runs.top20_overlap_share, 1)

    def test_judge_rejects_tampered_composite_scores(self):
        from src.agents.data_science_agent import answer
        evidence = {"currency":"USD", "source_table":config.CATEGORY_MODEL_SOURCE,
             "scope":"fixture", "start_week":19, "end_week":102,
             "revenue_definition":"SALES_VALUE", "result_status":"fixture",
             "categories_shown":1, "categories_scored":100, "top_score":50.,
             "weights":config.CATEGORY_WEIGHTS, "scoring_validation_passed":True,
             "rows":[{"COMMODITY_DESC":"A","rank":1,"score":50.,
                      **{"normalized_"+name:.5 for name in config.CATEGORY_WEIGHTS}}]}
        with patch("src.tools.get_category_intelligence", return_value=evidence):
            response = answer("category_intelligence", None, None, 19, 102)
        decision = route_question("Show category intelligence")
        self.assertTrue(validate_answer(response, decision, 19, 102)["accepted"])
        response["evidence"]["rows"][0]["score"] = 99.
        self.assertFalse(validate_answer(response, decision, 19, 102)["accepted"])


if __name__ == "__main__":
    unittest.main()

