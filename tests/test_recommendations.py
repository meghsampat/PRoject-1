"""Behavioral checks of independent candidate rankings, missingness and provisional actions."""
import copy
import unittest
import numpy as np
import pandas as pd
from src import config
from src.recommendations import select_target_segments,safe_growth,rank_candidates,combine,settings_fingerprint
from src.recommendation_evidence import validate_recommendation_evidence


def evidence_fixture():
    return pd.DataFrame({"COMMODITY_DESC":["A","B","C"],"product_score":[90.,80.,70.],
        "forecast_available":[True]*3,"forecast_growth":[.1,.2,-.2],
        "trailing_four_week_revenue":[100.]*3,"forecast_four_week_revenue":[110.,120.,80.],
        "target_affinity":[1.1,1.01,.99],"target_recent_momentum":[.1,0.,-.1],
        "target_previous_revenue":[100.]*3,"target_recent_revenue":[110.,100.,90.],
        "target_buyers":[100]*3,"forecast_total_WAPE_pct":[10.]*3,
        "promotion_association":[np.nan]*3,"promotion_evidence_available":[False]*3})


def tool_fixture():
    table=rank_candidates(evidence_fixture())
    records=table.astype(object).where(pd.notna(table),None).to_dict("records")
    return {"validation_passed":True,"business_usefulness_review_complete":False,
        "arbitration":{"selected_candidate":None},"weights":{"forecast":config.REC_FORECAST_WEIGHTS,"segment":config.REC_SEGMENT_WEIGHTS},
        "origin_week":101,"forecast_weeks":[102,103,104,105],"recent_weeks":[98,99,100,101],"previous_weeks":[94,95,96,97],
        "target_households":10,"target_segments":[{"households":10,"revenue_per_week_median_index":1.8}],
        "rows":records,"forecast_candidates_shown":3,"segment_candidates_shown":3,
        "candidate_counts":{"forecast":3,"segment":3},"shared_top10_categories":["A","B","C"],"top10_overlap_count":3}


class RecommendationTests(unittest.TestCase):
    def test_target_selection_follows_observed_spend_rule(self):
        profiles=pd.DataFrame({"segment":[1,2],"revenue_per_week_median_index":[.8,1.5]})
        self.assertEqual(select_target_segments(profiles).segment.tolist(),[2])
        with self.assertRaises(ValueError):
            select_target_segments(profiles.assign(revenue_per_week_median_index=1.))

    def test_zero_or_negative_growth_denominator_stays_unknown(self):
        actual=safe_growth(pd.Series([20.,20.,20.]),pd.Series([10.,0.,-10.]))
        self.assertEqual(actual.iloc[0],1)
        self.assertTrue(actual.iloc[1:].isna().all())

    def test_lists_use_separate_evidence(self):
        evidence=evidence_fixture()
        before=rank_candidates(evidence)
        evidence["forecast_growth"]=[1.,.01,.5]
        after=rank_candidates(evidence)
        for name in ["rank","recommendation_score","component_primary","component_secondary"]:
            a=before.loc[before.candidate.eq("segment")].set_index("COMMODITY_DESC")[name]
            b=after.loc[after.candidate.eq("segment")].set_index("COMMODITY_DESC")[name]
            pd.testing.assert_series_equal(a,b)
        evidence=evidence_fixture()
        evidence["target_affinity"]=[.9,1.2,1.5]
        changed=rank_candidates(evidence)
        a=before.loc[before.candidate.eq("forecast")].set_index("COMMODITY_DESC").recommendation_score
        b=changed.loc[changed.candidate.eq("forecast")].set_index("COMMODITY_DESC").recommendation_score
        pd.testing.assert_series_equal(a,b)

    def test_ineligible_candidates_retained_with_review_and_null_rank(self):
        evidence=evidence_fixture()
        evidence.loc[0,"forecast_available"]=False
        evidence.loc[1,"target_buyers"]=config.REC_MIN_TARGET_BUYERS-1
        table=rank_candidates(evidence)
        for method,category in [("forecast","A"),("segment","B")]:
            row=table.loc[table.candidate.eq(method)&table.COMMODITY_DESC.eq(category)].iloc[0]
            self.assertFalse(row.eligible)
            self.assertTrue(pd.isna(row["rank"]) and pd.isna(row.recommendation_score))
            self.assertEqual(row.priority_label,"review")
        self.assertTrue(table.promotion_association.isna().all())
        self.assertTrue(table.execution_status.eq("review_required").all())

    def test_large_forecast_error_forces_review_without_changing_score(self):
        before=rank_candidates(evidence_fixture())
        evidence=evidence_fixture()
        evidence["forecast_total_WAPE_pct"]=config.REC_MAX_FORECAST_WAPE+1
        after=rank_candidates(evidence)
        np.testing.assert_allclose(before.recommendation_score,after.recommendation_score)
        self.assertTrue(after.loc[after.candidate.eq("forecast"),"priority_label"].eq("review").all())

    def test_judge_validates_recommendation_route_and_withholds_edited_prose(self):
        from unittest.mock import patch
        from src.agents.forecast_agent import answer
        from src.judge import validate_answer
        from src.supervisor import route_question
        fixture=tool_fixture()
        fixture.update({"currency":"USD","source_table":config.REC_MODEL_SOURCE,"scope":"fixture",
                        "start_week":19,"end_week":102,"revenue_definition":"SALES_VALUE","result_status":"fixture"})
        with patch("src.tools.get_recommendations",return_value=fixture):
            response=answer("recommendations",None,None,19,102,None)
        decision=route_question("Which products should we promote next month?")
        self.assertTrue(validate_answer(response,decision,19,102)["accepted"])
        response["answer"]+=" This campaign guarantees a 30 percent profit increase."
        self.assertFalse(validate_answer(response,decision,19,102)["accepted"])

    def test_weights_reject_invalid_values(self):
        with self.assertRaises(ValueError):
            combine(pd.DataFrame({"a":[.5],"b":[.5]}),{"a":.7,"b":.7})
        with self.assertRaises(ValueError):
            combine(pd.DataFrame({"a":[np.nan],"b":[.5]}),{"a":.5,"b":.5})

    def test_evidence_rejects_changed_scores_growth_and_automatic_winner(self):
        fixture=tool_fixture()
        self.assertEqual(validate_recommendation_evidence(fixture),[])
        for field in ["recommendation_score","forecast_growth","target_recent_momentum"]:
            altered=copy.deepcopy(fixture)
            index = next(i for i,row in enumerate(altered["rows"]) if row["candidate"]==("segment" if field=="target_recent_momentum" else "forecast"))
            altered["rows"][index][field]+=1
            self.assertTrue(validate_recommendation_evidence(altered))
        altered=copy.deepcopy(fixture)
        altered["arbitration"]["selected_candidate"]="forecast"
        self.assertTrue(validate_recommendation_evidence(altered))


if __name__=="__main__":
    unittest.main()

