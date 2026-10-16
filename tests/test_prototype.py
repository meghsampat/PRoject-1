"""Behavioral checks for scoped analytics and evidence handling."""
import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from src.agents.data_science_agent import answer
from src.config import DEMO_QUESTIONS
from src.judge import validate_answer
from src.supervisor import route_question
from src.tools import forecast_demand, forecast_metrics, get_customer_segments, get_product_performance, get_sales_trend, query_sales_kpis, resolve_category


def sample_transactions():
    return pd.DataFrame({
        "household_key": [1, 1, 2, 2], "BASKET_ID": [10, 10, 20, 30],
        "PRODUCT_ID": [100, 100, 101, 101], "WEEK_NO": [1, 1, 2, 3],
        "DAY": [1, 1, 8, 15], "QUANTITY": [1, -1, 2, 1],
        "SALES_VALUE": [10., -2., 6., 4.], "IN_SCOPE": [True] * 4,
    })


def sample_products():
    return pd.DataFrame({"PRODUCT_ID": [100, 101], "COMMODITY_DESC": ["FLUID MILK PRODUCTS", "BREAD"], "SUB_COMMODITY_DESC": ["MILK", "BREAD"]})


def weekly_fixture(weeks=40):
    rows = []
    for week in range(1, weeks + 1):
        for day in range(1, 8):
            rows.append({"WEEK_NO": week, "DAY": (week - 1) * 7 + day,
                         "PRODUCT_ID": 100, "household_key": 1,
                         "BASKET_ID": week * 100 + day, "QUANTITY": 1,
                         "SALES_VALUE": float(week)})
    return pd.DataFrame(rows).assign(IN_SCOPE=True)


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        # Early-week synthetic fixtures deliberately use a test-only window.
        self.enterContext(patch("src.config.ANALYSIS_START_WEEK", 1))

    def test_demo_routing(self):
        intents = ["sales_kpis", "sales_trend", "top_products", "customer_segments", "category_intelligence", "week_diagnosis", "recommendations", "forecast"]
        self.assertEqual(len(DEMO_QUESTIONS), len(intents))
        for question, expected in zip(DEMO_QUESTIONS, intents):
            self.assertEqual(route_question(question)["intent"], expected)
        self.assertEqual(route_question("  SHOW Weekly SALES Trend! ")["intent"], "sales_trend")

    def test_unsupported_filters_and_multiple_tasks_are_rejected(self):
        for question in ["", "Show sales KPIs for milk", "Show weekly sales trend for store 1", "Show top products and customer segments", "Forecast milk and bread revenue for next month", "Delete all files"]:
            with self.subTest(question=question), self.assertRaises(ValueError):
                route_question(question)

    def test_kpis_retain_negative_lines_and_count_distinct_baskets(self):
        result = query_sales_kpis(sample_transactions(), 1, 1)
        self.assertEqual(result["revenue"], 8)
        self.assertEqual(result["average_basket_value"], 8)
        self.assertEqual(result["baskets"], 1)
        self.assertEqual(result["transaction_lines"], 2)
        self.assertEqual(result["anomalies"]["negative_sales_lines"], 1)

    def test_tools_require_scope_and_filter_out_of_scope_lines(self):
        data = sample_transactions()
        data.loc[2, "IN_SCOPE"] = False
        self.assertEqual(query_sales_kpis(data, 1, 3)["revenue"], 12)
        with patch("src.config.ANALYSIS_START_WEEK", 2):
            self.assertEqual(query_sales_kpis(sample_transactions(), 2, 3)["revenue"], 10)
        with self.assertRaises(ValueError):
            query_sales_kpis(data.drop(columns="IN_SCOPE"), 1, 3)
        data["IN_SCOPE"] = pd.Series(pd.NA, index=data.index, dtype="boolean")
        with self.assertRaises(ValueError):
            query_sales_kpis(data, 1, 3)
    def test_invalid_scope(self):
        for bounds in [(3, 1), (0, 2), (1, 4), (1.5, 2), (True, 2)]:
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                query_sales_kpis(sample_transactions(), *bounds)

    def test_trend_and_products_reconcile(self):
        data = sample_transactions()
        trend = get_sales_trend(data, 1, 3)
        self.assertEqual(sum(row["revenue"] for row in trend["rows"]), 18)
        products = get_product_performance(data, sample_products(), 1, 3)
        self.assertEqual(products["rows"][0]["PRODUCT_ID"], 101)
        self.assertEqual(products["rows"][0]["revenue"], 10)
        missing = sample_products().iloc[:1]
        with self.assertRaises(ValueError):
            get_product_performance(data, missing, 1, 3)

    def test_category_alias_and_ambiguity(self):
        products = sample_products()
        self.assertEqual(resolve_category(products, "milk"), "FLUID MILK PRODUCTS")
        products.loc[len(products)] = [102, "BREAD ROLLS", "ROLLS"]
        self.assertEqual(resolve_category(products, "bread"), "BREAD")
        with self.assertRaises(ValueError):
            resolve_category(products, "bre")
        with self.assertRaises(ValueError):
            resolve_category(products, "unknown commodity")

    def test_judge_rejects_unsupported_numeric_claim(self):
        decision = route_question(DEMO_QUESTIONS[0])
        response = answer("sales_kpis", sample_transactions(), None, 1, 3)
        self.assertTrue(validate_answer(response, decision, 1, 3)["accepted"])
        altered = copy.deepcopy(response)
        altered["claims"]["revenue"] = 1000000
        self.assertFalse(validate_answer(altered, decision, 1, 3)["accepted"])
        altered = copy.deepcopy(response)
        altered["evidence"]["average_basket_value"] = 1
        altered["claims"]["average_basket_value"] = 1
        self.assertFalse(validate_answer(altered, decision, 1, 3)["accepted"])
        self.assertFalse(validate_answer(response, decision, 2, 3)["accepted"])

    def test_judge_rejects_edited_prose_and_malformed_evidence(self):
        decision = route_question(DEMO_QUESTIONS[0])
        response = answer("sales_kpis", sample_transactions(), None, 1, 3)
        response["answer"] += " Revenue will grow 99 percent."
        self.assertFalse(validate_answer(response, decision, 1, 3)["accepted"])
        response["evidence"] = "unstructured output"
        self.assertFalse(validate_answer(response, decision, 1, 3)["accepted"])
        self.assertFalse(validate_answer(None, decision, 1, 3)["accepted"])

    def test_judge_rejects_fabricated_forecast_accuracy(self):
        from src.agents.forecast_agent import answer as forecast_answer
        decision = route_question(DEMO_QUESTIONS[-1])
        response = forecast_answer("forecast", weekly_fixture(), sample_products(), 1, 40, "milk")
        self.assertTrue(validate_answer(response, decision, 1, 40)["accepted"])
        response["evidence"]["evaluation"][0]["MAE"] = 0
        self.assertFalse(validate_answer(response, decision, 1, 40)["accepted"])
    def test_forecast_complete_weeks_and_baseline_comparison(self):
        data = weekly_fixture()
        partial = data.tail(3).copy()
        partial["WEEK_NO"] = 41
        partial["DAY"] = [281, 282, 283]
        data = pd.concat([data, partial], ignore_index=True)
        result = forecast_demand(data, sample_products(), 1, 41, "milk")
        json.dumps(result, allow_nan=False)  # Tools must be persistable as strict JSON.
        self.assertEqual(result["excluded_partial_weeks"], [41])
        self.assertEqual(result["origin_week"], 40)
        self.assertEqual(len(result["holdout"]), 12)
        self.assertEqual([row["week"] for row in result["rows"]], [41, 42, 43, 44])
        self.assertEqual(result["rows"][0]["forecast_revenue"], np.mean([37, 38, 39, 40]) * 7)
        self.assertEqual({row["model"] for row in result["evaluation"]}, {"Naive", "Four-week moving average"})
        self.assertEqual(result["evaluation"][0]["MAE"], 7)

    def test_forecast_has_no_future_leakage(self):
        data = weekly_fixture()
        before = forecast_demand(data, sample_products(), 1, 40, "milk")
        changed = data.copy()
        changed.loc[changed.WEEK_NO >= 29, "SALES_VALUE"] *= 100
        after = forecast_demand(changed, sample_products(), 1, 40, "milk")
        for key in ["naive", "moving_average"]:
            self.assertEqual(before["holdout"][0][key], after["holdout"][0][key])
        self.assertNotEqual(before["holdout"][0]["actual_revenue"], after["holdout"][0]["actual_revenue"])

    def test_forecast_rejects_short_or_gapped_history(self):
        with self.assertRaises(ValueError):
            forecast_demand(weekly_fixture(20), sample_products(), 1, 20, "milk")
        data = weekly_fixture()
        data = data[data.WEEK_NO != 20]
        with self.assertRaises(ValueError):
            forecast_demand(data, sample_products(), 1, 40, "milk")

    def test_zero_metric_denominators(self):
        result = forecast_metrics([0, 0], [1, 1])
        self.assertIsNone(result["MAPE_pct"])
        self.assertIsNone(result["WAPE_pct"])
        self.assertEqual(result["MAE"], 1)

    def test_segmentation_is_reproducible_and_accounts_for_households(self):
        rows = []
        for household in range(1, 25):
            for visit in range(1, household % 5 + 2):
                rows.append({"household_key": household, "BASKET_ID": household * 100 + visit,
                             "PRODUCT_ID": 100, "WEEK_NO": 1 if visit < 3 else 2,
                             "DAY": household % 4 + visit, "QUANTITY": 1,
                             "SALES_VALUE": float(household * visit)})
        data = pd.DataFrame(rows).assign(IN_SCOPE=True)
        first = get_customer_segments(data, 1, 2)
        second = get_customer_segments(data, 1, 2)
        self.assertEqual(first["rows"], second["rows"])
        self.assertEqual(sum(row["households"] for row in first["rows"]), 24)
        self.assertAlmostEqual(sum(row["revenue"] for row in first["rows"]), data.SALES_VALUE.sum())


if __name__ == "__main__":
    unittest.main()







