# browser_console_errors

## What it catches

JavaScript console errors that the dashboard (or a headless browser session) emits
while running. CUI BONO's dashboard polls `/api/dashboard` every 20 seconds and
emits a `console.warn` when the request returns >=500.

## Why this detector exists

The dashboard renders a "last good state" fallback when the API is down. From the
on-air stream's perspective, this looks fine — the frame still updates. But the
underlying API is broken, and the user might not know without checking the dashboard
console. This detector surfaces dashboard-side faults that are otherwise invisible
from the orchestrator logs.

## Pattern

```
files matching:
  - filename contains "console"
  - filename contains "browser"
  - filename contains "agent-browser"
for each line:
  classify:
    - "[ERROR]" or level:"error" → error
    - "[log]" with level:"warn" → warn
    - "[log]" with level:"error" → error
    - default → info
extract msg text
group by (msg-template)
if count >= N within W seconds AND any classified as error:
  fire
```

## Threshold

- `count`: 3 (from `config.yaml`)
- `window_seconds`: 120

## Output schema

```json
{
  "detector": "browser_console_errors",
  "msg_template": "<string>",
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso)",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- Errors that mention `favicon.ico` — universal browser artifact, ignore.
- Errors during the dashboard's first 5 seconds (cold start; React/D3 initialization
  often emits benign warnings before settling).
- Errors from a browser session that has been explicitly flagged as a "chaos"
  context (look for filenames matching `chaos-*` or session labels with "chaos").

## Worked example

```
{"time":"2026-06-19T13:30:25.062Z","level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"time":"2026-06-19T13:30:45.063Z","level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"time":"2026-06-19T13:31:05.063Z","level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
```
→ fires: msg_template=`dashboard /api/dashboard 500 — keeping last good state`,
occurrences=3.
