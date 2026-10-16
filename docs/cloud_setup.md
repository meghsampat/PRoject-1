# Retired cloud workflow — 13 October 2026

The user chose local-only VS Code operation without GCP or deployment. This guide is preserved as history; its steps are not required or authorized by the current scope. Cloud scripts and model calls are disabled by LOCAL_ONLY_MODE. Use [local_setup.md](local_setup.md).

# Google Cloud access setup — 13 October 2026

Google CLI 588.0.0 is installed in .tools/google-cloud-sdk after official archive SHA256 verification and executable version checks. Evidence: outputs/cloud_cli_installation.json. Optional google-genai==2.30.0 is installed from requirements-cloud.txt; pip check passed. Neither installation proves cloud access.

Local preflight currently lacks a Google Cloud project ID and Application Default Credentials (ADC). No real model request, account sign-in, project creation, billing/API/IAM change, data upload or deployment has been performed.

## Project and sign-in

Select your intended project in Google Cloud and verify billing, API enablement, required permissions and university project budget alerts. The [Google quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start) documents these prerequisites and roles/aiplatform.user for model use. Account setup has not been executed here.

Use your actual public project ID; keep passwords, tokens and credentials JSON out of chat. Complete local browser consent yourself. [ADC instructions](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc).

Run from the repository root, replacing the placeholder:

```powershell
$env:GOOGLE_CLOUD_PROJECT = 'replace-with-actual-project-id'
$env:GOOGLE_CLOUD_LOCATION = 'global'
$env:FMCG_GEMINI_MODEL = 'gemini-3.5-flash'
$env:CLOUDSDK_CONFIG = Join-Path (Get-Location) '.cloud-state'
$env:CLOUDSDK_CORE_DISABLE_USAGE_REPORTING = 'true'
.\.tools\google-cloud-sdk\bin\gcloud.cmd auth application-default login
.\.tools\google-cloud-sdk\bin\gcloud.cmd auth application-default set-quota-project $env:GOOGLE_CLOUD_PROJECT
.\.venv\Scripts\python.exe scripts/check_cloud_access.py --project-id $env:GOOGLE_CLOUD_PROJECT
```

The placeholder is rejected until replaced. Use the same terminal and CLOUDSDK_CONFIG for CLI login and the Python test. .cloud-state and .env are ignored by Git. .env.example documents variable names; scripts do not automatically load .env files.

If the API is not enabled, an identity with API-enable permissions can perform this separately for the selected project:

```powershell
.\.tools\google-cloud-sdk\bin\gcloud.cmd auth login
.\.tools\google-cloud-sdk\bin\gcloud.cmd services enable aiplatform.googleapis.com --project $env:GOOGLE_CLOUD_PROJECT
```

CLI account login and ADC serve different clients. No API-enable command has been executed here. See the [cloud quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start) for billing, IAM and API prerequisites.

## Actual access proof

After prerequisites are met:

```powershell
.\.venv\Scripts\python.exe scripts/check_cloud_access.py --project-id $env:GOOGLE_CLOUD_PROJECT --execute
```

This makes one fixed greeting request and can incur normal model charges. It sends no retail records. A real nonempty response is required for PASS in outputs/vertex_smoke_test.json. Errors record type/status only; credentials and raw exception text are not printed. Stub tests are not cloud proof.

outputs/cloud_preflight.json contains local presence checks and always leaves cloud_call_verified false. The actual-call record is separate. A real PASS would prove access for that configuration, not ADK integration or public deployment.

## Configuration and references

Settings live in src/config.py: configurable gemini-3.5-flash, global model location, cloud backend enterprise=True, ADC credentials, API v1, one attempt, 30-second timeout, maximum 128 output tokens. Future app deployment region us-central1 is a separate setting.

The current [Google Gen AI SDK](https://googleapis.github.io/python-genai/) accepts enterprise=True for the cloud backend and the legacy vertexai spelling. Defaults were checked against Google's [cloud quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start) and [model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions); recheck model availability when running the test. Official CLI versions/checksums: [Google versioned archives](https://docs.cloud.google.com/sdk/docs/downloads-versioned-archives). Six contained archive links were copied from their contained targets for Windows compatibility.

Next: Google ADK orchestration around validated local Python tools, saved-model loading, household/decomposition tools, human usefulness reviews, Python 3.11, deployment, final evaluation and Review 3 mapping. Do not create custom Vertex model-serving endpoints for the saved offline models.


## Enable the dashboard's connected assistant

After the real greeting PASS, launch/restart Streamlit from the **same terminal** containing GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, FMCG_GEMINI_MODEL and CLOUDSDK_CONFIG. The app must see the same settings and ADC file as the test.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

The sidebar **Use connected Gemini** toggle becomes available when local prerequisites and the real access record match. It defaults off. Enable it to interpret flexible supported questions and select checked evidence/suggestion paragraphs. Each model interaction can incur charges. The adapter sends the submitted question, prior route and checked aggregate summaries, without raw transactions or household histories.

Responses stay within the validated tools, checked paragraphs and review requirements. The model cannot add new numeric claims or unrestricted prose. Invalid selections and model errors produce an explicitly local fallback. This is optional Gemini support, not OpenAI GPT or ADK integration.

Structured SDK output was implemented against the [official Google Gen AI SDK JSON-schema documentation](https://googleapis.github.io/python-genai/). Unit-test stubs verify the request contract; they do not prove cloud chat access. Current outputs/chat_validation.json confirms local chat only, with actual_cloud_chat_verified=false.
