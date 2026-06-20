# Contributing to self-reflect

Thanks for considering a contribution. This guide explains how to add a new
detector, refine an existing one, and submit a PR that the maintainers can merge
quickly.

## What the project is

self-reflect is a Droid skill (an LLM-readable instruction bundle + a small set
of stdlib-only helper scripts) for mission self-reflection. It reads a mission's
`progress_log.jsonl`, `handoffs/`, `evidence/`, and external runtime logs,
detects recurring failure patterns, diagnoses their root causes, and writes a
PR-ready bundle of report + JSON findings + suggested patches.

The repo is intentionally small:

- **Markdown contracts** (`detectors/*.md`) — what each detector does
- **Python helpers** (`scripts/*.py`) — stdlib-only glue
- **One config file** (`config.yaml`) — tunable thresholds
- **One entry point** (`SKILL.md`) — the 10-phase process

There are no runtime dependencies, no API keys, no network calls.

## Adding a new detector

A detector is the smallest unit of contribution. Each one has four parts:

### 1. The detector spec (`detectors/<name>.md`)

Markdown, ~50 lines. Structure:

```markdown
# <name>

## What it catches
<1-2 sentences describing the failure shape>

## Why this detector exists
<1 short paragraph: what gets missed without it>

## Pattern
<regex or structural description of what to match>

## Threshold
<bullet list of values from config.yaml>

## Output schema
```json
{
  "detector": "<name>",
  ...
}
```

## What to skip
<false-positive guard rails>

## Worked example
<3-5 sample events with the expected finding>
```

The spec is **the API**. Edit the spec, the code follows.

### 2. The config block (`config.yaml`)

Add a section matching the detector name:

```yaml
<name>:
  count: 3
  window_seconds: 600
  patterns:
    - "..."
```

If the detector has no thresholds, the block can be empty.

### 3. The detector function (`scripts/cluster-findings.py`)

Implement `detect_<name>(events, cfg)` and add `("<name>", detect_<name>)` to
the `DETECTORS` list.

Convention: each function takes the normalized event list and the parsed
config, and returns a list of finding dicts. Use the helpers in the file
(`parse_ts`, `dedup_id`, etc.) rather than rolling your own.

Each finding must include:

- `detector` — the detector name (string)
- `occurrences` — count (int)
- `first_seen`, `last_seen` — ISO timestamps (may be empty strings)
- `evidence_event_ids` — list of event IDs from `events.jsonl`

Optional but recommended: `scope`, `severity` (auto-assigned later), or
detector-specific fields like `target`, `gap_seconds`, `verdict_text`.

### 4. The diagnosis + patch wiring

In the same file, add cases to `diagnose()`, `severity_for()`,
`recommended_action()`, and `patch_target_for()` for your detector.

Add a label in `scripts/render-report.py::patch_target_for_label()` so the
report's "Patch target:" line is human-readable.

### 5. Update the detector table in `SKILL.md`

Add one row. Keep the format consistent with the existing 11 rows.

### 6. Validate

Run the skill against a corpus where your pattern is present (or simulate one
by editing existing log files). Confirm:

- The detector fires (`detector_counts[<name>] > 0` in `summary.json`).
- The finding appears in `findings.json` with sensible `severity`, `diagnosis`,
  `recommended_action`.
- If `patch_target_for()` returns non-null, a patch file appears in
  `patches/<target>.md`.

If the pattern is not in your corpus, add a synthetic log file to `.run/` (or
to the test mission's `progress_log.jsonl`) and verify the detector fires on
it. Clean up the synthetic data before submitting the PR.

## Refining an existing detector

Iterate by reading `reflection.md` → `## Self-Review` → `### Missed patterns`.

For each missed pattern row:

- **Regex too narrow** — loosen the regex in `detectors/<name>.md`.
- **Threshold too high** — tune `config.yaml` (lower `count` or `delta`).
- **Pattern class is new** — write a new `detectors/<name>.md` from scratch.

Don't change the detector's *name* in a refactor PR — that breaks the
historical `findings.json` comparisons. Add a new detector and deprecate the
old one in `CHANGELOG.md` if the behavior change is significant.

## Style

- **Python: stdlib only.** No `pip install`. If your detector needs a third-
  party parser, write a small inline implementation (or a vendored
  single-file module under `scripts/`) instead.
- **Markdown: keep specs tight.** ~50 lines per detector. If a spec grows
  past 100 lines, the detector is probably doing too much — split it.
- **Naming: kebab-case for files, snake_case for functions.** Detector names
  in `DETECTORS` use snake_case to match Python conventions.

## Submitting a PR

1. Run the skill against your local test corpus. Confirm `summary.json`
   looks right.
2. Update `CHANGELOG.md` under `## [Unreleased]`:
   - Added: new detector name
   - Changed: refined detector
   - Fixed: bug in a detector
3. Open a PR with:
   - The detector spec
   - The Python function
   - The config block
   - The SKILL.md table update
   - The CHANGELOG.md entry
   - A short description of the failure shape you targeted

## What NOT to do

- Don't add real `pip install` dependencies. Keep it stdlib-only.
- Don't auto-edit the user's source files. The skill writes patches to
  `patches/<target>.md`; the user pastes them manually. Don't change this.
- Don't add detectors that phone home, scrape external services, or read
  credentials. The skill operates on logs only.
- Don't add a detector that duplicates an existing one. If you want to
  refine, edit the existing detector; if you want to expand scope, write a
  new one with a different name.

## Maintainers

The repo is small enough that the original author(s) can review PRs within a
day or two. Be patient. If a PR stalls, ping the maintainers with the PR
link and a one-line summary.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License (see `LICENSE`).
