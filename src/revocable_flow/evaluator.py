"""Offline evaluation; execution is isolated in the explicitly gated runner."""
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from . import __version__
from .loader import load_predictions, load_scenarios, validate_metadata
from .metrics import compute_metrics
from .schema import ValidationError, parse_json


# Backward import seam: the shared response interface lives outside offline scoring.
from .providers.base import ModelProvider


def load_config(path: str | Path) -> dict:
    # JSON is a YAML 1.2 subset; keep this pilot dependency-free.
    config = parse_json(Path(path).read_text(encoding="utf-8"))
    required = {"benchmark", "seed", "provider", "model", "model_parameters", "prompt_version", "annotation_version"}
    if not isinstance(config, dict) or config.keys() != required:
        raise ValidationError("configuration has missing or unknown keys")
    if type(config["seed"]) is not int or not isinstance(config["model_parameters"], dict):
        raise ValidationError("seed must be an integer and model_parameters an object")
    for key in required - {"seed", "model_parameters"}:
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValidationError(f"{key} must be a nonempty string")
    return config


def evaluate_files(benchmark: str | Path, predictions: str | Path, config_path: str | Path,
                   output_dir: str | Path) -> dict:
    """Evaluate supplied annotations and archive exact input bytes plus provenance.

    Existing run directories are never overwritten. Benchmark paths are explicit;
    the config's benchmark must resolve to the same file relative to config's parent.
    """
    benchmark, predictions, config_path = map(Path, (benchmark, predictions, config_path))
    config = load_config(config_path)
    if (config_path.parent / config["benchmark"]).resolve() != benchmark.resolve():
        raise ValidationError("config benchmark and evaluated benchmark differ")
    metadata_path = benchmark.with_name("metadata.json")
    scenarios = load_scenarios(benchmark, require_pilot=metadata_path.exists())
    metadata = validate_metadata(benchmark, scenarios) if metadata_path.exists() else None
    report = compute_metrics(scenarios, load_predictions(predictions))
    artifacts = {"scenarios.jsonl": benchmark.read_bytes(),
                 "predictions.jsonl": predictions.read_bytes(),
                 "config.yaml": config_path.read_bytes()}
    if metadata is not None:
        artifacts["metadata.json"] = metadata_path.read_bytes()
    repo = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config_path.parent,
                          capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=config_path.parent,
                           capture_output=True, text=True)
    manifest = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "evaluation_kind": "offline_supplied_annotations", "package_version": __version__,
                "python_version": platform.python_version(), "configuration": config, "benchmark_metadata": metadata,
                "git_commit": repo.stdout.strip() if repo.returncode == 0 else None,
                "git_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
                "artifact_sha256": {k: hashlib.sha256(v).hexdigest() for k,v in artifacts.items()}}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in artifacts.items():
        (output / name).write_bytes(data)
    (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return report
