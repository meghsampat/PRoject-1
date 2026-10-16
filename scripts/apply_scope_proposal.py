"""Apply the reviewed scope proposal to four config constants, preserving other code."""
from pathlib import Path
import ast
import json
import pprint
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.scope_proposal import make_scope_proposal


def main():
    if sys.argv[1:] != ["--apply"]:
        raise SystemExit("Use --apply only after the user has explicitly accepted this proposed scope.")
    config_path = Path(config.__file__).resolve()
    if config_path != (config.PROJECT_ROOT / "src" / "config.py").resolve():
        raise ValueError("Configuration target must be this project's src/config.py.")
    proposal = json.loads((config.PROPOSED_SCOPE_DIR / "scope_proposal.json").read_text(encoding="utf-8"))
    validation = json.loads((config.PROPOSED_SCOPE_DIR / "scenario_validation.json").read_text(encoding="utf-8"))
    if validation["status"] != "PASS_SCENARIO_NOT_APPROVED" or proposal["id"] != config.PROPOSED_SCOPE_ID:
        raise ValueError("Expected the tested proposal for this project.")
    if proposal["source_master_sha256"] != file_fingerprint(config.MASTER_FILE)["sha256"] or proposal["source_lookup_sha256"] != file_fingerprint(config.PRODUCT_LOOKUP_FILE)["sha256"]:
        raise ValueError("Proposal source snapshot changed. Regenerate and review it before applying.")
    import pandas as pd
    products = pd.read_parquet(config.PRODUCT_LOOKUP_FILE)
    policy = proposal["policy"]
    verified = make_scope_proposal(policy["excluded_departments"], policy["excluded_commodities"], policy["drug_gm_review_commodities"], policy["drug_gm_policy"], products)["policy"]
    values = {
        "EXCLUDED_DEPARTMENTS": verified["excluded_departments"],
        "EXCLUDED_COMMODITIES": verified["excluded_commodities"],
        "DRUG_GM_REVIEW_COMMODITIES": verified["drug_gm_review_commodities"],
        "DRUG_GM_POLICY": verified["drug_gm_policy"],
    }
    before = file_fingerprint(config_path)
    source = config_path.read_text(encoding="utf-8-sig")
    lines = source.splitlines(keepends=True)
    replacements = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in values:
            name = node.targets[0].id
            block = f"{name} = {pprint.pformat(values[name], width=88)}\n"
            replacements.append((node.lineno - 1, node.end_lineno, block))
    if len(replacements) != len(values):
        raise ValueError("Expected one top-level assignment for each scope constant.")
    for first, last, block in sorted(replacements, reverse=True):
        lines[first:last] = [block]
    updated = "".join(lines)
    ast.parse(updated)
    config_path.write_text(updated, encoding="utf-8")
    write_json(config.OUTPUTS_DIR / "scope_application.json", {
        "status": "USER_SELECTED_SCOPE_APPLIED_REBUILD_REQUIRED",
        "scope_id": proposal["id"], "selected_policy": verified,
        "authorization": "User explicitly selected 'Apply the tested new scope (Recommended)' in this chat.",
        "source_master_before_rebuild": proposal["source_master_sha256"],
        "configuration_before": before, "configuration_after": file_fingerprint(config_path),
        "note": "New documented scope, not reconstruction of the missing historical lists. Rebuild and validate before reporting metrics.",
    })
    print("Applied the accepted new scope to four config constants. Other configuration is preserved.", flush=True)
    print("Run build_master.py, validate_master.py, build_aggregates.py and validate_aggregates.py.", flush=True)


if __name__ == "__main__":
    main()
