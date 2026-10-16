"""Write a credential-safe local preflight; call Gemini only with --execute."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
from src import config
from src.artifact_io import write_json
from src.cloud_access import cloud_configuration,preflight,perform_smoke


def main():
    if config.LOCAL_ONLY_MODE:
        print("Cloud workflow disabled by the user. Run scripts/run_local.py in VS Code instead.", flush=True)
        return
    parser=argparse.ArgumentParser()
    parser.add_argument("--project-id")
    parser.add_argument("--location")
    parser.add_argument("--model")
    parser.add_argument("--execute",action="store_true",help="Make one authenticated model call; requires configured project/ADC.")
    args=parser.parse_args()
    settings=cloud_configuration(args.project_id,args.location,args.model)
    status=preflight(settings)
    write_json(config.CLOUD_PREFLIGHT_FILE,status)
    print(status["status"],"; missing:",", ".join(status["missing"]) or "none",flush=True)
    if not args.execute:
        print("No cloud call attempted. Authentication, billing and model access remain unverified.",flush=True)
        return
    if status["missing"]:
        write_json(config.CLOUD_SMOKE_FILE,{"status":"NOT_EXECUTED","cloud_call_verified":False,"missing":status["missing"]})
        raise SystemExit(2)
    from google import genai
    import google.auth
    try:
        result=perform_smoke(settings,genai.Client,google.auth.default)
    except Exception as error:
        # Exception text can contain credential paths/request metadata; report only type and HTTP code.
        result={"status":"FAILED","cloud_call_verified":False,"error_type":type(error).__name__,
                "http_code":getattr(error,"code",None),"configuration":settings}
    write_json(config.CLOUD_SMOKE_FILE,result)
    print(result["status"],flush=True)
    if result["cloud_call_verified"]:
        print(result["response_text"],flush=True)
    else:
        raise SystemExit(1)


if __name__=="__main__":
    main()
