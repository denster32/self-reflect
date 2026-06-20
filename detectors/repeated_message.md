# repeated_message

## What it catches

The same `(scope, normalized-message)` appears **N+ times within W seconds**. This is the
broadest detector and catches patterns that don't fit a more specific detector.

## Why this detector exists

Many failure modes in long-running services don't surface as a single loud error; they
show up as a quiet drumbeat of warnings. A message that fires once is noise; a message
that fires ten times in five minutes is a signal.

## Pattern

```
events where level in {warn, error}
group by (scope, msg_template)
where msg_template is msg with:
  - numeric tokens replaced with <NUM>
  - quoted strings replaced with <STR>
  - UUIDs replaced with <UUID>
  - timestamps replaced with <TS>
count >= N
all events fall within W seconds of first occurrence
```

## Threshold

- `count`: 3 (from `config.yaml`)
- `window_seconds`: 600 (10 minutes)

## Output schema

```json
{
  "detector": "repeated_message",
  "scope": "<string>",
  "msg_template": "<string>",
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "window_seconds": <int>,
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- `scope=health` + msg=`health probe exceeded <NUM>ms; resolving to fallback` — this is
  a known fallback path and is high-volume by design. Mark `likely_known: true`.
- `scope=breaker` + msg=`breaker.call` — breaker telemetry is high-volume. Skip unless
  the breaker name itself is in a list of "interesting" breakers (`http.breaker`,
  `llm.anthropic`, `tts.synth`).
- `scope=circuit` — same as `breaker`. Skip routine success events.
- Any scope+msg pair where the message has appeared in AGENTS.md or any sub-skill's
  `## Known failure modes` section. These are documented; mark `likely_known: true`.

## Worked example

```
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
{"level":"warn","scope":"state","msg":"dashboard /api/dashboard 500 — keeping last good state"}
```
→ fires: `scope=state`, `msg_template=dashboard /api/dashboard 500 — keeping last good state`,
3 occurrences, evidence=[id1,id2,id3].
