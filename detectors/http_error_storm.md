# http_error_storm

## What it catches

The same HTTP status code (4xx/5xx) appearing **N+ times within W seconds**. This is
distinct from `repeated_message` because it requires the status code to be structurally
extractable from the message.

## Why this detector exists

A single 500 is normal flakiness. Ten 500s in 30 seconds is an outage. The detector
surfaces the outage at the threshold of meaningful.

## Pattern

```
events where msg matches /(?:\d{3}) (?:Internal Server Error|Bad Gateway|Not Found|Service Unavailable|Unauthorized|Forbidden)/
  OR /HTTP (\d{3})/
  OR /status[=:]?\s*(\d{3})/
  OR /\b([45]\d{2})\b/
extract status code
group by status code
if any group has count >= N AND timespan <= W:
  fire
```

## Threshold

- `count`: 3 (from `config.yaml`)
- `window_seconds`: 60

## Output schema

```json
{
  "detector": "http_error_storm",
  "status_code": <int>,
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>,
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- 401/403 from probe/chaos drills — expected auth challenges.
- 404 from `/api/dashboard` polling during the dashboard cold-start period (first 5s).
- 5xx events that are explicitly `expected: true` in test fixtures (synthetic probes).

## Worked example

```
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
```
→ fires: status_code=500, occurrences=3.
