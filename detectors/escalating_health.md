# escalating_health

## What it catches

A "consecutive failures" or similar counter **incrementing** across events. This is a
distinct failure shape from `repeated_message`: instead of the same warning repeating,
the same counter grows, which usually means the system is trying to recover and failing
to recover.

## Why this detector exists

The CUI BONO orchestrator uses a watchdog pattern: `consecutive failures: 1`, `: 2`,
`: 3`... until the threshold triggers a hard restart. By the time the counter reaches
the threshold, the system has been degraded for minutes. The detector surfaces the
escalation so the failure mode is visible *before* the threshold trip.

## Pattern

```
events where msg matches /consecutive (?:failures?|errors?): (\d+)/
group by scope (or breaker name when present)
sort by ts
if max(counter) - min(counter) >= delta within W seconds:
  fire
```

## Threshold

- `delta`: 3 (from `config.yaml`)
- `window_seconds`: 300 (5 minutes)

## Output schema

```json
{
  "detector": "escalating_health",
  "scope": "<string>",
  "counter_min": <int>,
  "counter_max": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- Counters that reset back to 1 inside the window (normal recovery). Only fire if the
  trend is monotonically non-decreasing (allow plateaus but no resets).
- A single counter reading without a precursor (no `: 1` event in the window). The
  detector needs at least 2 readings to compute a delta.

## Worked example

```
{"scope":"stream","msg":"[encoder] heartbeat target process unavailable (consecutive failures: 1)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 1)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 2)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 3)"}
```
→ fires (TTS): counter 1→3, delta=2... if delta>=3 fires; otherwise note as "watching".
