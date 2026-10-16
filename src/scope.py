"""Explicit scope decisions and gates. Unknown scope never becomes all-in-scope."""
import hashlib
import json
import pandas as pd
from src import config


class ScopeNotConfiguredError(ValueError):
    pass


def normalize_names(values):
    return [str(value).strip().upper() for value in values]


def current_scope_policy():
    return {
        "excluded_departments": config.EXCLUDED_DEPARTMENTS,
        "excluded_commodities": config.EXCLUDED_COMMODITIES,
        "drug_gm_review_commodities": config.DRUG_GM_REVIEW_COMMODITIES,
        "drug_gm_policy": config.DRUG_GM_POLICY,
        "weighted_commodities": config.WEIGHTED_COMMODITIES,
        "analysis_start_week": config.ANALYSIS_START_WEEK,
        "analysis_end_week": config.ANALYSIS_END_WEEK,
        "calendar_day_one": config.CALENDAR_DAY_ONE,
    }


def policy_fingerprint(policy=None):
    policy = current_scope_policy() if policy is None else policy
    serialized = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def scope_pending_reasons(policy=None):
    policy = current_scope_policy() if policy is None else policy
    reasons = []
    for key in ["excluded_departments", "excluded_commodities", "drug_gm_review_commodities"]:
        if policy.get(key) is None:
            reasons.append(f"Exact {key.replace('_', ' ')} list is missing")
    if policy.get("drug_gm_policy") not in {"keep", "exclude"}:
        reasons.append("DRUG GM review decision must be keep or exclude")
    return reasons


def apply_scope_policy(master, policy, products):
    """Return a nullable IN_SCOPE flag and review flags; never guess missing lists."""
    department = master.DEPARTMENT.astype("string").str.strip().str.upper()
    commodity = master.COMMODITY_DESC.astype("string").str.strip().str.upper()
    review_values = policy.get("drug_gm_review_commodities")
    if review_values is None:
        review = pd.Series(False, index=master.index, dtype="boolean")
        review.loc[department == "DRUG GM"] = pd.NA
    else:
        review_names = normalize_names(review_values)
        available = set(products.loc[products.DEPARTMENT.astype("string").str.strip().str.upper() == "DRUG GM", "COMMODITY_DESC"].astype("string").str.strip().str.upper())
        if set(review_names) - available:
            raise ValueError("DRUG GM review list contains names outside the lookup's DRUG GM department.")
        review = (department.eq("DRUG GM") & commodity.isin(review_names)).astype("boolean")
    for key, column in [("excluded_departments", "DEPARTMENT"), ("excluded_commodities", "COMMODITY_DESC")]:
        values = policy.get(key)
        if values is not None:
            known = set(products[column].astype("string").str.strip().str.upper())
            unknown = set(normalize_names(values)) - known
            if unknown:
                raise ValueError(f"Unknown {key}: {sorted(unknown)}")
    if scope_pending_reasons(policy):
        scope = pd.Series(pd.NA, index=master.index, dtype="boolean")
    else:
        scope = (~department.isin(normalize_names(policy["excluded_departments"])) & ~commodity.isin(normalize_names(policy["excluded_commodities"]))).astype("boolean")
        if policy["drug_gm_policy"] == "exclude":
            scope &= ~review
    return scope, review


def require_final_scope(master):
    if "IN_SCOPE" not in master or master.IN_SCOPE.isna().any():
        raise ScopeNotConfiguredError("FMCG scope is unresolved. Supply the exact department, commodity and DRUG GM review lists plus the keep/exclude decision in src/config.py, then rebuild the master. No scoped KPIs or aggregates were calculated.")
    if not pd.api.types.is_bool_dtype(master.IN_SCOPE):
        raise ScopeNotConfiguredError("IN_SCOPE must be a validated boolean flag.")
