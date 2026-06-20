#!/usr/bin/env python3
"""render-report.py — Phase 8: render reflection.md from findings.json + events.jsonl.
Usage: render-report.py <output-dir>
"""
import json
import os
import re
import sys
import pathlib

SKILL_DIR = pathlib.Path.home() / ".factory" / "skills" / "self-reflect"
TEMPLATE_PATH = SKILL_DIR / "REPORT-TEMPLATE.md"


def load_events(output_dir):
    path = os.path.join(output_dir, "events.jsonl")
    events_by_id = {}
    with open(path) as f:
        for line in f:
            ev = json.loads(line)
            events_by_id[ev["id"]] = ev
    return events_by_id


def evidence_excerpt(events_by_id, ids, max_lines=5):
    lines = []
    for eid in ids[:max_lines]:
        ev = events_by_id.get(eid, {})
        ts = ev.get("ts", "")
        scope = ev.get("scope", "")
        msg = ev.get("msg", "")[:200]
        # strip ANSI escape codes AND NUL bytes so the rendered .md
        # stays plain text and `file` recognizes it as such
        msg = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", msg)
        msg = msg.replace("\x00", "")
        lines.append(f"[{ts}] [{scope}] {msg}")
    return "\n".join(lines)


def sanitize_for_markdown(text):
    """Strip ANSI codes and NULs from any string before it goes into the
    rendered report. Used for the title and any other rendered field."""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    text = text.replace("\x00", "")
    return text


def missed_patterns(events, all_finding_event_ids):
    """Sample warn/error events that no detector matched.
    Returns a list of (event_id, msg, suggested_detector) tuples."""
    matched_ids = set(all_finding_event_ids)
    sample = []
    for ev in events:
        if ev.get("level") not in ("warn", "error"):
            continue
        if ev["id"] in matched_ids:
            continue
        msg = ev.get("msg", "")
        suggested = "unknown"
        if "consecutive failures" in msg:
            suggested = "escalating_health"
        elif "loaded=false" in msg or "ready=false" in msg:
            suggested = "long_idle"
        elif "Failed to connect" in msg or "ECONNREFUSED" in msg:
            suggested = "service_unreachable"
        elif "tee @ " in msg or "Broken pipe" in msg or "Failed to update header" in msg:
            suggested = "muxer_failure"
        elif "did not return parseable JSON" in msg:
            suggested = "json_parse_failure"
        elif "/api/" in msg or "HTTP" in msg.upper():
            suggested = "http_error_storm"
        elif "restarting" in msg.lower():
            suggested = "restart_loop"
        elif "verdict:" in msg.lower():
            suggested = "chaos_verdict"
        elif "console" in ev.get("source", "").lower():
            suggested = "browser_console_errors"
        else:
            suggested = "repeated_message (above threshold?"
        sample.append((ev["id"], msg[:200], suggested, ev.get("scope", "")))
    return sample[:25]


def main():
    if len(sys.argv) < 2:
        print("usage: render-report.py <output-dir>", file=sys.stderr)
        sys.exit(2)
    output_dir = sys.argv[1]

    with open(os.path.join(output_dir, "findings.json")) as f:
        findings_data = json.load(f)
    with open(os.path.join(output_dir, "summary.json")) as f:
        summary = json.load(f)
    with open(os.path.join(output_dir, "inventory.json")) as f:
        inv = json.load(f)
    events_by_id = load_events(output_dir)
    events = list(events_by_id.values())

    primary = findings_data["primary"]
    appendix = findings_data["appendix"]
    sev_buckets = summary["severity_buckets"]

    # Executive summary
    if not primary:
        exec_summary = (
            "No findings matched any detector threshold. "
            "Possible causes: (a) the log corpus is too sparse, (b) thresholds in config.yaml are too strict, "
            "or (c) the detectors do not yet cover the failure shapes present in this corpus. "
            "Inspect the `Missed patterns` section below for events that should have triggered but did not."
        )
    else:
        top = primary[0]
        exec_summary = (
            f"Analyzed {summary['events_analyzed']} events from "
            f"{len(inv.get('mission_artifacts',{}).get('present',[]))} mission artifacts and "
            f"{len(inv.get('run_artifacts',{}).get('present',[]))} runtime logs. "
            f"Detected {summary['findings_total']} findings ({summary['findings_primary']} primary, "
            f"{len(appendix)} appendix). Severity: {sev_buckets}. "
            f"Highest-impact pattern: `{top['detector']}` — {top.get('diagnosis','?')}"
        )

    # Detector health table
    detector_rows = []
    for det_name in [
        "repeated_message", "escalating_health", "restart_loop",
        "service_unreachable", "http_error_storm", "muxer_failure",
        "long_idle", "json_parse_failure", "chaos_verdict", "browser_console_errors",
        "segment_gap",
    ]:
        cnt = summary.get("detector_counts", {}).get(det_name, 0)
        over = "yes" if cnt > 50 else ""
        under = "yes" if cnt == 0 else ""
        detector_rows.append(f"| `{det_name}` | {cnt} | {over} | {under} |")

    # Findings sections
    findings_md = []
    for i, f in enumerate(primary, start=1):
        title = sanitize_for_markdown(f.get("diagnosis") or f.get("detector", "?"))[:120]
        evidence = evidence_excerpt(events_by_id, f.get("evidence_event_ids", []))
        sev = f.get("severity", "?")
        rc = f.get("root_cause_class", "?")
        occ = f.get("occurrences", 1)
        first = f.get("first_seen", "?")
        last = f.get("last_seen", "?")
        likely = "yes" if f.get("likely_known") else "no"
        diag = sanitize_for_markdown(f.get("diagnosis", "?"))
        action = sanitize_for_markdown(f.get("recommended_action", "?"))
        patch_tgt = patch_target_for_label(f)
        impact = f.get("impact_score", "?")
        features = f.get("distinct_features_affected", 0)
        findings_md.append(
            f"### {i}. {title}\n\n"
            f"- **Detector:** `{f.get('detector','?')}`\n"
            f"- **Severity:** {sev} ({rc})\n"
            f"- **Occurrences:** {occ}\n"
            f"- **Distinct features affected:** {features}\n"
            f"- **First seen:** {first}\n"
            f"- **Last seen:** {last}\n"
            f"- **Likely known?** {likely}\n"
            f"- **Impact score:** {impact}\n\n"
            f"**Diagnosis:** {diag}\n\n"
            f"**Evidence:**\n\n```\n{evidence}\n```\n\n"
            f"**Recommended action:** {action}\n\n"
            f"**Patch target:** {patch_tgt}\n"
        )

    # Appendix
    appendix_md = []
    for f in appendix[:20]:
        title = sanitize_for_markdown(f.get("diagnosis") or f.get("detector", "?"))[:100]
        appendix_md.append(
            f"- `{f.get('detector','?')}` ({f.get('severity','?')}, impact={f.get('impact_score','?')}): "
            f"{title} — {f.get('occurrences',1)} occurrences, "
            f"{f.get('first_seen','?')} → {f.get('last_seen','?')}"
        )

    # Missed patterns
    # Collect ALL evidence event ids from findings (not just the first 10)
    all_matched_ids = set()
    for f in primary + appendix:
        for eid in f.get("evidence_event_ids", []):
            all_matched_ids.add(eid)
    missed = missed_patterns(events, all_matched_ids)

    missed_rows = []
    for eid, msg, suggested, scope in missed:
        missed_rows.append(
            f"| `{eid}` | `{scope}` | {sanitize_for_markdown(msg)[:100]} | {suggested} |"
        )

    # Threshold tuning
    detector_counts = summary.get("detector_counts", {})
    tuning = []
    for det, cnt in detector_counts.items():
        if cnt == 0:
            tuning.append(
                f"- `{det}` fired 0 times. Either (a) the corpus doesn't contain this pattern, "
                f"(b) the threshold is too strict, or (c) the regex is too narrow. "
                f"Inspect `missed_patterns` to disambiguate."
            )
        elif cnt > 50:
            tuning.append(
                f"- `{det}` fired {cnt} times — possibly over-triggered. "
                f"Consider adding to the `What to skip` section of its detector spec."
            )
    if not tuning:
        tuning.append("- No tuning recommended.")

    # Patch file list
    patches_dir = os.path.join(output_dir, "patches")
    patch_files = []
    if os.path.isdir(patches_dir):
        for fn in sorted(os.listdir(patches_dir)):
            patch_files.append(f"- `patches/{fn}`")

    # Render — substitute known placeholders, then drop any remaining
    # placeholder section by inserting real findings in its place.
    template = TEMPLATE_PATH.read_text()
    rendered = (
        template
        .replace("{{MISSION_DIR}}", str(inv.get("mission_dir") or "(none)"))
        .replace("{{RUN_DIR}}", str(inv.get("run_dir") or "(none)"))
        .replace("{{ANALYZED_AT}}", inv.get("analyzed_at", "?"))
        .replace("{{EVENT_COUNT}}", str(summary.get("events_analyzed", 0)))
        .replace("{{FINDING_COUNT}}", f"{summary['findings_primary']} (+ {len(appendix)} appendix)")
        .replace("{{SEVERITY_BUCKETS}}", ", ".join(f"{k}={v}" for k, v in sev_buckets.items()))
        .replace("{{EXECUTIVE_SUMMARY}}", exec_summary)
        .replace("{{DETECTOR_HEALTH_ROWS}}", "\n".join(detector_rows))
        .replace("{{MORE_FINDINGS}}", "yes" if appendix else "")
        .replace("{{APPENDIX_FINDINGS}}", "\n".join(appendix_md) if appendix_md else "(none)")
        .replace("{{MISSED_PATTERNS_TABLE}}",
                 "| Event ID | Scope | Message | Suggested detector |\n"
                 "| --- | --- | --- | --- |\n" + "\n".join(missed_rows) if missed_rows else
                 "(none — every warn/error event matched at least one detector)")
        .replace("{{THRESHOLD_TUNING_SUGGESTIONS}}", "\n".join(tuning))
        .replace("{{PATCH_FILE_LIST}}", "\n".join(patch_files) if patch_files else "(no patches generated)")
    )

    # Strip any remaining placeholders (the dummy top-finding block in template)
    rendered = re.sub(r"\{\{[A-Z_]+\}\}", "", rendered)
    # Drop the placeholder finding block — it's from the template, not real data.
    rendered = re.sub(
        r"### 1\. \(see sections below\).*?(?=^## |\Z)",
        "",
        rendered,
        flags=re.DOTALL | re.MULTILINE,
    )

    # Strip the template's inert placeholder block (the comment + appendix
    # block were left over from the template). We re-add the appendix
    # AFTER the real findings, just before Self-Review.
    rendered = re.sub(
        r"<!--.*?-->\s*",
        "",
        rendered,
        flags=re.DOTALL,
    )
    # Drop the appendix section from the template — we re-add it after findings
    rendered = re.sub(
        r"\{\{#if MORE_FINDINGS\}\}.*?\{\{/if\}\}",
        "",
        rendered,
        flags=re.DOTALL,
    )

    # Insert the real findings + appendix just before "## Self-Review"
    sections_text = "\n\n".join(findings_md)
    appendix_text = ""
    if appendix_md:
        appendix_text = (
            "\n\n## Appendix: Additional Findings\n\n"
            + "\n".join(appendix_md)
            + "\n"
        )
    if "## Self-Review" in rendered:
        rendered = rendered.replace(
            "## Self-Review",
            sections_text + appendix_text + "\n\n## Self-Review",
        )
    else:
        rendered = rendered + "\n\n" + sections_text + appendix_text

    out_path = os.path.join(output_dir, "reflection.md")
    # belt-and-braces: sanitize the entire rendered text one more time
    # (in case any string slipped through individual sanitize calls)
    rendered = sanitize_for_markdown(rendered)
    with open(out_path, "w") as f:
        f.write(rendered)
    print(f"reflection.md written: {out_path}")


def patch_target_for_label(f):
    det = f.get("detector")
    if det == "muxer_failure":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "service_unreachable" and "8800" in str(f.get("target", "")):
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "long_idle":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "http_error_storm":
        return "`dashboard/src/state.ts`"
    if det == "browser_console_errors":
        return "`dashboard/src/state.ts`"
    if det == "chaos_verdict":
        return "`orchestrator/AGENTS.md` (Architecture invariants)"
    if det == "segment_gap":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    return "(code fix — no markdown patch)"


if __name__ == "__main__":
    main()
