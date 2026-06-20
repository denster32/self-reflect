# segment_gap

## What it catches

A segment starts producing (or rendering) but **no subsequent segment starts within
X minutes**. This is the silent failure: the pipeline is alive, the watchdog is happy,
no error is logged — but the producer has stopped generating new segments. The on-air
stream goes silent.

## Why this detector exists

Most failure detectors surface loud signals (errors, exceptions, restarts). The most
insidious failure mode in a 24/7 stream is the *quiet* one: the producer loop exits
cleanly, the watchdog sees a healthy stream mixer, but no new editorial packages flow.
Operators notice when viewers complain about silence. This detector surfaces the
silence *before* viewers do.

## Pattern

```
events where msg matches any of:
  - /producing (\w+) from:/
  - /rendering segment/
  - /seg=(\d+)/
  - /\[tts-render\] seg=/
sort by ts
for each pair (prev, next) where next.ts - prev.ts > gap_seconds:
  fire a gap finding with:
    - last_segment_marker: the title/type from prev.msg
    - gap_seconds: next.ts - prev.ts
    - expected_within_seconds: gap_seconds (the configured threshold)
```

## Threshold

- `gap_minutes`: 15 (default). Tune up for sparse schedules (news streams might wait
  30 minutes between segments), down for fast-cycle schedulers (every 60 seconds).

## Output schema

```json
{
  "detector": "segment_gap",
  "last_segment_marker": "<string>",
  "gap_seconds": <int>,
  "expected_within_seconds": <int>,
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- The very last segment before the log ends. A gap that runs off the end of the log
  is not actionable from logs alone (the next segment may have started in a log
  file we don't have). Only fire gaps between two observed segment starts.
- Gaps shorter than `gap_minutes` (by definition — these are normal inter-segment
  spacing).
- Segments produced by the same logical source within a few seconds (e.g., a
  `producing primary_source_review` followed 5s later by `producing briefing`).
  Treat consecutive different segment types as one logical "production cycle" if
  they are within a small window (e.g., 60s).

## Worked example

```
{"ts":"2026-06-19T13:32:25.955Z","scope":"scheduler-produce","msg":"producing primary_source_review from: <title A>"}
{"ts":"2026-06-19T13:32:59.883Z","scope":"scheduler-produce","msg":"producing briefing from: <title B>"}
{"ts":"2026-06-19T13:33:29.913Z","scope":"scheduler-produce","msg":"producing primary_source_review from: <title C>"}
# (no more producing events for 15+ minutes)
```
→ fires: gap_seconds=900+, last_segment_marker=`primary_source_review from: <title C>`.

## Cross-reference with other detectors

- If a `restart_loop` fires in the same window as the gap, the gap is a *consequence*
  of the restart (not an independent finding). Mark `likely_known: true`.
- If `service_unreachable` (TTS or LLM) fires in the same window, the gap is a
  *consequence* of the upstream outage. Mark `likely_known: true` and reference the
  upstream finding in the diagnosis.
- If `muxer_failure` fires in the same window, the gap is likely a stream-pipeline
  consequence. Mark `likely_known: true`.
