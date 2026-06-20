# muxer_failure

## What it catches

ffmpeg tee/flv pipeline errors. These are emitted on **stderr** by ffmpeg with a
distinctive prefix format (`[tee @ 0x...]`, `[flv @ 0x...]`) that doesn't fit the
normal pino JSON envelope.

## Why this detector exists

ffmpeg errors are the loudest signal of a stream pipeline failure. They happen fast
(within 1-2 seconds of the actual fault) and they precede the orchestrator's recovery
attempt. Catching them gives a precise root cause for any subsequent `restarting
pipeline` event.

## Pattern

```
events where msg matches any of:
  - /\[tee @ [^\]]+\]/
  - /\[flv @ [^\]]+\]/
  - /Broken pipe/
  - /Failed to update header/
  - /All tee outputs failed/
  - /Error muxing a packet/
  - /Slave muxer/
fire on any occurrence
```

## Threshold

- Any occurrence fires (from `config.yaml: muxer_failure.patterns`)

## Output schema

```json
{
  "detector": "muxer_failure",
  "ffmpeg_tag": "<tee|flv|aost|out|null>",
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- `[flv @ ...] Failed to update header with correct duration.` at stream shutdown —
  these are emitted during normal teardown when the FLV header is no longer being
  written. To distinguish, check if the next event in the stream is a graceful
  `stream stopped` or `pipeline stopped`. If yes, this is teardown noise.

## Worked example

```
{"msg":"[tee @ 0x5b8a2716e400] All tee outputs failed."}
{"msg":"[flv @ 0x5b8a279ed680] Failed to update header with correct duration."}
{"msg":"[aost#0:1/aac @ 0x5b8a27177640] Error submitting a packet to the muxer: Broken pipe"}
```
→ fires: ffmpeg_tag=tee (also flv, aost), occurrences=3.
