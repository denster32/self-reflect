# chaos_verdict

## What it catches

Explicit `Verdict:` lines from chaos-drill summaries, plus the `Results:` block that
precedes them. Chaos drills are intentional fault-injection experiments; their verdicts
are the most authoritative signal of an architectural limitation.

## Why this detector exists

A chaos drill is run *because* someone suspects the system has a hole. The verdict is
the answer. Missing the verdict in a self-reflection run is a serious gap.

## Pattern

```
files in run-dir matching chaos patterns:
  - filename contains "chaos"
  - filename contains "summary"
  - filename contains "verdict"
for each file:
  scan for lines starting with "Verdict:" (case-insensitive)
  also extract the preceding "Results:" or "Strategy attempted:" block for context
emit one finding per Verdict: line
```

## Threshold

- Any verdict line fires (from `config.yaml: chaos_verdict.verdict_markers`)

## Output schema

```json
{
  "detector": "chaos_verdict",
  "verdict_text": "<verbatim text after 'Verdict:'>",
  "strategy": "<text of Strategy attempted: block, if present>",
  "results": "<text of Results: block, if present>",
  "source_file": "<relative path>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- Verdicts that explicitly state the chaos drill was a success (`Verdict: ... passed`,
  `Verdict: ... survived`). These are NOT findings.
- Verdicts from chaos drills whose target was a different system (e.g., a chaos drill
  on a CI runner, not on CUI BONO). Verify the file references the project under test
  before firing.

## Worked example

```
=== VAL-OBS-036: chaos drill outcome (round 2) ===
Strategy attempted: fresh orchestrator on :4105 ...
Results:
  before           deps.db = true
  after-rename     deps.db = true   <-- cached handle survives
  after-unlink     deps.db = true   <-- inode still alive via FD
Verdict: the chaos drill is unsatisfiable against a running orchestrator.
```
→ fires: verdict_text=`the chaos drill is unsatisfiable against a running orchestrator.`,
strategy=..., results=..., source_file=`.run/val-obs-round2/val-obs-036-chaos-summary.log`.
