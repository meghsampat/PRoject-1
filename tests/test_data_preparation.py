"""Preparation behavior checks. Fixtures are synthetic test data, never project results."""
import copy
import unittest
import numpy as np
import pandas as pd
from src import config
from src.aggregation import build_aggregate_frames
from src.preprocessing import prepare_master
from src.scope import ScopeNotConfiguredError, require_final_scope, scope_pending_reasons


def test_products():
    return pd.DataFrame({
        "PRODUCT_ID": [100, 101, 102, 103], "MANUFACTURER": [1, 1, 1, 1],
        "DEPARTMENT": ["GROCERY", "DRUG GM", "GROCERY", "OTHER"],
        "BRAND": ["National"] * 4,
        "COMMODITY_DESC": ["MILK", "SOAP", "COINS", "OTHER GOODS"],
        "SUB_COMMODITY_DESC": ["MILK", "SOAP", "COINS", "OTHER"],
        "CURR_SIZE_OF_PRODUCT": ["1 LB"] * 4,
    })


def test_policy(pending=False):
    return {"excluded_departments": None if pending else ["OTHER"],
            "excluded_commodities": None if pending else ["COINS"],
            "drug_gm_review_commodities": None if pending else ["SOAP"],
            "drug_gm_policy": None if pending else "exclude",
            "weighted_commodities": None, "calendar_day_one": config.CALENDAR_DAY_ONE,
            "analysis_start_week": config.ANALYSIS_START_WEEK, "analysis_end_week": None}


def test_raw(days=12):
    rows = []
    for day in range(1, days + 1):
        rows.append({"household_key": day % 3 + 1, "BASKET_ID": 1000 + day,
                     "DAY": day, "PRODUCT_ID": 100 if day % 5 else 101,
                     "QUANTITY": 1, "SALES_VALUE": float(day % 7 + 1),
                     "STORE_ID": 1, "RETAIL_DISC": -0.5, "TRANS_TIME": 1200,
                     "WEEK_NO": (day + 1) // 7 + 1,
                     "COUPON_DISC": 0., "COUPON_MATCH_DISC": 0.})
    return pd.DataFrame(rows)


class DataPreparationTests(unittest.TestCase):
    def test_only_joint_zero_lines_are_removed(self):
        raw = test_raw()
        raw.loc[0, ["QUANTITY", "SALES_VALUE"]] = [0, 0]
        raw.loc[1, ["QUANTITY", "SALES_VALUE"]] = [0, 5]
        raw.loc[2, ["QUANTITY", "SALES_VALUE"]] = [1, 0]
        raw.loc[3, ["QUANTITY", "SALES_VALUE"]] = [-1, -2]
        master, removed, report = prepare_master(raw, test_products(), test_policy())
        self.assertEqual(removed.SOURCE_ROW_ID.tolist(), [0])
        self.assertEqual(len(master) + len(removed), len(raw))
        self.assertAlmostEqual(master.SALES_VALUE.sum(), raw.SALES_VALUE.sum())
        self.assertEqual(master.ZERO_QTY_NONZERO_SALES.sum(), 1)
        self.assertEqual(master.IS_FREE_ITEM.sum(), 1)
        self.assertEqual(master.NEGATIVE_SALES.sum(), 1)
        self.assertEqual(master.NEGATIVE_QUANTITY.sum(), 1)
        self.assertEqual(report["removed_sales_value_usd"], 0)
        self.assertTrue(master.loc[master.QUANTITY.le(0), "UNIT_PRICE_PAID"].isna().all())

    def test_unknown_scope_is_nullable_and_blocks_aggregates(self):
        master, _, report = prepare_master(test_raw(), test_products(), test_policy(pending=True))
        self.assertTrue(master.IN_SCOPE.isna().all())
        self.assertTrue(master.UNIT_PRICE_PAID.isna().all())
        self.assertTrue(master.IS_WEIGHTED.isna().all())
        self.assertEqual(report["status"], "SCOPE_PENDING")
        with self.assertRaises(ScopeNotConfiguredError):
            require_final_scope(master)
        with self.assertRaises(ScopeNotConfiguredError):
            build_aggregate_frames(master)

    def test_scope_rules_and_drug_gm_decision(self):
        raw = test_raw()
        raw.loc[:3, "PRODUCT_ID"] = [100, 101, 102, 103]
        master, _, _ = prepare_master(raw, test_products(), test_policy())
        self.assertEqual(master.IN_SCOPE.head(4).tolist(), [True, False, False, False])
        policy = test_policy()
        policy["drug_gm_policy"] = "keep"
        master, _, _ = prepare_master(raw, test_products(), policy)
        self.assertTrue(master.IN_SCOPE.iloc[1])
        self.assertTrue(master.DRUG_GM_REVIEW.iloc[1])

    def test_unknown_scope_names_are_rejected(self):
        policy = test_policy()
        policy["excluded_departments"] = ["TYPO DEPARTMENT"]
        with self.assertRaises(ValueError):
            prepare_master(test_raw(), test_products(), policy)

    def test_calendar_anchor_and_partial_first_week(self):
        master, _, report = prepare_master(test_raw(), test_products(), test_policy())
        self.assertEqual(str(master.DATE.iloc[0].date()), "2015-12-30")
        self.assertEqual(master.loc[master.DAY.eq(6), "DATE"].iloc[0].dayofweek, 0)
        self.assertFalse(master.loc[master.WEEK_NO.eq(1), "IS_COMPLETE_WEEK"].any())
        self.assertTrue(master.loc[master.WEEK_NO.eq(2), "IS_COMPLETE_WEEK"].all())
        self.assertEqual(report["calendar_week_line_mismatches"], 0)
        raw = test_raw()
        raw.loc[0, "WEEK_NO"] = 2
        with self.assertRaises(ValueError):
            prepare_master(raw, test_products(), test_policy())

    def test_duplicate_or_missing_lookup_is_rejected(self):
        products = test_products()
        with self.assertRaises(ValueError):
            prepare_master(test_raw(), pd.concat([products, products.iloc[:1]]), test_policy())
        raw = test_raw()
        raw.loc[0, "PRODUCT_ID"] = 999
        with self.assertRaises(ValueError):
            prepare_master(raw, products, test_policy())

    def test_zero_filled_grids_and_correct_revenue_benchmarks(self):
        raw = test_raw(days=173)  # Partial week 1, followed by full weeks 2..25.
        policy = test_policy()
        policy["drug_gm_policy"] = "keep"
        master, _, _ = prepare_master(raw, test_products(), policy)
        daily, weekly, households, kpis, benchmarks = build_aggregate_frames(master)
        scoped = master.loc[master.IN_SCOPE]
        window = scoped.loc[config.in_analysis_window(scoped)]
        self.assertEqual(len(daily), 2 * 173)
        self.assertEqual(len(weekly), 2 * 24)
        self.assertTrue(daily.transaction_lines.eq(0).any())
        self.assertAlmostEqual(daily.revenue.sum(), scoped.SALES_VALUE.sum())
        self.assertAlmostEqual(weekly.revenue.sum(), scoped.loc[scoped.IS_COMPLETE_WEEK, "SALES_VALUE"].sum())
        self.assertAlmostEqual(households.revenue.sum(), window.SALES_VALUE.sum())
        self.assertAlmostEqual(kpis["revenue"], window.SALES_VALUE.sum())
        self.assertEqual(kpis["households"], window.household_key.nunique())
        self.assertEqual(kpis["baskets"], window.BASKET_ID.nunique())
        self.assertEqual(kpis["analysis_start_week"], 19)
        self.assertTrue(np.allclose(households.revenue_per_week, households.revenue / households.observed_weeks))
        self.assertLess(benchmarks["weekly_full_weeks_in_scope_revenue"], benchmarks["daily_all_in_scope_revenue"])

    def test_empty_list_is_an_explicit_decision_not_unknown(self):
        policy = test_policy()
        policy["excluded_departments"] = []
        policy["excluded_commodities"] = []
        policy["drug_gm_review_commodities"] = []
        policy["drug_gm_policy"] = "keep"
        self.assertEqual(scope_pending_reasons(policy), [])
        master, _, _ = prepare_master(test_raw(), test_products(), policy)
        self.assertTrue(master.IN_SCOPE.all())


if __name__ == "__main__":
    unittest.main()
