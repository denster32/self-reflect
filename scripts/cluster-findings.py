#!/usr/bin/env python3
"""cluster-findings.py — stdlib-only Phase 3+5+6: run all detectors on events.jsonl,
score findings, write findings.json and patches/*.md.

Usage: cluster-findings.py <output-dir> [--top N]
Reads: <output-dir>/events.jsonl, <output-dir>/inventory.json
       ~/.factory/skills/self-reflect/config.yaml
Writes: <output-dir>/findings.json
        <output-dir>/summary.json
        <output-dir>/patches/<file>.md
"""
import json
import os
import re
import sys
import datetime
import collections
import pathlib

SKILL_DIR = pathlib.Path.home() / ".factory" / "skills" / "self-reflect"
CONFIG_PATH = SKILL_DIR / "config.yaml"


def load_config():
    """Tiny YAML loader sufficient for our flat-keyed config.yaml.
    Avoids requiring PyYAML on the user's machine. Handles `# comment` after values
    and 2-level nesting with lists (e.g. `foo:\\n  bar:\\n    - baz`).
    """
    def parse_scalar(s):
        s = s.split("#", 1)[0].strip()  # strip trailing comment
        if not s:
            return None
        if s.startswith("[") and s.endswith("]"):
            return [x.strip().strip('"').strip("'") for x in s[1:-1].split(",") if x.strip()]
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    cfg = {}
    cur_section = None
    cur_subsection = None
    with open(CONFIG_PATH) as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip("\n")
            if not line.strip():
                continue
            # Top-level key (no leading whitespace)
            if not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                if v == "":
                    cfg[k] = {}
                    cur_section = k
                    cur_subsection = None
                else:
                    cfg[k] = parse_scalar(v)
                    cur_section = None
                    cur_subsection = None
                continue
            # 4-space-indented list item (list under subsection)
            if line.startswith("    - ") or line.startswith("    \t- "):
                v = parse_scalar(line.lstrip()[2:].lstrip())
                if cur_section and cur_subsection:
                    section_dict = cfg[cur_section]
                    if cur_subsection not in section_dict or isinstance(section_dict[cur_subsection], dict):
                        section_dict[cur_subsection] = []
                    section_dict[cur_subsection].append(v)
                continue
            # 2-space-indented key (subkey under section)
            if line.startswith("  ") and ":" in line:
                stripped = line.strip()
                if stripped.startswith("- "):
                    continue
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                if cur_section is None:
                    continue
                if v == "":
                    cfg[cur_section][k] = {}
                    cur_subsection = k
                else:
                    cfg[cur_section][k] = parse_scalar(v)
                    cur_subsection = None
                continue
    return cfg


def parse_ts(ts_str):
    """Best-effort ISO-8601 parser."""
    if not ts_str:
        return None
    try:
        return datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def dedup_id():
    n = 0
    while True:
        yield f"f{n:04d}"
        n += 1


def detect_repeated_message(events, cfg):
    cfg_rm = cfg["repeated_message"]
    threshold = cfg_rm["count"]
    window = cfg_rm["window_seconds"]
    findings = []
    # group by (scope, msg_template)
    groups = collections.defaultdict(list)
    for ev in events:
        if ev.get("level") not in ("warn", "error"):
            continue
        # Skip high-volume known telemetry
        if ev.get("scope") in ("breaker", "circuit") and "breaker.call" in ev.get("msg_template", ""):
            continue
        key = (ev.get("scope", ""), ev.get("msg_template", ""))
        groups[key].append(ev)
    for (scope, tmpl), evs in groups.items():
        if len(evs) < threshold:
            continue
        # Check window
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if not ts_list:
            # No parsable ts; still fire if count is high enough
            window_ok = True
        else:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            window_ok = span <= window
        if not window_ok:
            continue
        findings.append({
            "detector": "repeated_message",
            "scope": scope,
            "msg_template": tmpl,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_escalating_health(events, cfg):
    cfg_eh = cfg["escalating_health"]
    delta_min = cfg_eh["delta"]
    window = cfg_eh["window_seconds"]
    counter_re = re.compile(r"consecutive (?:failures?|errors?):\s*(\d+)")
    # group by scope (or broader key)
    groups = collections.defaultdict(list)
    for ev in events:
        m = counter_re.search(ev.get("msg", ""))
        if not m:
            continue
        counter = int(m.group(1))
        ts = parse_ts(ev.get("ts", ""))
        if ts is None:
            continue
        scope = ev.get("scope", "")
        groups[scope].append((ts, counter, ev))
    findings = []
    for scope, entries in groups.items():
        entries.sort(key=lambda x: x[0])
        # find the longest monotonically-rising run within window
        # where the counter never resets and increases by >= delta_min
        i = 0
        n = len(entries)
        while i < n:
            ts0, c0, ev0 = entries[i]
            j = i
            max_counter = c0
            while j + 1 < n:
                ts1, c1, _ = entries[j + 1]
                if (ts1 - ts0).total_seconds() > window:
                    break
                if c1 < max_counter:
                    # counter reset; this run is over
                    break
                j += 1
                if c1 > max_counter:
                    max_counter = c1
            if max_counter - c0 >= delta_min and j > i:
                cluster = entries[i:j + 1]
                findings.append({
                    "detector": "escalating_health",
                    "scope": scope,
                    "counter_min": c0,
                    "counter_max": max_counter,
                    "occurrences": len(cluster),
                    "first_seen": cluster[0][2].get("ts", ""),
                    "last_seen": cluster[-1][2].get("ts", ""),
                    "evidence_event_ids": [e[2]["id"] for e in cluster],
                })
                i = j + 1
            else:
                i += 1
    return findings


def detect_restart_loop(events, cfg):
    cfg_rl = cfg["restart_loop"]
    window = cfg_rl["followup_window_seconds"]
    restart_re = re.compile(r"restarting (?:\w+ )?(?:pipeline )?\(attempt (\d+)\)")
    restarts = []
    for ev in events:
        m = restart_re.search(ev.get("msg", ""))
        if not m:
            continue
        ts = parse_ts(ev.get("ts", ""))
        if ts is None:
            continue
        restarts.append((ts, int(m.group(1)), ev))
    restarts.sort(key=lambda x: x[0])
    findings = []
    for i in range(len(restarts)):
        ts0, att0, ev0 = restarts[i]
        cluster_tuples = [(ts0, att0, ev0)]
        last_ts = ts0
        for j in range(i + 1, len(restarts)):
            ts1, att1, ev1 = restarts[j]
            if (ts1 - last_ts).total_seconds() <= window:
                cluster_tuples.append((ts1, att1, ev1))
                last_ts = ts1
            else:
                break
        if len(cluster_tuples) >= 2:
            findings.append({
                "detector": "restart_loop",
                "scope": cluster_tuples[0][2].get("scope", ""),
                "restart_count": len(cluster_tuples),
                "max_attempt": max(c[1] for c in cluster_tuples),
                "first_seen": cluster_tuples[0][2].get("ts", ""),
                "last_seen": cluster_tuples[-1][2].get("ts", ""),
                "evidence_event_ids": [c[2]["id"] for c in cluster_tuples],
            })
    # dedupe overlapping
    deduped = []
    seen_keys = set()
    for f in findings:
        k = (f["scope"], f["first_seen"], f["last_seen"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        deduped.append(f)
    return deduped


def detect_service_unreachable(events, cfg):
    patterns = cfg["service_unreachable"]["patterns"]
    findings = []
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg):
                matched.append(ev)
                break
    if not matched:
        return findings
    # group by target (host:port or service name)
    groups = collections.defaultdict(list)
    for ev in matched:
        m = re.search(r"(?:to |@ )?(\d+\.\d+\.\d+\.\d+:\d+|127\.0\.0\.1 port \d+)", ev.get("msg", ""))
        target = m.group(1) if m else "unknown"
        groups[target].append(ev)
    for target, evs in groups.items():
        findings.append({
            "detector": "service_unreachable",
            "target": target,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_http_error_storm(events, cfg):
    cfg_h = cfg["http_error_storm"]
    threshold = cfg_h["count"]
    window = cfg_h["window_seconds"]
    # extract status code
    code_re = re.compile(r"\b([45]\d{2})\b")
    code_groups = collections.defaultdict(list)
    for ev in events:
        msg = ev.get("msg", "")
        if not any(k in msg.lower() for k in ("http", "status", "api/", "dashboard")):
            continue
        m = code_re.search(msg)
        if not m:
            continue
        code = int(m.group(1))
        ts = parse_ts(ev.get("ts", ""))
        code_groups[code].append((ts, ev))
    findings = []
    for code, entries in code_groups.items():
        ts_entries = [e for e in entries if e[0] is not None]
        if not ts_entries:
            if len(entries) >= threshold:
                findings.append({
                    "detector": "http_error_storm",
                    "status_code": code,
                    "occurrences": len(entries),
                    "first_seen": entries[0][1].get("ts", ""),
                    "last_seen": entries[-1][1].get("ts", ""),
                    "evidence_event_ids": [e[1]["id"] for e in entries],
                })
            continue
        ts_entries.sort(key=lambda x: x[0])
        # sliding window check
        for i in range(len(ts_entries)):
            j = i
            while j + 1 < len(ts_entries) and (ts_entries[j + 1][0] - ts_entries[i][0]).total_seconds() <= window:
                j += 1
            count = j - i + 1
            if count >= threshold:
                cluster = ts_entries[i:j + 1]
                findings.append({
                    "detector": "http_error_storm",
                    "status_code": code,
                    "occurrences": count,
                    "first_seen": cluster[0][1].get("ts", ""),
                    "last_seen": cluster[-1][1].get("ts", ""),
                    "evidence_event_ids": [c[1]["id"] for c in cluster],
                })
                break
    return findings


def detect_muxer_failure(events, cfg):
    patterns = cfg["muxer_failure"]["patterns"]
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg):
                matched.append(ev)
                break
    if not matched:
        return []
    findings = []
    tag_groups = collections.defaultdict(list)
    for ev in matched:
        m = re.search(r"\[(tee|flv|aost|out) @", ev.get("msg", ""))
        tag = m.group(1) if m else "misc"
        tag_groups[tag].append(ev)
    for tag, evs in tag_groups.items():
        findings.append({
            "detector": "muxer_failure",
            "ffmpeg_tag": tag,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_long_idle(events, cfg):
    cfg_li = cfg["long_idle"]
    idle_seconds = cfg_li["idle_seconds"]
    markers = cfg_li["idle_markers"]
    # find events matching any marker
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for m in markers:
            if m in msg:
                matched.append(ev)
                break
    if not matched:
        return []
    # Try to find idle duration: consecutive "still idle" events from same source
    # without an intervening "ready=true" event.
    by_source = collections.defaultdict(list)
    for ev in matched:
        by_source[ev.get("source", "")].append(ev)
    findings = []
    for source, evs in by_source.items():
        # extract timestamps; if any ts present, compute span
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if ts_list:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            if span < idle_seconds:
                continue
            poll_count = len(evs)
            first_seen = evs[0].get("ts", "")
            last_seen = evs[-1].get("ts", "")
        else:
            # No timestamps — use count heuristic for poll logs
            poll_count = len(evs)
            if poll_count < 5:
                continue
            span = poll_count * 5  # assume 5s poll spacing
            first_seen = ""
            last_seen = ""
        findings.append({
            "detector": "long_idle",
            "service": "TTS" if "tts" in source.lower() or "8800" in source else "unknown",
            "idle_seconds": int(span),
            "poll_count": poll_count,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_json_parse_failure(events, cfg):
    patterns = cfg["json_parse_failure"]["patterns"]
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg, re.IGNORECASE):
                matched.append(ev)
                break
    if not matched:
        return []
    by_scope = collections.defaultdict(list)
    for ev in matched:
        by_scope[ev.get("scope", "")].append(ev)
    findings = []
    for scope, evs in by_scope.items():
        findings.append({
            "detector": "json_parse_failure",
            "scope": scope,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_chaos_verdict(events, cfg):
    findings = []
    for ev in events:
        if ev.get("scope") == "chaos.verdict":
            m = re.match(r"verdict:\s*(.+)", ev.get("msg", ""))
            verdict_text = m.group(1) if m else ev.get("msg", "")
            findings.append({
                "detector": "chaos_verdict",
                "verdict_text": verdict_text,
                "occurrences": 1,
                "first_seen": ev.get("ts", ""),
                "last_seen": ev.get("ts", ""),
                "evidence_event_ids": [ev["id"]],
                "source_file": ev.get("source", ""),
            })
    return findings


def detect_segment_gap(events, cfg):
    """Find gaps between successive segment-start events that exceed the
    configured threshold (default 15 minutes).

    A "segment start" is any event whose msg matches one of the configured
    `starting_markers` (default: `producing ... from:`, `rendering segment`,
    `seg=N`, `[tts-render] seg=N`). We sort all matched events by ts, then
    fire one finding per adjacent pair whose gap exceeds `gap_minutes`.
    """
    cfg_sg = cfg["segment_gap"]
    markers = cfg_sg["starting_markers"]
    gap_seconds = cfg_sg["gap_minutes"] * 60
    # collect and sort
    starts = []
    for ev in events:
        msg = ev.get("msg", "") or ""
        if any(m in msg for m in markers):
            ts = parse_ts(ev.get("ts", ""))
            if ts is None:
                continue
            starts.append((ts, ev))
    starts.sort(key=lambda x: x[0])
    findings = []
    for i in range(len(starts) - 1):
        ts0, ev0 = starts[i]
        ts1, ev1 = starts[i + 1]
        gap = (ts1 - ts0).total_seconds()
        if gap <= gap_seconds:
            continue
        # extract a short marker from the previous event's msg
        marker = ev0.get("msg", "")[:120]
        findings.append({
            "detector": "segment_gap",
            "last_segment_marker": marker,
            "gap_seconds": int(gap),
            "expected_within_seconds": gap_seconds,
            "occurrences": 1,
            "first_seen": ev0.get("ts", ""),
            "last_seen": ev1.get("ts", ""),
            "evidence_event_ids": [ev0["id"], ev1["id"]],
        })
    # dedupe overlapping (defensive — shouldn't happen with sorted starts)
    deduped = []
    seen_keys = set()
    for f in findings:
        k = (f["first_seen"], f["last_seen"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        deduped.append(f)
    return deduped


def detect_browser_console_errors(events, cfg):
    cfg_bc = cfg["browser_console_errors"]
    threshold = cfg_bc["count"]
    window = cfg_bc["window_seconds"]
    # events from sources matching console/browser/agent-browser
    matched = []
    for ev in events:
        src = ev.get("source", "").lower()
        if any(s in src for s in ("console", "browser", "agent-browser")):
            if ev.get("level") in ("warn", "error"):
                matched.append(ev)
    if not matched:
        return []
    by_template = collections.defaultdict(list)
    for ev in matched:
        by_template[ev.get("msg_template", "")].append(ev)
    findings = []
    for tmpl, evs in by_template.items():
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if ts_list:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            window_ok = span <= window
        else:
            window_ok = True
        if len(evs) < threshold or not window_ok:
            continue
        findings.append({
            "detector": "browser_console_errors",
            "msg_template": tmpl,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


DETECTORS = [
    ("repeated_message", detect_repeated_message),
    ("escalating_health", detect_escalating_health),
    ("restart_loop", detect_restart_loop),
    ("service_unreachable", detect_service_unreachable),
    ("http_error_storm", detect_http_error_storm),
    ("muxer_failure", detect_muxer_failure),
    ("long_idle", detect_long_idle),
    ("json_parse_failure", detect_json_parse_failure),
    ("chaos_verdict", detect_chaos_verdict),
    ("browser_console_errors", detect_browser_console_errors),
    ("segment_gap", detect_segment_gap),
]


def diagnose(finding, events_by_id):
    """Assign a root cause class and a one-line diagnosis.
    Evidence is the surrounding 5 events."""
    det = finding["detector"]
    evidence_ids = finding.get("evidence_event_ids", [])
    context = [events_by_id.get(eid, {}).get("msg", "")[:200] for eid in evidence_ids]

    if det == "service_unreachable":
        return ("upstream_dependency",
                f"Target {finding.get('target','?')} refused connections "
                f"{finding['occurrences']}x. Check that the upstream service is running and reachable.")
    if det == "long_idle":
        return ("upstream_dependency" if finding.get("service") == "TTS" else "code_bug",
                f"Service {finding.get('service','?')} reported idle/warming for "
                f"~{finding['idle_seconds']}s without transitioning to ready. "
                f"Check model load, GPU availability, and warmup logs.")
    if det == "muxer_failure":
        return ("upstream_dependency",
                f"ffmpeg {finding.get('ffmpeg_tag','?')} muxer reported pipeline failures "
                f"{finding['occurrences']}x. Check RTMP target reachability and tee output health.")
    if det == "restart_loop":
        return ("code_bug" if finding.get("max_attempt", 0) >= 3 else "race_condition",
                f"Pipeline restart loop detected ({finding['restart_count']} restarts, "
                f"max attempt {finding['max_attempt']}). Underlying fault not resolved by restart.")
    if det == "escalating_health":
        return ("upstream_dependency" if "TTS" in finding.get("scope", "") else "code_bug",
                f"Health counter for {finding.get('scope','?')} escalated "
                f"{finding['counter_min']}->{finding['counter_max']} within window. "
                f"Watchdog will trigger hard restart soon.")
    if det == "http_error_storm":
        return ("code_bug",
                f"HTTP {finding['status_code']} storm ({finding['occurrences']} occurrences). "
                f"Backend route is failing; check server logs for the cause.")
    if det == "chaos_verdict":
        text = finding.get("verdict_text", "")[:160]
        return ("architecture",
                f"Chaos drill verdict: {text}. "
                f"This indicates a design-level limitation, not a runtime bug.")
    if det == "json_parse_failure":
        return ("upstream_dependency",
                f"LLM returned unparseable JSON {finding['occurrences']}x. "
                f"Check the prompt, the model version, and the parseJson fallback chain.")
    if det == "browser_console_errors":
        return ("code_bug",
                f"Dashboard console reported {finding['occurrences']} repeated errors. "
                f"Backend API may be unavailable; dashboard is keeping last-good-state.")
    if det == "repeated_message":
        msg = finding.get("msg_template", "")[:120]
        return ("code_bug",
                f"Repeated message in scope '{finding.get('scope','?')}': {msg}. "
                f"Investigate root cause; this is a sustained condition, not noise.")
    return ("unknown", "No diagnosis available.")


def severity_for(finding):
    det = finding["detector"]
    occ = finding.get("occurrences", 1)
    sev = "low"
    if det in ("chaos_verdict", "restart_loop"):
        sev = "high"
    elif det in ("muxer_failure", "service_unreachable"):
        sev = "high" if occ >= 2 else "medium"
    elif det in ("http_error_storm", "long_idle", "escalating_health"):
        sev = "high" if occ >= 5 else "medium"
    elif det == "json_parse_failure":
        sev = "medium"
    elif det == "browser_console_errors":
        sev = "medium"
    return sev


def recommended_action(finding):
    det = finding["detector"]
    if det == "service_unreachable":
        target = finding.get("target", "?")
        return (f"1. Verify {target} is running: `curl -fsS {target}/health` (or service-specific probe). "
                f"2. If the service is supposed to be local, check the process is alive (`pgrep -af <svc>`). "
                f"3. If the target is an external API, check status page and recent changes.")
    if det == "long_idle":
        return (f"1. Check the model load path for OOM/timeout. "
                f"2. Increase the watchdog warmup grace period if the load is legitimately slow. "
                f"3. Verify GPU is still attached: `nvidia-smi`.")
    if det == "muxer_failure":
        return (f"1. Verify all RTMP targets are reachable from this host. "
                f"2. Check mediamtx/Rumble endpoint health. "
                f"3. Add the specific failure mode to AGENTS.md \"Common pitfalls\".")
    if det == "restart_loop":
        return (f"1. Read the first restart's underlying error — the loop is a symptom, not the cause. "
                f"2. Add a circuit-breaker around the recurring fault. "
                f"3. If unfixable in this session, surface as BLOCKED with reproduction steps.")
    if det == "escalating_health":
        return (f"1. The watchdog will hard-restart soon; prepare for that. "
                f"2. Add a probe or alert on this counter's trajectory before it crosses the threshold.")
    if det == "http_error_storm":
        return (f"1. Capture the server-side stack trace for one of these requests. "
                f"2. Check the orchestrator HTTP route handling the affected path. "
                f"3. Add an integration test that exercises this path under load.")
    if det == "chaos_verdict":
        return (f"1. Read the full chaos summary and understand why the drill was unsatisfiable. "
                f"2. Decide: fix the architecture to make the drill satisfiable, "
                f"   OR explicitly accept the limitation in AGENTS.md and move on.")
    if det == "json_parse_failure":
        return (f"1. Inspect the raw LLM response (it should be in the orchestrator log). "
                f"2. Extend parseJson's fallback regex if the response has a new wrapping pattern. "
                f"3. If persistent, add the failure rate as a watchdog signal.")
    if det == "browser_console_errors":
        return (f"1. Check whether the dashboard's `/api/dashboard` endpoint is returning an error. "
                f"2. The dashboard's last-good-state hides this from on-air viewers; "
                f"   surface it more loudly (badge in the UI? banner?).")
    if det == "segment_gap":
        return (f"1. The producer loop has stalled silently — no crash, no restart, just silence. "
                f"2. Check the editorial + signal pipeline: is `rankUnused()` returning items? "
                f"3. Check the WS state stream: is `nextInSec` advancing? "
                f"4. Add a watchdog probe that surfaces \"no new segment in N minutes\" as a warn.")
    if det == "repeated_message":
        return (f"1. Read the surrounding context to identify the underlying fault. "
                f"2. Add a dedicated detector for this pattern if it's a recurring class. "
                f"3. Add to the relevant sub-skill's \"Known failure modes\" if it's project-specific.")
    return "Investigate."


def patch_target_for(finding):
    """Return (target_path, section_name, patch_text) or (None, None, None)."""
    det = finding["detector"]
    if det == "muxer_failure":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **ffmpeg tee muxer failures cascade.** A single `[tee @ ...] All tee outputs failed` "
                f"is followed by `[flv @ ...] Failed to update header` and the orchestrator's "
                f"`restarting pipeline (attempt 1)` log. Treat the first tee failure as the root cause; "
                f"downstream messages are consequences. Check RTMP target reachability first.")
    if det == "service_unreachable" and finding.get("target", "").endswith(":8800"):
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **TTS service can take 60-180 seconds to warm.** Distinguish \"loaded:false during warmup\" "
                f"from \"port 8800 not accepting connections at all.\" `curl: (7) Failed to connect` "
                f"means the process is gone or never started; `loaded:false` for >90s means the model "
                f"is stuck loading. Different remediation paths.")
    if det == "long_idle":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **TTS `loaded:false` for >2 minutes is a fault, not a warmup.** "
                f"The 60-180s warmup window is documented, but anything beyond that indicates "
                f"a stuck model load (CUDA OOM, broken HF download, etc.). Add a watchdog probe "
                f"that surfaces this rather than waiting for the watchdog's hard-restart threshold.")
    if det == "http_error_storm":
        return ("dashboard/src/state.ts", None,
                f"// NOTE: when `/api/dashboard` returns 500, the dashboard falls back to last-good-state. "
                f"// This hides outages from on-air viewers. Consider surfacing a degraded-mode badge "
                f"in the top bar so operators notice.")
    if det == "browser_console_errors":
        return ("dashboard/src/state.ts", None,
                f"// NOTE: console warns on every 500 are noisy and easy to miss. "
                f"// Surface a persistent degraded-mode indicator in the TopBar.")
    if det == "chaos_verdict":
        return ("orchestrator/AGENTS.md", "Architecture invariants",
                f"- **The cached SQLite handle survives rename + unlink.** "
                f"Chaos drills that try to corrupt the DB on a running orchestrator are unsatisfiable "
                f"because `better-sqlite3` keeps the inode alive via the open FD. Either accept this "
                f"limitation (and document it) or close the handle when the watchdog detects a "
                f"file-level anomaly.")
    if det == "segment_gap":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **The producer can stall silently.** No error, no restart, no watchdog trip — "
                f"the editorial loop simply stops emitting segments. The watchdog's 5s heartbeats all "
                f"look healthy. Add a watchdog probe that watches the gap between consecutive "
                f"`producing ... from:` log lines and surfaces a warn after >15 minutes of silence.")
    return (None, None, None)


def write_patches(output_dir, findings):
    patches_dir = os.path.join(output_dir, "patches")
    os.makedirs(patches_dir, exist_ok=True)
    written = []
    seen = set()
    for f in findings:
        target = patch_target_for(f)
        if not target or not target[0]:
            continue
        path, section, text = target
        # Dedupe by (target_path, section, text-hash) — multiple findings of
        # the same detector with identical recommendations collapse to one.
        key = (path, section, hash(text))
        if key in seen:
            continue
        seen.add(key)
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", path)
        out_path = os.path.join(patches_dir, f"{safe}.md")
        with open(out_path, "a") as fh:
            if os.path.getsize(out_path) == 0:
                fh.write(f"# Suggested patches for `{path}`\n\n")
            fh.write(f"## Finding: `{f.get('detector')}` — "
                     f"{f.get('occurrences', 1)} occurrences, "
                     f"{f.get('first_seen', '?')} → {f.get('last_seen', '?')}\n\n")
            if section:
                fh.write(f"Append under `## {section}`:\n\n")
            else:
                fh.write(f"Add at an appropriate location:\n\n")
            fh.write(text + "\n\n---\n\n")
        written.append(out_path)
    return written


def build_feature_index(inventory):
    """Load features.json and return:
       features_by_id: {feature_id: {id, slug, status, tokens: set}}
       tokens_to_id: {token: feature_id}
    Where `tokens` includes the feature slug (e.g. "m1-mypy-strict-tts"),
    each worker session UUID, and any handoff filename stem. The
    tokens_to_id map is the reverse index used to find which feature(s)
    a given evidence source path belongs to.

    Returns ({}, {}) if no features.json is found.
    """
    mission_dir = inventory.get("mission_dir")
    if not mission_dir:
        return {}, {}
    features_path = os.path.join(mission_dir, "features.json")
    if not os.path.isfile(features_path):
        return {}, {}
    try:
        with open(features_path) as f:
            doc = json.load(f)
    except Exception:
        return {}, {}
    raw = doc.get("features") if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return {}, {}

    features_by_id = {}
    tokens_to_id = {}
    for feat in raw:
        fid = feat.get("id")
        if not fid:
            continue
        slug = fid
        tokens = {slug}
        for k in ("workerSessionIds", "currentWorkerSessionId", "completedWorkerSessionId"):
            v = feat.get(k)
            if isinstance(v, str):
                tokens.add(v)
            elif isinstance(v, list):
                tokens.update(v)
        # also index milestone-prefixed tokens (e.g., m1, m2)
        m = re.match(r"^(m\d+)", slug)
        if m:
            tokens.add(m.group(1))
        features_by_id[fid] = {
            "id": fid,
            "slug": slug,
            "status": feat.get("status", ""),
            "tokens": tokens,
        }
        for tok in tokens:
            tokens_to_id.setdefault(tok, set()).add(fid)
    return features_by_id, tokens_to_id


def features_affected_for(finding, events_by_id, tokens_to_id):
    """Return the count of distinct features affected by a finding.

    A finding is considered to affect a feature if any of its evidence
    events' source path contains one of the feature's tokens (slug or
    worker session UUID). Returns 0 if no features.json was loaded or
    if no token matched.
    """
    if not tokens_to_id:
        return 0
    affected = set()
    for eid in finding.get("evidence_event_ids", []):
        ev = events_by_id.get(eid, {})
        src = ev.get("source", "") or ""
        for tok, feat_ids in tokens_to_id.items():
            if tok and tok in src:
                affected.update(feat_ids)
    return len(affected)


def main():
    if len(sys.argv) < 2:
        print("usage: cluster-findings.py <output-dir> [--top N]", file=sys.stderr)
        sys.exit(2)
    output_dir = sys.argv[1]
    top_n = 10
    if "--top" in sys.argv:
        i = sys.argv.index("--top")
        top_n = int(sys.argv[i + 1])

    cfg = load_config()
    events_path = os.path.join(output_dir, "events.jsonl")
    if not os.path.exists(events_path):
        print(f"ERROR: {events_path} not found. Run parse-progress-log.sh first.", file=sys.stderr)
        sys.exit(1)
    events = []
    with open(events_path) as f:
        for line in f:
            events.append(json.loads(line))

    events_by_id = {e["id"]: e for e in events}

    # Load features.json (if inventory.json has a mission_dir) and build
    # the feature-token index used by features_affected_for() below.
    inventory_path = os.path.join(output_dir, "inventory.json")
    inventory = {}
    if os.path.isfile(inventory_path):
        try:
            with open(inventory_path) as f:
                inventory = json.load(f)
        except Exception:
            inventory = {}
    _features_by_id, tokens_to_id = build_feature_index(inventory)
    features_loaded = bool(tokens_to_id)

    # Run all detectors
    all_findings = []
    detector_counts = {}
    for name, fn in DETECTORS:
        try:
            fs = fn(events, cfg)
        except Exception as e:
            fs = []
            print(f"detector {name} crashed: {e}", file=sys.stderr)
        detector_counts[name] = len(fs)
        all_findings.extend(fs)

    # Assign id, severity, diagnosis, action
    idgen = dedup_id()
    severity_buckets = collections.Counter()
    for f in all_findings:
        f["id"] = next(idgen)
        f["severity"] = severity_for(f)
        rc, diag = diagnose(f, events_by_id)
        f["root_cause_class"] = rc
        f["diagnosis"] = diag
        f["recommended_action"] = recommended_action(f)
        # LIKELY_KNOWN heuristic: if msg_template mentions "loaded=false" + (TTS or model)
        if f["detector"] == "long_idle" and f.get("idle_seconds", 0) < 90:
            f["likely_known"] = True
        elif f["detector"] == "repeated_message" and "breaker.call" in f.get("msg_template", ""):
            f["likely_known"] = True
        elif f["detector"] == "escalating_health" and f.get("counter_max", 0) <= 2:
            f["likely_known"] = True
        else:
            f["likely_known"] = False
        severity_buckets[f["severity"]] += 1

    # Rank
    weights = cfg["ranking"]
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    for f in all_findings:
        occ = f.get("occurrences", 1)
        last_ts = parse_ts(f.get("last_seen", ""))
        recency_hours_inverse = 0
        if last_ts:
            hours = max(0.0, (now - last_ts).total_seconds() / 3600)
            recency_hours_inverse = max(0.0, 10 - hours)  # higher when recent
        features_affected = features_affected_for(f, events_by_id, tokens_to_id)
        f["distinct_features_affected"] = features_affected
        score = (occ * weights["weight_occurrences"]
                 + recency_hours_inverse * weights["weight_recency_inverse"]
                 + features_affected * weights["weight_features_affected"]
                 - (5.0 if f.get("likely_known") else 0.0) * weights["penalty_likely_known"] / 5.0)
        f["impact_score"] = round(score, 2)

    all_findings.sort(key=lambda x: x["impact_score"], reverse=True)
    primary = all_findings[:top_n]
    appendix = all_findings[top_n:]

    # Write findings.json
    with open(os.path.join(output_dir, "findings.json"), "w") as f:
        json.dump({
            "primary": primary,
            "appendix": appendix,
            "all_count": len(all_findings),
        }, f, indent=2)

    # Write summary.json
    summary = {
        "events_analyzed": len(events),
        "findings_total": len(all_findings),
        "findings_primary": len(primary),
        "severity_buckets": dict(severity_buckets),
        "detector_counts": detector_counts,
        "features_loaded": features_loaded,
        "feature_count": len(_features_by_id),
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Write patches
    patches = write_patches(output_dir, all_findings)
    summary["patch_files_written"] = len(patches)
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"findings.json: {len(all_findings)} total ({len(primary)} primary + {len(appendix)} appendix)")
    print(f"severity buckets: {dict(severity_buckets)}")
    print(f"detector counts: {detector_counts}")
    print(f"patches written: {len(patches)}")


if __name__ == "__main__":
    main()
