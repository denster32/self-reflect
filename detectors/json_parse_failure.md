# json_parse_failure

## What it catches

LLM/JSON output that the system tried to parse but failed. The CUI BONO orchestrator
has a `parseJson` helper that strips fences and falls back to a balanced-block regex.
A failure here means even the fallback gave up.

## Why this detector exists

LLM output is non-deterministic. A small fraction of responses come back wrapped in
prose that even the robust extractor can't parse. When this rate climbs (e.g., from
1% to 10%), it usually means the prompt changed, the model was upgraded, or the
provider is having a bad day.

## Pattern

```
events where msg matches any of:
  - /did not return parseable JSON/i
  - /LLM did not return parseable JSON/i
  - /completeJSON/ and level in {error, warn}
  - /parseJson/
  - /JSON\.parse/
  - /Unexpected token .* in JSON/
fire on any occurrence (count and group by scope/msg-template)
```

## Threshold

- Any occurrence fires (from `config.yaml: json_parse_failure.patterns`)

## Output schema

```json
{
  "detector": "json_parse_failure",
  "scope": "<string>",
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso)",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- Parse failures inside test fixtures (the validator intentionally passes malformed
  JSON to verify `parseJson` rejects it). Look for `scope=test` or `scope=fuzz`.
- A single occurrence per session is noise; require at least 2 in a 30-minute window
  before firing.

## Worked example

```
{"level":"error","scope":"editorial","msg":"LLM did not return parseable JSON: <truncated>..."}
```
→ fires: scope=editorial, occurrences=1. If a second event fires within 30 minutes,
upgrade to `escalating` and add to top findings.
