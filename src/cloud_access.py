"""Local cloud configuration checks and a separate explicit Gemini access proof."""
from importlib import metadata
import os
from pathlib import Path
import re
from src import config


def cloud_configuration(project=None,location=None,model=None):
    project=(project or os.environ.get(config.CLOUD_PROJECT_ENV,"")).strip()
    if project and (not re.fullmatch(config.CLOUD_PROJECT_PATTERN,project) or project in {"your-project-id","changeme","not-created"}):
        raise ValueError("Provide an actual Google Cloud project ID, not a placeholder.")
    return {"project_id":project or None,"location":location or os.environ.get(config.CLOUD_LOCATION_ENV) or config.CLOUD_GENAI_LOCATION,
            "model":model or os.environ.get(config.CLOUD_MODEL_ENV) or config.CLOUD_GENAI_MODEL,
            "deployment_region":config.CLOUD_DEPLOYMENT_REGION}


def sdk_version():
    try:
        return metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        return None


def credential_hint():
    explicit=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if explicit and Path(explicit).is_file():
        return "configured_credentials_file"
    root=Path(os.environ.get("CLOUDSDK_CONFIG") or (Path(os.environ.get("APPDATA",str(Path.home())))/"gcloud"))
    if (root/"application_default_credentials.json").is_file():
        return "local_application_default_credentials"
    if os.environ.get("K_SERVICE"):
        return "attached_runtime_credentials_expected"
    return "not_observed"


def preflight(configuration):
    if config.LOCAL_ONLY_MODE:
        return {"status": "DISABLED_BY_USER", "configuration": None, "missing": [], "cloud_call_verified": False,
                "billing_verified": False, "service_api_verified": False, "note": "Local-only VS Code workflow; cloud is not required."}
    version=sdk_version()
    hint=credential_hint()
    api_keys_present=any(bool(os.environ.get(name)) for name in ("GOOGLE_API_KEY","GEMINI_API_KEY"))
    gaps=[]
    if not configuration["project_id"]:gaps.append("Google Cloud project ID")
    if version is None:gaps.append("Pinned google-genai dependency")
    if hint=="not_observed":gaps.append("Application Default Credentials sign-in")
    if api_keys_present:gaps.append("Remove API-key environment variables for this ADC-only test")
    local_cli=(config.CLOUD_TOOLS_DIR/"google-cloud-sdk"/"bin"/"gcloud.cmd").is_file()
    return {"status":"READY_TO_ATTEMPT" if not gaps else "NEEDS_CONFIGURATION",
        "configuration":configuration,"google_genai_version":version,"credential_hint":hint,"cli_available_locally":local_cli,
        "missing":gaps,"cloud_call_verified":False,"billing_verified":False,"service_api_verified":False,
        "note":"Local presence checks do not verify credentials, billing, permissions or model availability. Credentials/tokens are never printed. No resources are created and no data is uploaded by preflight."}


def perform_smoke(configuration,client_factory,credential_factory):
    if config.LOCAL_ONLY_MODE:
        raise ValueError("Cloud calls are disabled for the local-only VS Code workflow.")
    if not configuration["project_id"]:
        raise ValueError("A project ID is required before a cloud call.")
    credentials,_=credential_factory(scopes=[config.CLOUD_VERTEX_SCOPE],quota_project_id=configuration["project_id"])
    client=client_factory(enterprise=True,project=configuration["project_id"],location=configuration["location"],
        credentials=credentials,http_options={"api_version":config.CLOUD_API_VERSION,"timeout":config.CLOUD_REQUEST_TIMEOUT_MS,
                                             "retry_options":{"attempts":1}})
    try:
        response=client.models.generate_content(model=configuration["model"],contents=config.CLOUD_SMOKE_PROMPT,
            config={"max_output_tokens":config.CLOUD_SMOKE_MAX_TOKENS,"temperature":0})
        text=(response.text or "").strip()
        return {"status":"PASS" if text else "CALL_RETURNED_NO_TEXT","cloud_call_verified":bool(text),
                "configuration":configuration,"response_text":text,
                "note":"One fixed greeting prompt only; no retail data or credentials sent as prompt. This proves model access, not ADK integration or deployment."}
    finally:
        client.close()
