"""Inspect preserved source and new recovery artifacts before authorizing upload."""
import os
from pathlib import Path
from hashlib import sha256

from revocable_flow.artifact_safety import stage_archive
from revocable_flow.runner import _read


def main():
    run_id = os.environ["RECOVERY_ID"]
    source_id = os.environ["SOURCE_RUN_ID"]
    preserved = Path(os.environ["RUNNER_TEMP"]) / "recovery-preserved/source"
    destination = Path(os.environ["RUNNER_TEMP"]) / "recovery-upload"
    manifest = _read(Path("results"), f"manifests/{run_id}.json")
    hashes = {str(p.relative_to(preserved)): sha256(p.read_bytes()).hexdigest()
              for p in preserved.rglob("*") if p.is_file()}
    if hashes != manifest["recovery"]["source_file_hashes"]:
        raise ValueError("source changed")
    stage_archive(preserved, source_id, destination / "source")
    stage_archive("results", run_id, destination / "recovery", recovery=True)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write("safe=true\n")
    print("Inspected recovery archive prepared; original source bytes unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit("Safe recovery staging failed; upload not authorized.") from None
