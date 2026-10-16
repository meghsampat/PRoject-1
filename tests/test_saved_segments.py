"""RFM behavior checks and saved-model numerical round-trip on test fixtures."""
import pickle
import unittest
import numpy as np
import pandas as pd
from src.rfm import build_rfm, percentile_scores
from src.segmentation import assign_segment, fit_segmentation
from src.segment_access import artifact_path


class SegmentationTests(unittest.TestCase):
    def test_tied_scores_are_order_independent_and_recency_reversed(self):
        values = pd.Series([0, 0, 1, 5, 30, 90])
        scores = percentile_scores(values, lower_is_better=True)
        self.assertEqual(scores.iloc[0], scores.iloc[1])
        self.assertGreater(scores.iloc[0], scores.iloc[-1])
        shuffled = values.sample(frac=1, random_state=42)
        pd.testing.assert_series_equal(scores, percentile_scores(shuffled, True).sort_index())
        constant = percentile_scores(pd.Series([5.] * 10))
        self.assertEqual(constant.nunique(), 1)

    def test_negative_missing_and_duplicate_features_are_rejected(self):
        frame = pd.DataFrame({"household_key": [1, 2], "recency_days": [0, 5], "baskets_per_week": [1., 2.], "revenue_per_week": [10., 20.]})
        changed = frame.copy()
        changed.loc[0, "revenue_per_week"] = -1
        with self.assertRaises(ValueError):
            build_rfm(changed)
        changed.loc[0, "revenue_per_week"] = np.nan
        with self.assertRaises(ValueError):
            build_rfm(changed)
        changed = frame.copy()
        changed["household_key"] = 1
        with self.assertRaises(ValueError):
            build_rfm(changed)

    def test_pickle_reload_and_single_household_inference_reproduce_labels(self):
        low = pd.DataFrame({"household_key": range(30), "recency_days": np.arange(30) % 3,
                            "baskets_per_week": 0.1 + np.arange(30) / 1000, "revenue_per_week": 2 + np.arange(30) / 100})
        high = pd.DataFrame({"household_key": range(30, 60), "recency_days": 50 + np.arange(30) % 3,
                             "baskets_per_week": 4 + np.arange(30) / 1000, "revenue_per_week": 100 + np.arange(30) / 100})
        rfm = build_rfm(pd.concat([low, high], ignore_index=True))
        fit = fit_segmentation(rfm)
        scaler = pickle.loads(pickle.dumps(fit["scaler"]))
        model = pickle.loads(pickle.dumps(fit["model"]))
        actual = model.predict(scaler.transform(np.log1p(rfm[["recency_days", "baskets_per_week", "revenue_per_week"]])))
        self.assertTrue(np.array_equal(actual, fit["labels"]))
        first = rfm.iloc[0]
        self.assertEqual(assign_segment(first.recency_days, first.baskets_per_week, first.revenue_per_week, scaler, model), int(actual[0]) + 1)
        with self.assertRaises(ValueError):
            assign_segment(-1, 1, 10, scaler, model)
        self.assertTrue(fit["evaluation"].loc[fit["evaluation"].k.eq(fit["chosen_k"]), "eligible"].iloc[0])

    def test_constant_features_do_not_force_clusters(self):
        frame = pd.DataFrame({"household_key": range(10), "recency_days": 0, "baskets_per_week": 1., "revenue_per_week": 10.})
        with self.assertRaises(ValueError):
            fit_segmentation(build_rfm(frame))

    def test_model_artifact_names_are_restricted(self):
        with self.assertRaises(ValueError):
            artifact_path("../config.py")
        with self.assertRaises(ValueError):
            artifact_path("other_model.pkl")


if __name__ == "__main__":
    unittest.main()
