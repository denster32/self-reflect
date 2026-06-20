# long_idle

## What it catches

A service that reports an "idle" or "not ready" state (e.g., `loaded=false`,
`ready=false`, `warming`) for **more than X seconds without ever transitioning to the
ready state**. This is distinct from `repeated_message` because the absence of
transition matters more than the repetition of the message.

## Why this detector exists

Models that take 30-60 seconds to warm up are normal. Models that take 5 minutes to
warm up (or never warm up) indicate a stuck load or a CUDA/OOM issue. The detector
surfaces the long stall, especially when probe polls are spaced regularly and the
state never changes.

## Pattern

```
events where msg matches any of:
  - /loaded[=:]false/
  - /ready[=:]false/
  - /warming/
group by source file
find the longest run of consecutive "still idle" events where no event has
  msg matching /loaded[=:]true/ or /ready[=:]true/ or /model warmed/
if idle_duration > X seconds:
  fire with idle duration and last_seen ts
```

## Threshold

- `idle_seconds`: 120 (from `config.yaml`)
- `idle_markers`: `loaded=false`, `ready=false`, `warming`

## Output schema

```json
{
  "detector": "long_idle",
  "service": "<TTS|model|...>",
  "idle_seconds": <int>,
  "poll_count": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso)",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- The first 60-90 seconds of a service warmup. Track this with a config flag
  `idle_warmup_grace_seconds: 60` — events within this window after process start
  are not considered idle failures.
- Idle states for services the user explicitly disabled (e.g., `enabled: false` in
  feature flags).

## Worked example

```
poll=1  t=0s    loaded=false
poll=2  t=5s    loaded=false
poll=3  t=10s   loaded=false
...
poll=36 t=176s  loaded=false
```
→ fires: service=TTS, idle_seconds=176, poll_count=36.
