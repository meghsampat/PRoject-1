"""Install the checksum-verified Google CLI archive inside this workspace, without login."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import hashlib
import os
import posixpath
import subprocess
import urllib.request
import zipfile
from src import config
from src.artifact_io import write_json,file_fingerprint


def main():
    if config.LOCAL_ONLY_MODE:
        print("Cloud workflow disabled by the user. Run scripts/run_local.py in VS Code instead.", flush=True)
        return
    destination=config.CLOUD_TOOLS_DIR.resolve()
    archive=destination/config.CLOUD_CLI_ARCHIVE_NAME
    destination.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(config.CLOUD_CLI_ARCHIVE_URL,timeout=config.CLOUD_DOWNLOAD_TIMEOUT) as response, archive.open("wb") as handle:
            while block:=response.read(config.HASH_CHUNK_BYTES):
                handle.write(block)
    fingerprint=file_fingerprint(archive)
    if fingerprint["sha256"]!=config.CLOUD_CLI_ARCHIVE_SHA256:
        raise ValueError("Google CLI archive SHA256 mismatch; do not extract or bypass verification.")
    sdk=destination/"google-cloud-sdk"
    materialized_links=0
    if sdk.exists():
        marker=sdk/".fmcg_archive_sha256"
        if not marker.is_file() or marker.read_text()!=fingerprint["sha256"]:
            raise ValueError("An existing unverified SDK directory will not be overwritten.")
    else:
        materialized_links=0
        with zipfile.ZipFile(archive) as z:
            links=[]
            for item in z.infolist():
                target=(destination/item.filename).resolve()
                if not target.is_relative_to(destination) or not item.filename.replace("\\","/").startswith("google-cloud-sdk/"):
                    raise ValueError("Unsafe archive path.")
                if (item.external_attr>>16)&0o170000==0o120000:
                    link=z.read(item).decode("utf-8")
                    if posixpath.isabs(link):
                        raise ValueError("Absolute archive link.")
                    source=posixpath.normpath(posixpath.join(posixpath.dirname(item.filename),link))
                    if not source.startswith("google-cloud-sdk/"):
                        raise ValueError("Archive link escapes the SDK.")
                    links.append((item,source))
            link_names={item.filename for item,_ in links}
            z.extractall(destination,members=[item for item in z.infolist() if item.filename not in link_names])
            for item,source in links:
                target=destination/item.filename
                if source in z.namelist() and not z.getinfo(source).is_dir():
                    if source in link_names:
                        raise ValueError("Nested archive links require explicit review.")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(z.read(source))
                else:
                    matches=[member for member in z.infolist() if member.filename.startswith(source+"/") and not member.is_dir()]
                    if not matches or any(member.filename in link_names for member in matches):
                        raise ValueError("Missing or nested link target.")
                    for member in matches:
                        copied=(target/member.filename.removeprefix(source+"/")).resolve()
                        if not copied.is_relative_to(destination):
                            raise ValueError("Materialized archive link escapes workspace.")
                        copied.parent.mkdir(parents=True,exist_ok=True)
                        copied.write_bytes(z.read(member))
                materialized_links+=1
        (sdk/".fmcg_archive_sha256").write_text(fingerprint["sha256"])
    interpreter=sdk/"platform"/"bundledpython"/"python.exe"
    entry=sdk/"lib"/"gcloud.py"
    if not interpreter.is_file() or not entry.is_file():
        raise ValueError("Expected CLI interpreter/entrypoint missing.")
    environment=os.environ.copy()
    environment["CLOUDSDK_CORE_DISABLE_USAGE_REPORTING"]="true"
    environment["CLOUDSDK_CONFIG"]=str(config.PROJECT_ROOT/".cloud-state")
    run=subprocess.run([str(interpreter),str(entry),"--version","--format=json"],capture_output=True,text=True,
        timeout=config.CLOUD_COMMAND_TIMEOUT,env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    if run.returncode:
        raise ValueError("CLI version check failed; no auth or project configuration attempted.")
    write_json(config.OUTPUTS_DIR/"cloud_cli_installation.json",{"status":"INSTALLED_VERSION_CHECKED",
        "version":config.CLOUD_CLI_VERSION,"archive":fingerprint,"cli_path":str(sdk/"bin"/"gcloud.cmd"),
        "version_output":run.stdout.strip(),"materialized_in_archive_links":materialized_links,"authenticated":False,"project_configured":False,
        "reference":config.CLOUD_CLI_REFERENCE})
    print(f"Installed verified Google CLI {config.CLOUD_CLI_VERSION} locally; authentication/project setup not performed.",flush=True)


if __name__=="__main__":
    main()

