"""Generate a reviewable scope configuration from explicit selections."""
from src.scope import apply_scope_policy, current_scope_policy, normalize_names


def make_scope_proposal(departments, commodities, drug_gm_commodities, drug_gm_policy, products):
    """Validate names and return a draft. This function never modifies configuration."""
    selections = [departments, commodities, drug_gm_commodities]
    if any(not isinstance(values, list) or any(not isinstance(value, str) for value in values) for values in selections):
        raise ValueError("Each selection must be an explicit list of names; unknown lists are not allowed.")
    if drug_gm_policy not in {"keep", "exclude"}:
        raise ValueError("Choose whether to keep or exclude the selected DRUG GM commodities.")
    policy = current_scope_policy()
    policy.update({
        "excluded_departments": sorted(set(normalize_names(departments))),
        "excluded_commodities": sorted(set(normalize_names(commodities))),
        "drug_gm_review_commodities": sorted(set(normalize_names(drug_gm_commodities))),
        "drug_gm_policy": drug_gm_policy,
    })
    # Validate against the entire processed lookup, including categories with no retained sales.
    apply_scope_policy(products[["DEPARTMENT", "COMMODITY_DESC"]].head(0), policy, products)
    assignments = [
        ("EXCLUDED_DEPARTMENTS", policy["excluded_departments"]),
        ("EXCLUDED_COMMODITIES", policy["excluded_commodities"]),
        ("DRUG_GM_REVIEW_COMMODITIES", policy["drug_gm_review_commodities"]),
        ("DRUG_GM_POLICY", policy["drug_gm_policy"]),
    ]
    code = "\n".join(f"{name} = {value!r}" for name, value in assignments) + "\n"
    return {"status": "REVIEWED_DRAFT_NOT_APPLIED", "policy": policy, "configuration_block": code,
            "note": "Explicit user-selected scope. Matching guide counts alone does not reproduce the missing historical lists. Rebuild and validate after applying."}
