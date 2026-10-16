"""Deterministic checks for the two separate evidence lists shown to a manager."""
import math
from numbers import Real
from src import config


def finite(value):
    return isinstance(value,Real) and not isinstance(value,bool) and math.isfinite(value)


def same(a,b):
    return finite(a) and finite(b) and math.isclose(a,b,abs_tol=1e-6,rel_tol=1e-9)


def validate_recommendation_evidence(evidence):
    errors = []
    if evidence.get("validation_passed") is not True or evidence.get("business_usefulness_review_complete") is not False:
        errors.append("Recommendation technical validation/review status is inconsistent.")
    if evidence["arbitration"].get("selected_candidate") is not None:
        errors.append("An automatic winner is unsupported by this two-list stage.")
    expected={"forecast":config.REC_FORECAST_WEIGHTS,"segment":config.REC_SEGMENT_WEIGHTS}
    if evidence["weights"]!=expected:
        errors.append("Recommendation weights differ from documented settings.")
    periods=evidence["forecast_weeks"]
    if periods!=list(range(evidence["origin_week"]+1,evidence["origin_week"]+config.FORECAST_HORIZON+1)):
        errors.append("Recommendation forecast period is inconsistent.")
    recent=list(range(evidence["origin_week"]-config.REC_RECENT_WEEKS+1,evidence["origin_week"]+1))
    previous=list(range(evidence["origin_week"]-2*config.REC_RECENT_WEEKS+1,evidence["origin_week"]-config.REC_RECENT_WEEKS+1))
    if evidence["recent_weeks"]!=recent or evidence["previous_weeks"]!=previous:
        errors.append("Recommendation momentum periods differ from source origin.")
    if evidence["target_households"]!=sum(row["households"] for row in evidence["target_segments"]) or any(row["revenue_per_week_median_index"]<config.REC_HIGH_SPEND_INDEX for row in evidence["target_segments"]):
        errors.append("Target group evidence does not support the spending rule.")
    top_sets={}
    for method,weights in expected.items():
        rows=[row for row in evidence["rows"] if row["candidate"]==method]
        count=evidence[method+"_candidates_shown"]
        if len(rows)!=count or count!=min(config.REC_DISPLAY_N,evidence["candidate_counts"][method]) or [row["rank"] for row in rows]!=list(range(1,count+1)):
            errors.append("Recommendation count/rank evidence is inconsistent.")
        top_sets[method]={row["COMMODITY_DESC"] for row in rows}
        if len(top_sets[method])!=len(rows) or any(a["recommendation_score"]<b["recommendation_score"] for a,b in zip(rows,rows[1:])):
            errors.append("Recommendation ordering/identities are inconsistent.")
        for row in rows:
            if row["eligible"] is not True or row["execution_status"]!="review_required":
                errors.append("Shown recommendations lack eligibility or required review status.")
            primary,secondary=row["component_primary"],row["component_secondary"]
            if not finite(primary) or not finite(secondary) or not 0<=primary<=1 or not 0<=secondary<=1:
                errors.append("Recommendation score components are invalid.")
                continue
            calculated=(primary*list(weights.values())[0]+secondary*list(weights.values())[1])*config.REC_SCORE_SCALE
            if not same(row["recommendation_score"],calculated):
                errors.append("Recommendation score does not match components.")
            before,after=row["trailing_four_week_revenue"],row["forecast_four_week_revenue"]
            if method=="forecast" and (before<=0 or not same(row["forecast_growth"],after/before-1)):
                errors.append("Forecast recommendation growth does not reconcile.")
            prior,now=row["target_previous_revenue"],row["target_recent_revenue"]
            if method=="segment" and (prior<=0 or not same(row["target_recent_momentum"],now/prior-1)):
                errors.append("Target group momentum does not reconcile.")
            if row["promotion_association"] is None and (row["promotion_evidence_available"] is not False or row["promotion_evidence_status"]!="unavailable"):
                errors.append("Missing promotion association was misrepresented.")
            if method=="forecast" and not same(secondary,row["product_score"]/config.CATEGORY_SCORE_SCALE):
                errors.append("Category-score component is inconsistent.")
            growth=row["forecast_growth"] if method=="forecast" else row["target_recent_momentum"]
            label="maintain"
            if growth < -config.REC_REVIEW_DECLINE:
                label="review"
            elif method=="forecast" and (row["forecast_total_WAPE_pct"] is None or row["forecast_total_WAPE_pct"]>config.REC_MAX_FORECAST_WAPE):
                label="review"
            elif row["rank"]<=config.REC_DISPLAY_N and growth>=config.REC_PROMOTE_GROWTH and (method=="forecast" or row["target_affinity"]>=config.REC_PROMOTE_AFFINITY):
                label="promote"
            if row["priority_label"]!=label:
                errors.append("Provisional recommendation label lacks its stated evidence.")
    shared=sorted(top_sets["forecast"]&top_sets["segment"])
    if shared!=evidence["shared_top10_categories"] or len(shared)!=evidence["top10_overlap_count"]:
        errors.append("Candidate-list overlap is inconsistent.")
    if len(evidence["rows"])!=sum(evidence[method+"_candidates_shown"] for method in expected):
        errors.append("Unexpected extra recommendation method.")
    return errors

