#!/usr/bin/env bash
# list-mission-artifacts.sh
# Phase 1: enumerate mission artifacts and runtime logs.
# Usage: list-mission-artifacts.sh <mission-dir> <run-dir> <output-dir>
# Writes <output-dir>/inventory.json (and exits 0 even if some sources are missing).

set -euo pipefail

MISSION_DIR="${1:-}"
RUN_DIR="${2:-}"
OUTPUT_DIR="${3:-}"

if [[ -z "${OUTPUT_DIR}" ]]; then
  echo "usage: $0 <mission-dir> <run-dir> <output-dir>" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}"

# Use python for JSON assembly (already used everywhere in the project, no jq dep).
python3 - "${MISSION_DIR}" "${RUN_DIR}" "${OUTPUT_DIR}" <<'PY'
import json, os, sys, pathlib

mission_dir = sys.argv[1] or ""
run_dir = sys.argv[2] or ""
output_dir = sys.argv[3]

inventory = {
  "analyzed_at": "2026-06-19T17:23:00Z",  # overwritten below
  "mission_dir": mission_dir or None,
  "run_dir": run_dir or None,
  "mission_artifacts": {"present": [], "missing": []},
  "run_artifacts": {"present": [], "missing": []},
  "skipped_artifacts": [],
}

import datetime
inventory["analyzed_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

# Mission artifacts
mission_files = [
  "mission.md", "architecture.md", "validation-contract.md", "AGENTS.md",
  "features.json", "progress_log.jsonl", "model-settings.json",
]
if mission_dir and os.path.isdir(mission_dir):
  for f in mission_files:
    p = os.path.join(mission_dir, f)
    if os.path.exists(p):
      inventory["mission_artifacts"]["present"].append(p)
    else:
      inventory["mission_artifacts"]["missing"].append(p)
  # handoffs
  handoffs_dir = os.path.join(mission_dir, "handoffs")
  if os.path.isdir(handoffs_dir):
    for fn in sorted(os.listdir(handoffs_dir)):
      inventory["mission_artifacts"]["present"].append(os.path.join(handoffs_dir, fn))
  # evidence (just count; not enumerated for size)
  ev = os.path.join(mission_dir, "evidence")
  if os.path.isdir(ev):
    cnt = sum(len(files) for _, _, files in os.walk(ev))
    inventory["mission_artifacts"]["present"].append(f"{ev}/ ({cnt} files)")
  # library
  lib = os.path.join(mission_dir, "library")
  if os.path.isdir(lib):
    for fn in sorted(os.listdir(lib)):
      inventory["mission_artifacts"]["present"].append(os.path.join(lib, fn))
  # skills (sub-skill SKILL.md files)
  sk = os.path.join(mission_dir, "skills")
  if os.path.isdir(sk):
    for root, _, files in os.walk(sk):
      for fn in files:
        if fn.endswith(".md"):
          inventory["mission_artifacts"]["present"].append(os.path.join(root, fn))
else:
  for f in mission_files:
    inventory["mission_artifacts"]["missing"].append(os.path.join(mission_dir, f) if mission_dir else f)

# Run artifacts
if run_dir and os.path.isdir(run_dir):
  for root, _, files in os.walk(run_dir):
    for fn in files:
      p = os.path.join(root, fn)
      # binary files: record presence, skip reading
      binary_ext = (".png", ".jpg", ".jpeg", ".gif", ".wav", ".mp3", ".mp4",
                    ".html", ".htm", ".pdf", ".zip", ".tar", ".gz", ".bin")
      if any(fn.lower().endswith(ext) for ext in binary_ext):
        inventory["skipped_artifacts"].append({"path": p, "reason": "binary"})
        continue
      inventory["run_artifacts"]["present"].append(p)
else:
  inventory["run_artifacts"]["missing"].append(run_dir or "(no run-dir)")

with open(os.path.join(output_dir, "inventory.json"), "w") as f:
  json.dump(inventory, f, indent=2)

print(f"inventory.json written: "
      f"mission={len(inventory['mission_artifacts']['present'])} present, "
      f"run={len(inventory['run_artifacts']['present'])} present, "
      f"skipped={len(inventory['skipped_artifacts'])}")
PY
