#!/usr/bin/env bash
# parse-progress-log.sh
# Phase 2: normalize mission artifacts + runtime logs into events.jsonl.
# Usage: parse-progress-log.sh <inventory.json> <output-dir>

set -euo pipefail

INV="${1:-}"
OUTPUT_DIR="${2:-}"

if [[ -z "${INV}" || -z "${OUTPUT_DIR}" ]]; then
  echo "usage: $0 <inventory.json> <output-dir>" >&2
  exit 2
fi

python3 - "${INV}" "${OUTPUT_DIR}" <<'PY'
import json, os, re, sys, datetime

inventory_path = sys.argv[1]
output_dir = sys.argv[2]

with open(inventory_path) as f:
  inv = json.load(f)

events = []
event_id = 0

def next_id():
  global event_id
  event_id += 1
  return f"e{event_id:06d}"

VERDICT_RE = re.compile(r"^\s*Verdict\s*:\s*(.+)", re.IGNORECASE)
RESULTS_RE = re.compile(r"^\s*Results\s*:", re.IGNORECASE)
STRATEGY_RE = re.compile(r"^\s*Strategy attempted\s*:\s*(.+)", re.IGNORECASE)
SECTION_RE = re.compile(r"^===\s*([^=]+?)\s*===")
HTTP_STATUS_RE = re.compile(r"\b([45]\d{2})\b")
POLL_RE = re.compile(r"^poll=(\d+)\s+t=(\d+)s\s+http_rc=(\d+)\s+loaded=(\S+)\s+resp=(.+)$")

def normalize_msg(msg):
  """Replace volatile tokens in a message to enable grouping."""
  if not isinstance(msg, str):
    msg = str(msg)
  msg = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", msg)
  msg = re.sub(r"\b\d+\.\d+\.\d+\.\d+:\d+\b", "<HOST:PORT>", msg)
  msg = re.sub(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b", "<TS>", msg)
  msg = re.sub(r"\b\d+\b", "<NUM>", msg)
  return msg

def heuristic_level(line):
  low = line.lower()
  if low.startswith("[error]") or '"level":"error"' in low or '"level": "error"' in low:
    return "error"
  if low.startswith("[warn]") or '"level":"warn"' in low or '"level": "warn"' in low:
    return "warn"
  if "failed" in low or "error" in low or "broken pipe" in low:
    return "warn"
  if low.startswith("===") or low.startswith("poll=") or low.startswith("results"):
    return "info"
  return "info"

def heuristic_scope(line):
  m = SECTION_RE.match(line)
  if m:
    return m.group(1).strip()[:40]
  return ""

def parse_jsonl_line(line, source):
  """Parse a JSONL line from a pino-style orchestrator log."""
  try:
    obj = json.loads(line)
  except json.JSONDecodeError:
    return None
  return {
    "id": next_id(),
    "ts": obj.get("ts") or obj.get("time") or "",
    "level": (obj.get("level") or "info").lower(),
    "scope": (obj.get("scope") or ""),
    "msg": (obj.get("msg") or obj.get("message") or ""),
    "source": source,
    "raw": line[:500],
    "msg_template": normalize_msg(obj.get("msg") or obj.get("message") or ""),
  }

def parse_text_line(line, source, default_ts=""):
  """Parse a non-JSONL line."""
  level = heuristic_level(line)
  scope = heuristic_scope(line)
  return {
    "id": next_id(),
    "ts": default_ts,
    "level": level,
    "scope": scope,
    "msg": line.strip(),
    "source": source,
    "raw": line[:500],
    "msg_template": normalize_msg(line.strip()),
  }

def parse_poll_line(line, source, start_ts=""):
  m = POLL_RE.match(line.strip())
  if not m:
    return None
  poll_n, t_s, rc, loaded, resp = m.groups()
  level = "error" if rc == "7" or (rc == "0" and "false" in loaded) else "info"
  # Synthesize ts from start_ts + t_s offset when available
  ts = ""
  if start_ts:
    try:
      base = datetime.datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
      ts = (base + datetime.timedelta(seconds=int(t_s))).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
      ts = ""
  return {
    "id": next_id(),
    "ts": ts,
    "level": level,
    "scope": "tts.health.poll",
    "msg": f"poll={poll_n} t={t_s}s http_rc={rc} loaded={loaded}",
    "source": source,
    "raw": line[:500],
    "msg_template": "poll=<NUM> t=<NUM>s http_rc=<NUM> loaded=<STR>",
    "extra": {"http_rc": int(rc), "loaded": loaded, "resp": resp[:200]},
  }

# Process all mission artifacts and run artifacts
sources = []
sources.extend(inv.get("mission_artifacts", {}).get("present", []))
sources.extend(inv.get("run_artifacts", {}).get("present", []))

# File-type policy:
#   - .md     : documentation; skip (not an event stream)
#   - .json   : snapshot; skip (one event per file is enough)
#   - .jsonl  : event stream; parse every line
#   - .log    : event stream OR probe log; parse every line
#   - other   : parse every line
SKIP_EXT = {".md"}
SNAPSHOT_EXT = {".json"}

for path in sources:
  if not isinstance(path, str) or not os.path.isfile(path):
    continue
  ext = os.path.splitext(path)[1].lower()
  if ext in SKIP_EXT:
    continue
  if ext in SNAPSHOT_EXT:
    # record one summary event for snapshots
    events.append({
      "id": next_id(),
      "ts": "",
      "level": "info",
      "scope": "snapshot",
      "msg": f"snapshot file present: {os.path.basename(path)}",
      "source": path,
      "raw": "",
      "msg_template": "snapshot file present: <STR>",
    })
    continue
  rel = path
  try:
    with open(path, "r", errors="replace") as f:
      lines = f.readlines()
  except Exception:
    continue
  # Hoist per-file state: probe log "polling start:" header sets a
  # start timestamp that subsequent poll= lines should inherit (their
  # own t=<NUM>s is an offset from this header). Without hoisting, the
  # variable resets on every line and only the line directly after the
  # header inherits the timestamp.
  poll_start_ts = ""
  for i, line in enumerate(lines):
    line = line.rstrip("\n")
    if not line.strip():
      continue
    # Try JSON first
    if line.lstrip().startswith("{"):
      ev = parse_jsonl_line(line, rel)
      if ev:
        events.append(ev)
        # Special handling: if this is a chaos verdict, also pull context
        if VERDICT_RE.match(line):
          # Look back for Strategy / Results
          ctx_lines = lines[max(0, i-15):i]
          for cl in ctx_lines:
            m = STRATEGY_RE.match(cl)
            if m:
              events.append({
                "id": next_id(), "ts": "", "level": "info", "scope": "chaos.context",
                "msg": f"strategy: {m.group(1).strip()}", "source": rel, "raw": cl[:500],
                "msg_template": "strategy: <STR>",
              })
            elif RESULTS_RE.match(cl):
              events.append({
                "id": next_id(), "ts": "", "level": "info", "scope": "chaos.context",
                "msg": "results block", "source": rel, "raw": cl[:500],
                "msg_template": "results block",
              })
        continue
    # Probe log poll lines — start_ts is the hoisted per-file value.
    # When this line IS the header, capture and reuse it.
    if "polling start:" in line:
      m = re.search(r"polling start:\s*(\S+)", line)
      if m:
        poll_start_ts = m.group(1)
    ev = parse_poll_line(line, rel, poll_start_ts)
    if ev:
      events.append(ev)
      continue
    # Section marker / chaos summary text
    if SECTION_RE.match(line) or RESULTS_RE.match(line) or STRATEGY_RE.match(line) or VERDICT_RE.match(line):
      m = VERDICT_RE.match(line)
      if m:
        events.append({
          "id": next_id(), "ts": "", "level": "info", "scope": "chaos.verdict",
          "msg": f"verdict: {m.group(1).strip()}", "source": rel, "raw": line[:500],
          "msg_template": "verdict: <STR>",
        })
      else:
        events.append(parse_text_line(line, rel))
      continue
    # Generic text line
    events.append(parse_text_line(line, rel))

# Write events.jsonl
out_path = os.path.join(output_dir, "events.jsonl")
with open(out_path, "w") as f:
  for ev in events:
    f.write(json.dumps(ev) + "\n")

print(f"events.jsonl written: {len(events)} events from {len(sources)} sources")
PY
