"""Review report accuracy and preservation of the original presentation."""
import tempfile
import unittest
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
from src import config
from src.review3_presentation import replace_paragraph, paragraph_text, build_deck
from src.review3_values import calculate_values


class Review3Tests(unittest.TestCase):
    def test_text_replacement_escapes_xml_and_retains_run_style(self):
        source = '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:pPr lvl="1"/><a:r><a:rPr b="1" sz="2000"/><a:t>Value </a:t></a:r><a:r><a:t>[__]</a:t></a:r></a:p>'
        result = replace_paragraph(source, "USD 12.00 & under <20")
        ET.fromstring(result)
        self.assertEqual(paragraph_text(result), "USD 12.00 & under <20")
        self.assertIn('b="1" sz="2000"', result)
        self.assertIn('<a:pPr lvl="1"/>', result)
        self.assertEqual(result.count("<a:r>"), source.count("<a:r>"))

    def test_presentation_writer_refuses_overwriting_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "original.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("fixture", b"original")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                build_deck(path, path, {})
            self.assertEqual(path.read_bytes(), before)

    def test_discount_share_and_rule_means_are_not_cluster_counts_or_unit_prices(self):
        data = pd.DataFrame({"household_key": [1, 2, 3, 4], "BASKET_ID": [10, 20, 30, 40],
            "IN_SCOPE": [True] * 4, "WEEK_NO": [19, 19, 20, 20], "IS_COMPLETE_WEEK": [True] * 4,
            "SALES_VALUE": [10., 20., 30., 40.], "DEPARTMENT": ["A", "B", "A", "B"],
            "RETAIL_DISC": [0., -1., 0., 0.], "COUPON_DISC": [0.] * 4,
            "COUPON_MATCH_DISC": [0., 0., 0., -1.],
            "HAS_LOYALTY_DISC": [False, True, False, False], "HAS_COUPON": [False, False, False, True]})
        rfm = pd.DataFrame({"household_key": [1, 2, 3, 4], "revenue": [10., 20., 30., 40.],
                            "rule_segment": list(config.REVIEW3_RULE_ORDER)})
        profiles = pd.DataFrame({"segment": [1, 2], "households": [2, 2], "revenue": [30., 70.]})
        scores = pd.DataFrame({"COMMODITY_DESC": ["A", "B"], "rank": [1, 2], "score": [80., 70.]})
        panel = pd.DataFrame({"horizon": [1], "target_week": [20], "actual_revenue": [10.]})
        forecast = {"overall_metrics": [{"horizon": 1, "model": "Gradient boosting"}], "forecastable_categories": 2,
                    "four_week_total_metrics": [], "schedule": {"evaluation_training_cutoff": 20, "test_start": 21, "test_end": 24}}
        master = {"retained_transaction_lines": 4, "removed_zero_quantity_and_zero_sales_lines": 1,
                  "households_in_retained_unscoped_data": 4}
        v = calculate_values(data, rfm, scores, profiles, panel, forecast, master, {"verification": {}})
        self.assertEqual(v["discounted_sales_share_pct"], 60)
        self.assertEqual(v["chosen_k"], 2)
        self.assertEqual(len(v["rfm_rule_groups"]), 4)
        self.assertEqual(v["rfm_rule_groups"][config.REVIEW3_RULE_ORDER[2]]["mean_window_spend"], 30)
        self.assertEqual(v["average_basket_value_usd"], 25)
        contaminated = data.copy()
        contaminated.loc[0, "IN_SCOPE"] = False
        with self.assertRaises(ValueError):
            calculate_values(contaminated, rfm, scores, profiles, panel, forecast, master, {"verification": {}})


if __name__ == "__main__":
    unittest.main()
