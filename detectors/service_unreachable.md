# service_unreachable

## What it catches

Network-level failures indicating a service we depend on is **not reachable**:
connection refused, connect failed, ECONNREFUSED, connection reset.

## Why this detector exists

These errors are often buried in chain messages. They appear as `Error: connect
ECONNREFUSED 127.0.0.1:8800` deep in a stack trace and the user only sees the
high-level symptom ("TTS unhealthy"). Surfacing them explicitly makes the
upstream cause visible.

## Pattern

```
events where msg matches any of:
  - /Failed to connect to .+ (?:port \d+|after \d+ ms)/
  - /ECONNREFUSED/
  - /connection refused/i
  - /Connection reset/i
  - /no route to host/i
fire on any occurrence (these are always actionable)
```

## Threshold

- Any occurrence fires (from `config.yaml: service_unreachable.patterns`)

## Output schema

```json
{
  "detector": "service_unreachable",
  "target": "<host:port or service name extracted from msg>",
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- `connection refused` during a known shutdown sequence (e.g., `scope=watchdog` with
  msg containing "shutting down"). These are expected.
- `ECONNREFUSED` inside a circuit-breaker "open" event — already captured by
  `escalating_health` if the counter is rising.

## Worked example

```
{"level":"error","scope":"http","msg":"Error: connect ECONNREFUSED 127.0.0.1:8800"}
```
→ fires: target=`127.0.0.1:8800`, occurrences=1.
