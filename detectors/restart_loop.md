# restart_loop

## What it catches

A "restarting" or "rebuild" event followed by another restart within **W seconds**.
This indicates the recovery is failing — the system tried to restart, the restart
didn't hold, and another restart is needed.

## Why this detector exists

A single restart is healthy behavior (the watchdog worked). Two restarts in a row is a
strong signal that the underlying fault has not been resolved. Three is a loop that
will burn CPU and produce log spam without making progress.

## Pattern

```
events where msg matches /restarting (?:\w+ )?(?:pipeline )?\(attempt (\d+)\)/
sort by ts
for each event:
  if any other restart event is within W seconds AND attempt > 1:
    fire with all events in the cluster
```

## Threshold

- `followup_window_seconds`: 60 (from `config.yaml`)

## Output schema

```json
{
  "detector": "restart_loop",
  "scope": "<string>",
  "restart_count": <int>,
  "max_attempt": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>,
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- A single restart event with no followup. This is normal watchdog behavior.
- Restarts that occur >W seconds apart (likely unrelated).

## Worked example

```
{"scope":"main","msg":"restarting pipeline (attempt 1): encoder not alive — waiting 3s"}
# (33 seconds later)
{"scope":"main","msg":"restarting pipeline (attempt 2): encoder not alive — waiting 6s"}
```
→ fires: 2 restarts, max_attempt=2, window=33s.
