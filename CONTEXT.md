# self-reflect — single-file context for Claude

> A Droid-compatible skill for mission self-reflection and self-correction (v1.0.0).

## TL;DR

Reads execution logs, detects 11 recurring failure patterns, diagnoses root causes, writes a PR-ready bundle of report + JSON + suggested patches.

Validated: **8/8 known real failure patterns caught** in v1.

## Detector menu (v1.0.0)

# segment_gap

## What it catches

A segment starts producing (or rendering) but **no subsequent segment starts within
X minutes**. This is the silent failure: the pipeline is alive, the watchdog is happy,
no error is logged — but the producer has stopped generating new segments. The on-air
stream goes silent.

## Why this detector exists

Most failure detectors surface loud signals (errors, exceptions, restarts). The most
insidious failure mode in a 24/7 stream is the *quiet* one: the producer loop exits
cleanly, the watchdog sees a healthy stream mixer, but no new editorial packages flow.
Operators notice when viewers complain about silence. This detector surfaces the
silence *before* viewers do.

## Pattern

```

---


## File: `LICENSE`

```
MIT License

Copyright (c) 2026 self-reflect contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

## File: `README.md`

```
# self-reflect

> A Droid skill for mission self-reflection and self-correction. Reads execution
> logs from a mission's `progress_log.jsonl`, `handoffs/`, `evidence/`, and external
> runtime logs; detects recurring failure patterns; diagnoses root causes; and
> produces a PR-ready bundle of report + JSON findings + suggested patches to
> `AGENTS.md` or sub-skill `Known Failure Modes`.

```
detect → diagnose → patch → iterate
```

## Status

**v1.0.0** — initial release. Validated against CUI BONO's runtime logs and a real
mission: **8/8 known real failure patterns caught** in v1. See `CHANGELOG.md` for
detector coverage and iteration history.

## What it does

In a single run, self-reflect:

1. **Discovers** mission artifacts (`features.json`, `progress_log.jsonl`, `handoffs/`,
   `evidence/`, `library/`, sub-skill `SKILL.md` files) and external runtime logs
   (`.run/`).
2. **Normalizes** everything into a single event stream (`events.jsonl`).
3. **Detects** recurring failure patterns via a menu of 11 detectors (see below).
4. **Diagnoses** each finding — assigns a root-cause class
   (`upstream_dependency`, `code_bug`, `architecture`, `race_condition`, etc.) and
   pulls surrounding context.
5. **Ranks** by impact score that factors occurrence count, recency, and number of
   distinct features affected (cross-referenced from `features.json`).
6. **Generates corrective actions** — concrete file edits, tests, or config changes.
7. **Writes patches** to `patches/<target>.md` (markdown snippets the user pastes
   manually — the skill never auto-edits source files).
8. **Self-reviews** its own output — flags false positives and missed patterns in the
   report's `Self-Review` section so iteration is measurable.

The skill is **read-only by design**. It writes only to `--output-dir`.

## Detector menu (v1.0.0 — 11 detectors)

| Detector | Catches | Default threshold |
| --- | --- | --- |
| `repeated_message` | same `(scope, msg)` N+ times in W | N=3, W=10min |
| `escalating_health` | `consecutive failures` counter rising | delta >= 2 in 5min |
| `restart_loop` | pipeline restart followed by another within W | W=60s |
| `service_unreachable` | ECONNREFUSED, Failed to connect, etc. | any |
| `http_error_storm` | same HTTP status N+ times in W | N=3, W=60s |
| `muxer_failure` | ffmpeg tee/flv broken pipe | any |
| `long_idle` | `loaded=false` repeated >X seconds with no transition | X=120s |
| `json_parse_failure` | LLM returned unparseable JSON | any |
| `chaos_verdict` | explicit `Verdict:` line in chaos summary | any |
| `browser_console_errors` | repeated dashboard console error | N=3 in 120s |
| `segment_gap` | segment starts but next start >X min later | X=15min |

Each detector has a markdown contract in `detectors/<name>.md` describing the
pattern, threshold, output schema, and what to skip.

## Install

### Personal scope (recommended for cross-project use)

```bash
mkdir -p ~/.factory/skills
cp -r self-reflect ~/.factory/skills/self-reflect
```

### Project scope (committed to the repo)

```bash
mkdir -p .factory/skills
cp -r self-reflect .factory/skills/self-reflect
git add .factory/skills/self-reflect
```

Requires Python 3.10+ (stdlib only — no `pip install`).

## Usage

```bash
# Default: auto-discovers mission dir + .run/
droid exec --auto high --prompt "Run the self-reflect skill"

# Explicit paths
droid exec --auto high --prompt "Run the self-reflect skill \
  --mission-dir /home/server/.factory/missions/fec95956-c7a8-4c94-9aab-d1ebda54d857 \
  --run-dir /home/server/cui bono/.run \
  --output-dir /home/server/cui bono/qa-results/self-reflection"

# Focused on one feature
droid exec --auto high --prompt "Run the self-reflect skill --feature <id> --since <iso>"
```

Or invoke the helpers directly (no Droid required):

```bash
OUT=/tmp/self-reflection
mkdir -p "$OUT"

bash self-reflect/scripts/list-mission-artifacts.sh \
  "$MISSION_DIR" "$RUN_DIR" "$OUT"

bash self-reflect/scripts/parse-progress-log.sh \
  "$OUT/inventory.json" "$OUT"

python3 self-reflect/scripts/cluster-findings.py "$OUT" --top 10

python3 self-reflect/scripts/render-report.py "$OUT"
```

## Output bundle

`<output-dir>/` contains:

```
inventory.json           # what was read (provenance)
events.jsonl             # normalized event stream (one JSON per line)
findings.json            # structured findings (primary + appendix)
summary.json             # counts, severity buckets, detector health
reflection.md            # human-readable report with Self-Review
patches/                 # one markdown file per suggested edit
  orchestrator_AGENTS.md.md
  dashboard_src_state.ts.md
  ...
```

## Adding a new detector

1. Create `detectors/<name>.md` with: pattern, threshold, output schema, what to skip.
2. Add `<name>:` block to `config.yaml` with the threshold values.
3. Implement `detect_<name>(events, cfg)` in `scripts/cluster-findings.py`.
4. Add `(<name>, detect_<name>)` to the `DETECTORS` list.
5. Add diagnosis + recommended_action + patch_target entries.
6. Add the label in `scripts/render-report.py::patch_target_for_label()`.
7. Update the detector table in `SKILL.md`.
8. Run the validate harness (see `validate.py` in your output dir) and iterate.

See `CONTRIBUTING.md` for the full authoring guide.

## Iterate via Self-Review

The skill reports its own misses in `reflection.md` → `## Self-Review` →
`### Missed patterns`. The iteration loop:

1. Run the skill.
2. Read `Self-Review`. Each missed pattern row suggests a detector name.
3. Either tune the threshold in `config.yaml`, loosen a regex in the detector
   spec, or add a new detector.
4. Re-run. Compare `summary.json` against the previous run.
5. Stop when `missed_patterns` is empty or contains only out-of-scope events.

## Why a skill, not a library?

Mission structure (`features.json` + `progress_log.jsonl` + `handoffs/`) varies
across projects but the *failure shapes* (`restarting pipeline (attempt N)`,
`consecutive failures: N`, `ECONNREFUSED`, `tee ... All tee outputs failed`)
are universal. The skill encodes the failure-shape knowledge as markdown
contracts that any LLM can read; the scripts are stdlib-only glue. Adding a new
detector is a markdown edit + a small Python function, not a library release.

## Cross-project portability

The skill reads only:

- Mission artifacts: `features.json`, `progress_log.jsonl`, `handoffs/`,
  `evidence/`, `library/`, `AGENTS.md`.
- Runtime logs: any `*.log` and `*.jsonl` file in `--run-dir`.

No project-specific code, no env vars, no API keys, no network calls. Drop it
into any mission directory and it works.

## License

MIT — see `LICENSE`.

## See also

- `SKILL.md` — the entry-point contract the orchestrator reads.
- `CONTRIBUTING.md` — how to author detectors and contribute.
- `CHANGELOG.md` — release history and detector coverage.
- `CONTEXT.md` — single-file concatenation of every file in this bundle
  (~2800 lines), ready to paste into a Claude conversation as context.
- `detectors/` — one markdown contract per detection pattern.
- `scripts/` — stdlib-only helpers (Python 3.10+, bash 4+).

```

## File: `CHANGELOG.md`

```
# Changelog

All notable changes to self-reflect are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-20

Initial open-source release.

### Added — 11 detectors

- **`repeated_message`** — same `(scope, msg-template)` N+ times in window.
  Catches sustained warnings/errors that aren't in a more specific detector.
- **`escalating_health`** — `consecutive failures: N` counter rising within
  window. Surfaces watchdog trajectory before hard restart threshold trips.
- **`restart_loop`** — pipeline restart followed by another restart within
  window. Indicates the underlying fault has not been resolved.
- **`service_unreachable`** — connection refused, ECONNREFUSED, ECONNRESET,
  socket hang up, etc.
- **`http_error_storm`** — same HTTP status code N+ times in window.
- **`muxer_failure`** — ffmpeg tee/flv/aost broken-pipe and header failures.
- **`long_idle`** — `loaded=false` / `warming` held for >X seconds without
  transitioning to ready.
- **`json_parse_failure`** — LLM returned unparseable JSON (parseJson
  fallback exhausted).
- **`chaos_verdict`** — explicit `Verdict:` line from chaos-drill summaries.
- **`browser_console_errors`** — repeated dashboard console errors (e.g.
  `/api/dashboard 500` storm with last-good-state fallback).
- **`segment_gap`** — segment starts producing but no subsequent segment
  starts within X minutes. Catches the silent producer-stall failure.

### Added — infrastructure

- 10-phase process in `SKILL.md`: Discover → Normalize → Detect → Diagnose →
  Rank → Generate corrective actions → Cross-project patches → Output bundle
  → Self-review → Iterate.
- `parse-progress-log.sh` normalizes JSONL + text probe logs + chaos
  summaries into a single event stream.
- `cluster-findings.py` runs all detectors, scores findings by impact
  (`occurrences * 1.0 + recency * 0.5 + features_affected * 2.0 -
  likely_known * 5.0`), generates diagnoses and patches.
- `render-report.py` produces `reflection.md` with executive summary,
  detector health table, top findings (with evidence excerpts), appendix,
  and Self-Review section listing missed patterns.
- `config.yaml` — single file for tunable thresholds.
- `CONTEXT.md` — single-file concatenation of every file in the bundle,
  ready to paste into a Claude conversation as context.

### Added — features cross-reference

- `cluster-findings.py` loads `features.json` from the mission directory and
  builds a token index (feature slugs + worker session UUIDs + milestone
  prefixes). Each finding's `evidence_event_ids` source paths are checked
  against the index; the count of distinct features affected is folded into
  the impact score.

### Added — Self-Review

- `reflection.md` → `## Self-Review` → `### Missed patterns` lists warn/error
  events from `events.jsonl` that didn't trigger any detector, with a
  suggested detector name per event. This makes iteration measurable.
- A "Detector Health" table flags over-triggering (>50 firings) and
  under-triggering (0 firings) detectors.

### Validated

Against CUI BONO's runtime logs (`mission:fec95956-c7a8-4c94-9aab-d1ebda54d857` +
`.run/`):

| # | Real failure pattern | Detector | v1 caught |
| --- | --- | --- | --- |
| 1 | TTS service unreachable on `:8800` | `service_unreachable` | yes |
| 2 | TTS `loaded=false` for 180s | `long_idle` | yes |
| 3 | ffmpeg tee/flv muxer failures | `muxer_failure` | yes |
| 4 | Pipeline restart loop | `restart_loop` | yes |
| 5 | Dashboard `/api/dashboard` 500 storm | `http_error_storm` + `browser_console_errors` | yes |
| 6 | Health probe timeout (350ms) | `repeated_message` | yes |
| 7 | Chaos drill verdict (cached SQLite) | `chaos_verdict` | yes |
| 8 | TTS unhealthy escalating (1→3) | `escalating_health` | yes |

**Result: 8/8 known real failure patterns detected.**

### Known limitations

- `segment_gap` requires the orchestrator's producer loop to emit
  `producing ... from:` log lines. Systems that don't log segment starts at
  this verbosity will need a custom detector or a more lenient
  `starting_markers` list.
- `distinct_features_affected` only matches against `features.json` tokens
  (slugs + worker session UUIDs + milestone prefixes). Custom ID schemes
  need a small extension to `build_feature_index()`.
- The skill assumes UTC ISO-8601 timestamps. Logs with non-UTC or non-ISO
  timestamps need a custom `parse_ts()` adapter.
- Single-occurrence events below the `repeated_message` threshold
  (`count=3` default) will appear in `Self-Review → Missed patterns` but
  won't fire. This is intentional — bump the threshold or add a new
  detector if you need to catch one-offs.

### Iteration history (from initial development)

- **v0.1** — initial detector set (6 detectors), config-driven thresholds,
  stdlib-only helpers.
- **v0.2** — added `escalating_health`, `restart_loop`, `muxer_failure`,
  `json_parse_failure`, `chaos_verdict`, `browser_console_errors`.
- **v0.3** — fixed YAML parser (nested lists, comment stripping), fixed
  `restart_loop` KeyError, lowered `escalating_health` threshold, added
  `ECONNRESET` + `socket hang up` to `service_unreachable`.
- **v0.4** — added `segment_gap` detector; implemented
  `distinct_features_affected` from `features.json`; hoisted
  `poll_start_ts` in `parse-progress-log.sh`; stripped ANSI/NUL bytes from
  rendered report.

[1.0.0]: https://github.com/your-org/self-reflect/releases/tag/v1.0.0

```

## File: `CONTRIBUTING.md`

```
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

```

## File: `SKILL.md`

```
---
name: self-reflect
description: >
  Mission self-reflection and self-correction. Reads execution logs from a mission's
  progress_log.jsonl, handoffs, evidence, and external runtime logs; detects recurring
  failure patterns; diagnoses root causes; and produces a PR-ready bundle of report +
  JSON findings + suggested patches to AGENTS.md or sub-skill Known Failure Modes.
  Use when running against a mission that has accumulated logs and you want to find
  what is actually breaking before adding more features.
---

# Self-Reflect: Mission Self-Correction

**SCOPE: This skill is read-only. It analyzes mission artifacts and runtime logs. It does
NOT mutate source files, missions, logs, or running services. It writes outputs to a
directory the user specifies (or `<cwd>/qa-results/self-reflection/` by default).**

## Inputs

The skill accepts the following flags. All have sensible defaults so a bare invocation
against a mission directory works.

| Flag | Purpose | Default |
| --- | --- | --- |
| `--mission-dir <path>` | Mission directory containing `features.json`, `progress_log.jsonl`, `handoffs/`, `evidence/`, `AGENTS.md`, `library/` | auto-discovered by walking up from cwd looking for `features.json` |
| `--run-dir <path>` | External runtime logs directory (e.g., `<repo>/.run/`) | `.run/` relative to cwd, if present |
| `--feature <id>` | Scope analysis to one feature (its handoffs + its evidence slice) | analyze all features |
| `--since <iso>` | Only analyze events newer than this timestamp | analyze all events |
| `--output-dir <path>` | Where the bundle lands | `<cwd>/qa-results/self-reflection/` |
| `--top <N>` | How many ranked findings to feature in the primary report | 10 |

## The 10-phase process

### Phase 1: Discover

Enumerate every artifact the skill will read. Write an inventory to
`<output-dir>/inventory.json`:

- From `--mission-dir` if given:
  - `mission.md`, `architecture.md`, `validation-contract.md`, `AGENTS.md`
  - `features.json` (the feature catalog)
  - `progress_log.jsonl` (worker events, JSONL)
  - `handoffs/*.json` (one per completed feature)
  - `evidence/**/*` (test outputs, screenshots, JSON snapshots)
  - `library/**/*.md` (shared knowledge)
  - `skills/**/*.md` (sub-skill SKILL.md files)
- From `--run-dir` if given:
  - All `*.log` and `*.jsonl` files
  - Chaos summary files (any file containing the literal `Verdict:`)
  - Browser console logs (filename matches `*console*`)
  - Note presence of binary artifacts (screenshots, HTML reports, wav files) but skip reading

### Phase 2: Normalize

Build a single normalized event stream at `<output-dir>/events.jsonl`. Each line is:

```json
{"ts": "2026-06-19T13:32:25.645Z", "level": "info|warn|error|debug", "scope": "feeds|main|ofac|streamer|...", "msg": "...", "source": "<relative path of source file>", "raw": "..."}
```

Parsing rules:
- **JSONL files** (`progress_log.jsonl`, pino runtime logs, agent-browser console JSON): parse each non-empty line as JSON. Extract `ts`/`time`, `level`, `scope`, `msg`/`message`. Anything else goes in `raw`.
- **Text probe logs** (`val-obs-*-poll.log`, `*-probe.log`): emit one event per line. Set `level` heuristically (lines starting with `[ERROR]` or `error` → `error`; `=== ` markers → `info`; lines with `Failed` → `warn`; default `info`). Set `scope` from the leading `=` `===` section header if present.
- **Chaos summaries** (text files containing `Verdict:`): extract the paragraph after `Verdict:` and emit one event with `level=info`, `msg="chaos verdict: <text>"`.
- **HTML/screenshots/binaries**: skip; record their paths in `inventory.json` under `skipped_artifacts`.

### Phase 3: Detect (menu, not a checklist)

Each detector in `detectors/` is a markdown specification with: pattern, regex/logic,
threshold, output schema, and a "what to skip" note. The orchestrator runs the detectors
that match the corpus (e.g., skip `chaos_verdict` if no chaos summaries were found).

See `detectors/` for full specs. Summary:

| Detector | Triggers on | Default threshold |
| --- | --- | --- |
| `repeated_message` | Same `(scope, normalized-msg)` N+ times in W | N=3, W=10min |
| `escalating_health` | `consecutive failures` counter incrementing | delta >= 2 within 5min |
| `restart_loop` | `restarting pipeline (attempt N)` then another restart within W | W=60s |
| `service_unreachable` | `connection refused`, `Failed to connect`, `ECONNREFUSED` | any occurrence |
| `http_error_storm` | Same HTTP status code N+ times in W | N=3, W=60s |
| `muxer_failure` | `tee`, `Broken pipe`, `Failed to update header` | any |
| `long_idle` | `loaded=false` repeated >X seconds with no `loaded=true` | X=120s |
| `json_parse_failure` | `parseJson`, `did not return parseable JSON`, `completeJSON.*throw` | any |
| `chaos_verdict` | Explicit `Verdict:` line in chaos summary | any |
| `browser_console_errors` | Repeated console error in dashboard log | N=3 |
| `segment_gap` | Segment starts producing but no next start within X | X=15min |

### Phase 4: Diagnose

For each finding, pull 5 events of surrounding context (offset in `events.jsonl`). Look up:
- `scope` in `library/` (mission knowledge base)
- `scope` in sub-skill `## Known failure modes` sections
- `AGENTS.md` "Common pitfalls" / "Common pitfalls (for agents)" sections

Assign one root cause class from this enum:
- `upstream_dependency` — third-party service / API changed or is down
- `env_config` — `.env` / config value missing or wrong
- `code_bug` — orchestrator/dashboard/tts code defect
- `race_condition` — timing/state-machine issue
- `capacity` — disk, memory, port, GPU exhaustion
- `architecture` — design-level limitation (e.g., cached SQLite handle)
- `expected_warmup` — known startup behavior, not a bug

### Phase 5: Rank

```
impact = (occurrences * 1.0)
       + (recency_hours_inverse * 0.5)
       + (distinct_features_affected * 2.0)
       - (likely_known ? 5.0 : 0.0)
```

`distinct_features_affected` is computed by cross-referencing each finding's
`evidence_event_ids` source paths against a token index built from
`<missionDir>/features.json`. The index maps feature slugs (e.g.,
`m1-mypy-strict-tts`) and worker session UUIDs to feature IDs; any source
path containing a token counts as affecting that feature. When no
`features.json` is available, the term collapses to 0.

Top `--top` (default 10) findings become the report's primary sections. Remaining
findings appear in an appendix.

### Phase 6: Generate corrective actions

For each ranked finding produce:
- **diagnosis** (1-2 sentences)
- **evidence** (file:line references + log excerpts, max 5 lines each)
- **recommended_action** (concrete: which file to edit, what check to add, what test to add)
- **patch_target** (which file should receive a patch — one of `AGENTS.md`, `<sub-skill>/SKILL.md`, `library/<topic>.md`, or `null` for code fixes)

### Phase 7: Cross-project patches

For each finding with a non-null `patch_target`, write
`<output-dir>/patches/<sanitized-target>.md`:

```markdown
## Suggested patch for `<target>` — section `<section>`

Append after the last item in the section:

<exact markdown to paste>
```

The user pastes these manually. The skill never auto-edits source files.

### Phase 8: Output bundle

- `<output-dir>/reflection.md` — human-readable report
- `<output-dir>/findings.json` — structured findings (one JSON object per finding)
- `<output-dir>/inventory.json` — what was read
- `<output-dir>/events.jsonl` — normalized event stream
- `<output-dir>/patches/*.md` — one per suggested edit
- `<output-dir>/summary.json` — top-level counts and severity buckets

### Phase 9: Self-review

The skill re-reads its own `findings.json` and checks:

1. **False-positive audit**: any detector that fired but the diagnosis is `expected_warmup` or the AGENTS.md cross-reference already documents the pattern → mark `likely_known: true`.
2. **Gap audit**: read a random 10% sample of `events.jsonl` events with `level in {warn, error}`. Did each one match at least one detector? If not, list as `missed_patterns` with the event id, the detector name it should have matched, and the reason it didn't (regex too narrow, threshold too high, scope not in pattern, etc.).
3. **Threshold sanity**: any detector that fired on EVERY event (over-triggered) or fired on NONE (under-triggered)? Flag in the report's "Detector Health" section.

### Phase 10: Iterate

To improve detection:
1. Read `<output-dir>/reflection.md` → "Self-Review" section.
2. For each `missed_pattern`, either:
   - Tune the threshold in `config.yaml`, OR
   - Add a new regex/logic to the corresponding detector file, OR
   - Add a new detector file and reference it in this SKILL.md.
3. Re-run; compare `summary.json` against previous.
4. Stop when `missed_patterns` is empty or contains only events outside scope.

## Usage

```bash
# Default invocation (auto-discovers mission dir + .run/)
droid exec --auto high --prompt "Run the self-reflect skill"

# Explicit paths
droid exec --auto high --prompt "Run the self-reflect skill --mission-dir /home/server/.factory/missions/fec95956-c7a8-4c94-9aab-d1ebda54d857 --run-dir /home/server/cui bono/.run --output-dir /home/server/cui bono/qa-results/self-reflection"

# Focused on one feature
droid exec --auto high --prompt "Run the self-reflect skill --feature 7c5b... --since 2026-06-19T00:00:00Z"
```

## Notes on this skill

- **Read-only by design.** The skill writes only to `--output-dir`. It does not touch
  mission artifacts, source code, or runtime logs.
- **Detector specs are the API.** To add or refine a detection, edit the corresponding
  `detectors/<name>.md` file. The threshold values live in `config.yaml`.
- **Iteration is the value.** A single run will catch the loudest patterns. Each
  iteration, guided by the `Self-Review` section, catches quieter ones.
- **Cross-project portability.** The skill reads only mission structure
  (`features.json` + `progress_log.jsonl` + `handoffs/`) and log files. It works on any
  mission in any project.

## Related

- `README.md` — invocation matrix, worked example
- `config.yaml` — tunable thresholds
- `REPORT-TEMPLATE.md` — the `reflection.md` skeleton
- `detectors/` — one file per detection pattern
- `scripts/` — helper scripts (stdlib-only)

```

## File: `config.yaml`

```
# self-reflect detector thresholds
#
# Tune these to make detectors more or less sensitive.
# The Self-Review section of reflection.md will tell you which way to go.

# repeated_message: same (scope, normalized-message) N+ times in W seconds
repeated_message:
  count: 3
  window_seconds: 600        # 10 minutes

# escalating_health: counter delta >= D within W seconds
# delta=2 means "counter rose by at least 2 increments" — catches the
# 1→3 pattern visible in real orchestrator logs (TTS unhealthy: 1, 2, 3)
escalating_health:
  delta: 2
  window_seconds: 300        # 5 minutes

# restart_loop: a restart followed by another restart within W seconds
restart_loop:
  followup_window_seconds: 60

# service_unreachable: any occurrence of these patterns
service_unreachable:
  patterns:
    - "Failed to connect to"
    - "ECONNREFUSED"
    - "ECONNRESET"
    - "connection refused"
    - "Connection reset"
    - "no route to host"
    - "socket hang up"

# http_error_storm: same HTTP status code N+ times in W seconds
http_error_storm:
  count: 3
  window_seconds: 60

# muxer_failure: any of these ffmpeg-tee pipeline errors
muxer_failure:
  patterns:
    - "Broken pipe"
    - "Failed to update header"
    - "All tee outputs failed"
    - "Error muxing a packet"
    - "Slave muxer"

# long_idle: a "loaded=false"-style state held for >X seconds with no transition
long_idle:
  idle_seconds: 120
  idle_markers:
    - "loaded=false"
    - "ready=false"
    - "warming"

# json_parse_failure: any occurrence
json_parse_failure:
  patterns:
    - "did not return parseable JSON"
    - "LLM did not return parseable JSON"
    - "completeJSON"
    - "parseJson"
    - "JSON.parse"
    - "Unexpected token"

# chaos_verdict: explicit Verdict: lines
chaos_verdict:
  verdict_markers:
    - "Verdict:"
    - "verdict:"

# browser_console_errors: N+ console errors in W seconds
browser_console_errors:
  count: 3
  window_seconds: 120

# segment_gap: a segment starts producing but no subsequent segment
# starts within X minutes. Default 15 minutes; tune down for fast-cycle
# schedulers or up for sparse schedules.
segment_gap:
  gap_minutes: 15
  starting_markers:
    - "producing "
    - "rendering segment"
    - "seg="
    - "tts-render] seg="

# Ranking weights
ranking:
  weight_occurrences: 1.0
  weight_recency_inverse: 0.5
  weight_features_affected: 2.0
  penalty_likely_known: 5.0

# Output
output:
  top_findings: 10
  max_evidence_excerpt_lines: 5
  include_appendix: true

```

## File: `REPORT-TEMPLATE.md`

```
# Self-Reflection Report

**Mission:** `{{MISSION_DIR}}`
**Run dir:** `{{RUN_DIR}}`
**Analyzed at:** {{ANALYZED_AT}}
**Events analyzed:** {{EVENT_COUNT}}
**Findings (primary):** {{FINDING_COUNT}}
**Severity buckets:** {{SEVERITY_BUCKETS}}

## Executive Summary

{{EXECUTIVE_SUMMARY}}

## Detector Health

| Detector | Fired | Over-triggered? | Under-triggered? |
| --- | --- | --- | --- |
{{DETECTOR_HEALTH_ROWS}}

## Top Findings

<!-- Rendered dynamically by scripts/render-report.py. The placeholder
     section below is intentionally inert; it gets stripped during rendering. -->

{{#if MORE_FINDINGS}}
## Appendix: Additional Findings

{{APPENDIX_FINDINGS}}
{{/if}}

## Self-Review

### Missed patterns

The following events had `level in {warn, error}` but did NOT trigger any detector.
Address these in the next iteration:

{{MISSED_PATTERNS_TABLE}}

### Threshold tuning suggestions

{{THRESHOLD_TUNING_SUGGESTIONS}}

## Suggested Patches

The following files contain suggested edits. Apply manually after review.

{{PATCH_FILE_LIST}}

---

Generated by the `self-reflect` skill. Re-run after applying patches or tuning
`config.yaml` to verify the changes have closed the gaps.

```

## File: `detectors/browser_console_errors.md`

```
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

```

## File: `detectors/chaos_verdict.md`

```
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

```

## File: `detectors/escalating_health.md`

```
# escalating_health

## What it catches

A "consecutive failures" or similar counter **incrementing** across events. This is a
distinct failure shape from `repeated_message`: instead of the same warning repeating,
the same counter grows, which usually means the system is trying to recover and failing
to recover.

## Why this detector exists

The CUI BONO orchestrator uses a watchdog pattern: `consecutive failures: 1`, `: 2`,
`: 3`... until the threshold triggers a hard restart. By the time the counter reaches
the threshold, the system has been degraded for minutes. The detector surfaces the
escalation so the failure mode is visible *before* the threshold trip.

## Pattern

```
events where msg matches /consecutive (?:failures?|errors?): (\d+)/
group by scope (or breaker name when present)
sort by ts
if max(counter) - min(counter) >= delta within W seconds:
  fire
```

## Threshold

- `delta`: 3 (from `config.yaml`)
- `window_seconds`: 300 (5 minutes)

## Output schema

```json
{
  "detector": "escalating_health",
  "scope": "<string>",
  "counter_min": <int>,
  "counter_max": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- Counters that reset back to 1 inside the window (normal recovery). Only fire if the
  trend is monotonically non-decreasing (allow plateaus but no resets).
- A single counter reading without a precursor (no `: 1` event in the window). The
  detector needs at least 2 readings to compute a delta.

## Worked example

```
{"scope":"stream","msg":"[encoder] heartbeat target process unavailable (consecutive failures: 1)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 1)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 2)"}
{"scope":"main","msg":"TTS unhealthy (consecutive failures: 3)"}
```
→ fires (TTS): counter 1→3, delta=2... if delta>=3 fires; otherwise note as "watching".

```

## File: `detectors/http_error_storm.md`

```
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

```

## File: `detectors/json_parse_failure.md`

```
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

```

## File: `detectors/long_idle.md`

```
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

```

## File: `detectors/muxer_failure.md`

```
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

```

## File: `detectors/repeated_message.md`

```
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

```

## File: `detectors/restart_loop.md`

```
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

```

## File: `detectors/segment_gap.md`

```
# segment_gap

## What it catches

A segment starts producing (or rendering) but **no subsequent segment starts within
X minutes**. This is the silent failure: the pipeline is alive, the watchdog is happy,
no error is logged — but the producer has stopped generating new segments. The on-air
stream goes silent.

## Why this detector exists

Most failure detectors surface loud signals (errors, exceptions, restarts). The most
insidious failure mode in a 24/7 stream is the *quiet* one: the producer loop exits
cleanly, the watchdog sees a healthy stream mixer, but no new editorial packages flow.
Operators notice when viewers complain about silence. This detector surfaces the
silence *before* viewers do.

## Pattern

```
events where msg matches any of:
  - /producing (\w+) from:/
  - /rendering segment/
  - /seg=(\d+)/
  - /\[tts-render\] seg=/
sort by ts
for each pair (prev, next) where next.ts - prev.ts > gap_seconds:
  fire a gap finding with:
    - last_segment_marker: the title/type from prev.msg
    - gap_seconds: next.ts - prev.ts
    - expected_within_seconds: gap_seconds (the configured threshold)
```

## Threshold

- `gap_minutes`: 15 (default). Tune up for sparse schedules (news streams might wait
  30 minutes between segments), down for fast-cycle schedulers (every 60 seconds).

## Output schema

```json
{
  "detector": "segment_gap",
  "last_segment_marker": "<string>",
  "gap_seconds": <int>,
  "expected_within_seconds": <int>,
  "occurrences": <int>,
  "first_seen": "<iso>",
  "last_seen": "<iso>",
  "evidence_event_ids": ["<id>", ...]
}
```

## What to skip

- The very last segment before the log ends. A gap that runs off the end of the log
  is not actionable from logs alone (the next segment may have started in a log
  file we don't have). Only fire gaps between two observed segment starts.
- Gaps shorter than `gap_minutes` (by definition — these are normal inter-segment
  spacing).
- Segments produced by the same logical source within a few seconds (e.g., a
  `producing primary_source_review` followed 5s later by `producing briefing`).
  Treat consecutive different segment types as one logical "production cycle" if
  they are within a small window (e.g., 60s).

## Worked example

```
{"ts":"2026-06-19T13:32:25.955Z","scope":"scheduler-produce","msg":"producing primary_source_review from: <title A>"}
{"ts":"2026-06-19T13:32:59.883Z","scope":"scheduler-produce","msg":"producing briefing from: <title B>"}
{"ts":"2026-06-19T13:33:29.913Z","scope":"scheduler-produce","msg":"producing primary_source_review from: <title C>"}
# (no more producing events for 15+ minutes)
```
→ fires: gap_seconds=900+, last_segment_marker=`primary_source_review from: <title C>`.

## Cross-reference with other detectors

- If a `restart_loop` fires in the same window as the gap, the gap is a *consequence*
  of the restart (not an independent finding). Mark `likely_known: true`.
- If `service_unreachable` (TTS or LLM) fires in the same window, the gap is a
  *consequence* of the upstream outage. Mark `likely_known: true` and reference the
  upstream finding in the diagnosis.
- If `muxer_failure` fires in the same window, the gap is likely a stream-pipeline
  consequence. Mark `likely_known: true`.

```

## File: `detectors/service_unreachable.md`

```
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

```

## File: `scripts/list-mission-artifacts.sh`

```
#!/usr/bin/env bash
# list-mission-artifacts.sh
# Phase 1: enumerate mission artifacts and runtime logs.
# Usage: list-mission-artifacts.sh <mission-dir> <run-dir> <output-dir>
# Writes <output-dir>/inventory.json (and exits 0 even if some sources are missing).

set -euo pipefail

MISSION_DIR="${1:-}"
RUN_DIR="${2:-}"
OUTPUT_DIR="${3:-}"

if [[ -z "${OUTPUT_DIR}" ]]; then
  echo "usage: $0 <mission-dir> <run-dir> <output-dir>" >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}"

# Use python for JSON assembly (already used everywhere in the project, no jq dep).
python3 - "${MISSION_DIR}" "${RUN_DIR}" "${OUTPUT_DIR}" <<'PY'
import json, os, sys, pathlib

mission_dir = sys.argv[1] or ""
run_dir = sys.argv[2] or ""
output_dir = sys.argv[3]

inventory = {
  "analyzed_at": "2026-06-19T17:23:00Z",  # overwritten below
  "mission_dir": mission_dir or None,
  "run_dir": run_dir or None,
  "mission_artifacts": {"present": [], "missing": []},
  "run_artifacts": {"present": [], "missing": []},
  "skipped_artifacts": [],
}

import datetime
inventory["analyzed_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

# Mission artifacts
mission_files = [
  "mission.md", "architecture.md", "validation-contract.md", "AGENTS.md",
  "features.json", "progress_log.jsonl", "model-settings.json",
]
if mission_dir and os.path.isdir(mission_dir):
  for f in mission_files:
    p = os.path.join(mission_dir, f)
    if os.path.exists(p):
      inventory["mission_artifacts"]["present"].append(p)
    else:
      inventory["mission_artifacts"]["missing"].append(p)
  # handoffs
  handoffs_dir = os.path.join(mission_dir, "handoffs")
  if os.path.isdir(handoffs_dir):
    for fn in sorted(os.listdir(handoffs_dir)):
      inventory["mission_artifacts"]["present"].append(os.path.join(handoffs_dir, fn))
  # evidence (just count; not enumerated for size)
  ev = os.path.join(mission_dir, "evidence")
  if os.path.isdir(ev):
    cnt = sum(len(files) for _, _, files in os.walk(ev))
    inventory["mission_artifacts"]["present"].append(f"{ev}/ ({cnt} files)")
  # library
  lib = os.path.join(mission_dir, "library")
  if os.path.isdir(lib):
    for fn in sorted(os.listdir(lib)):
      inventory["mission_artifacts"]["present"].append(os.path.join(lib, fn))
  # skills (sub-skill SKILL.md files)
  sk = os.path.join(mission_dir, "skills")
  if os.path.isdir(sk):
    for root, _, files in os.walk(sk):
      for fn in files:
        if fn.endswith(".md"):
          inventory["mission_artifacts"]["present"].append(os.path.join(root, fn))
else:
  for f in mission_files:
    inventory["mission_artifacts"]["missing"].append(os.path.join(mission_dir, f) if mission_dir else f)

# Run artifacts
if run_dir and os.path.isdir(run_dir):
  for root, _, files in os.walk(run_dir):
    for fn in files:
      p = os.path.join(root, fn)
      # binary files: record presence, skip reading
      binary_ext = (".png", ".jpg", ".jpeg", ".gif", ".wav", ".mp3", ".mp4",
                    ".html", ".htm", ".pdf", ".zip", ".tar", ".gz", ".bin")
      if any(fn.lower().endswith(ext) for ext in binary_ext):
        inventory["skipped_artifacts"].append({"path": p, "reason": "binary"})
        continue
      inventory["run_artifacts"]["present"].append(p)
else:
  inventory["run_artifacts"]["missing"].append(run_dir or "(no run-dir)")

with open(os.path.join(output_dir, "inventory.json"), "w") as f:
  json.dump(inventory, f, indent=2)

print(f"inventory.json written: "
      f"mission={len(inventory['mission_artifacts']['present'])} present, "
      f"run={len(inventory['run_artifacts']['present'])} present, "
      f"skipped={len(inventory['skipped_artifacts'])}")
PY

```

## File: `scripts/parse-progress-log.sh`

```
#!/usr/bin/env bash
# parse-progress-log.sh
# Phase 2: normalize mission artifacts + runtime logs into events.jsonl.
# Usage: parse-progress-log.sh <inventory.json> <output-dir>

set -euo pipefail

INV="${1:-}"
OUTPUT_DIR="${2:-}"

if [[ -z "${INV}" || -z "${OUTPUT_DIR}" ]]; then
  echo "usage: $0 <inventory.json> <output-dir>" >&2
  exit 2
fi

python3 - "${INV}" "${OUTPUT_DIR}" <<'PY'
import json, os, re, sys, datetime

inventory_path = sys.argv[1]
output_dir = sys.argv[2]

with open(inventory_path) as f:
  inv = json.load(f)

events = []
event_id = 0

def next_id():
  global event_id
  event_id += 1
  return f"e{event_id:06d}"

VERDICT_RE = re.compile(r"^\s*Verdict\s*:\s*(.+)", re.IGNORECASE)
RESULTS_RE = re.compile(r"^\s*Results\s*:", re.IGNORECASE)
STRATEGY_RE = re.compile(r"^\s*Strategy attempted\s*:\s*(.+)", re.IGNORECASE)
SECTION_RE = re.compile(r"^===\s*([^=]+?)\s*===")
HTTP_STATUS_RE = re.compile(r"\b([45]\d{2})\b")
POLL_RE = re.compile(r"^poll=(\d+)\s+t=(\d+)s\s+http_rc=(\d+)\s+loaded=(\S+)\s+resp=(.+)$")

def normalize_msg(msg):
  """Replace volatile tokens in a message to enable grouping."""
  if not isinstance(msg, str):
    msg = str(msg)
  msg = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", msg)
  msg = re.sub(r"\b\d+\.\d+\.\d+\.\d+:\d+\b", "<HOST:PORT>", msg)
  msg = re.sub(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b", "<TS>", msg)
  msg = re.sub(r"\b\d+\b", "<NUM>", msg)
  return msg

def heuristic_level(line):
  low = line.lower()
  if low.startswith("[error]") or '"level":"error"' in low or '"level": "error"' in low:
    return "error"
  if low.startswith("[warn]") or '"level":"warn"' in low or '"level": "warn"' in low:
    return "warn"
  if "failed" in low or "error" in low or "broken pipe" in low:
    return "warn"
  if low.startswith("===") or low.startswith("poll=") or low.startswith("results"):
    return "info"
  return "info"

def heuristic_scope(line):
  m = SECTION_RE.match(line)
  if m:
    return m.group(1).strip()[:40]
  return ""

def parse_jsonl_line(line, source):
  """Parse a JSONL line from a pino-style orchestrator log."""
  try:
    obj = json.loads(line)
  except json.JSONDecodeError:
    return None
  return {
    "id": next_id(),
    "ts": obj.get("ts") or obj.get("time") or "",
    "level": (obj.get("level") or "info").lower(),
    "scope": (obj.get("scope") or ""),
    "msg": (obj.get("msg") or obj.get("message") or ""),
    "source": source,
    "raw": line[:500],
    "msg_template": normalize_msg(obj.get("msg") or obj.get("message") or ""),
  }

def parse_text_line(line, source, default_ts=""):
  """Parse a non-JSONL line."""
  level = heuristic_level(line)
  scope = heuristic_scope(line)
  return {
    "id": next_id(),
    "ts": default_ts,
    "level": level,
    "scope": scope,
    "msg": line.strip(),
    "source": source,
    "raw": line[:500],
    "msg_template": normalize_msg(line.strip()),
  }

def parse_poll_line(line, source, start_ts=""):
  m = POLL_RE.match(line.strip())
  if not m:
    return None
  poll_n, t_s, rc, loaded, resp = m.groups()
  level = "error" if rc == "7" or (rc == "0" and "false" in loaded) else "info"
  # Synthesize ts from start_ts + t_s offset when available
  ts = ""
  if start_ts:
    try:
      base = datetime.datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
      ts = (base + datetime.timedelta(seconds=int(t_s))).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
      ts = ""
  return {
    "id": next_id(),
    "ts": ts,
    "level": level,
    "scope": "tts.health.poll",
    "msg": f"poll={poll_n} t={t_s}s http_rc={rc} loaded={loaded}",
    "source": source,
    "raw": line[:500],
    "msg_template": "poll=<NUM> t=<NUM>s http_rc=<NUM> loaded=<STR>",
    "extra": {"http_rc": int(rc), "loaded": loaded, "resp": resp[:200]},
  }

# Process all mission artifacts and run artifacts
sources = []
sources.extend(inv.get("mission_artifacts", {}).get("present", []))
sources.extend(inv.get("run_artifacts", {}).get("present", []))

# File-type policy:
#   - .md     : documentation; skip (not an event stream)
#   - .json   : snapshot; skip (one event per file is enough)
#   - .jsonl  : event stream; parse every line
#   - .log    : event stream OR probe log; parse every line
#   - other   : parse every line
SKIP_EXT = {".md"}
SNAPSHOT_EXT = {".json"}

for path in sources:
  if not isinstance(path, str) or not os.path.isfile(path):
    continue
  ext = os.path.splitext(path)[1].lower()
  if ext in SKIP_EXT:
    continue
  if ext in SNAPSHOT_EXT:
    # record one summary event for snapshots
    events.append({
      "id": next_id(),
      "ts": "",
      "level": "info",
      "scope": "snapshot",
      "msg": f"snapshot file present: {os.path.basename(path)}",
      "source": path,
      "raw": "",
      "msg_template": "snapshot file present: <STR>",
    })
    continue
  rel = path
  try:
    with open(path, "r", errors="replace") as f:
      lines = f.readlines()
  except Exception:
    continue
  # Hoist per-file state: probe log "polling start:" header sets a
  # start timestamp that subsequent poll= lines should inherit (their
  # own t=<NUM>s is an offset from this header). Without hoisting, the
  # variable resets on every line and only the line directly after the
  # header inherits the timestamp.
  poll_start_ts = ""
  for i, line in enumerate(lines):
    line = line.rstrip("\n")
    if not line.strip():
      continue
    # Try JSON first
    if line.lstrip().startswith("{"):
      ev = parse_jsonl_line(line, rel)
      if ev:
        events.append(ev)
        # Special handling: if this is a chaos verdict, also pull context
        if VERDICT_RE.match(line):
          # Look back for Strategy / Results
          ctx_lines = lines[max(0, i-15):i]
          for cl in ctx_lines:
            m = STRATEGY_RE.match(cl)
            if m:
              events.append({
                "id": next_id(), "ts": "", "level": "info", "scope": "chaos.context",
                "msg": f"strategy: {m.group(1).strip()}", "source": rel, "raw": cl[:500],
                "msg_template": "strategy: <STR>",
              })
            elif RESULTS_RE.match(cl):
              events.append({
                "id": next_id(), "ts": "", "level": "info", "scope": "chaos.context",
                "msg": "results block", "source": rel, "raw": cl[:500],
                "msg_template": "results block",
              })
        continue
    # Probe log poll lines — start_ts is the hoisted per-file value.
    # When this line IS the header, capture and reuse it.
    if "polling start:" in line:
      m = re.search(r"polling start:\s*(\S+)", line)
      if m:
        poll_start_ts = m.group(1)
    ev = parse_poll_line(line, rel, poll_start_ts)
    if ev:
      events.append(ev)
      continue
    # Section marker / chaos summary text
    if SECTION_RE.match(line) or RESULTS_RE.match(line) or STRATEGY_RE.match(line) or VERDICT_RE.match(line):
      m = VERDICT_RE.match(line)
      if m:
        events.append({
          "id": next_id(), "ts": "", "level": "info", "scope": "chaos.verdict",
          "msg": f"verdict: {m.group(1).strip()}", "source": rel, "raw": line[:500],
          "msg_template": "verdict: <STR>",
        })
      else:
        events.append(parse_text_line(line, rel))
      continue
    # Generic text line
    events.append(parse_text_line(line, rel))

# Write events.jsonl
out_path = os.path.join(output_dir, "events.jsonl")
with open(out_path, "w") as f:
  for ev in events:
    f.write(json.dumps(ev) + "\n")

print(f"events.jsonl written: {len(events)} events from {len(sources)} sources")
PY

```

## File: `scripts/cluster-findings.py`

```
#!/usr/bin/env python3
"""cluster-findings.py — stdlib-only Phase 3+5+6: run all detectors on events.jsonl,
score findings, write findings.json and patches/*.md.

Usage: cluster-findings.py <output-dir> [--top N]
Reads: <output-dir>/events.jsonl, <output-dir>/inventory.json
       ~/.factory/skills/self-reflect/config.yaml
Writes: <output-dir>/findings.json
        <output-dir>/summary.json
        <output-dir>/patches/<file>.md
"""
import json
import os
import re
import sys
import datetime
import collections
import pathlib

SKILL_DIR = pathlib.Path.home() / ".factory" / "skills" / "self-reflect"
CONFIG_PATH = SKILL_DIR / "config.yaml"


def load_config():
    """Tiny YAML loader sufficient for our flat-keyed config.yaml.
    Avoids requiring PyYAML on the user's machine. Handles `# comment` after values
    and 2-level nesting with lists (e.g. `foo:\\n  bar:\\n    - baz`).
    """
    def parse_scalar(s):
        s = s.split("#", 1)[0].strip()  # strip trailing comment
        if not s:
            return None
        if s.startswith("[") and s.endswith("]"):
            return [x.strip().strip('"').strip("'") for x in s[1:-1].split(",") if x.strip()]
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    cfg = {}
    cur_section = None
    cur_subsection = None
    with open(CONFIG_PATH) as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip("\n")
            if not line.strip():
                continue
            # Top-level key (no leading whitespace)
            if not line.startswith(" "):
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                if v == "":
                    cfg[k] = {}
                    cur_section = k
                    cur_subsection = None
                else:
                    cfg[k] = parse_scalar(v)
                    cur_section = None
                    cur_subsection = None
                continue
            # 4-space-indented list item (list under subsection)
            if line.startswith("    - ") or line.startswith("    \t- "):
                v = parse_scalar(line.lstrip()[2:].lstrip())
                if cur_section and cur_subsection:
                    section_dict = cfg[cur_section]
                    if cur_subsection not in section_dict or isinstance(section_dict[cur_subsection], dict):
                        section_dict[cur_subsection] = []
                    section_dict[cur_subsection].append(v)
                continue
            # 2-space-indented key (subkey under section)
            if line.startswith("  ") and ":" in line:
                stripped = line.strip()
                if stripped.startswith("- "):
                    continue
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                if cur_section is None:
                    continue
                if v == "":
                    cfg[cur_section][k] = {}
                    cur_subsection = k
                else:
                    cfg[cur_section][k] = parse_scalar(v)
                    cur_subsection = None
                continue
    return cfg


def parse_ts(ts_str):
    """Best-effort ISO-8601 parser."""
    if not ts_str:
        return None
    try:
        return datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None


def dedup_id():
    n = 0
    while True:
        yield f"f{n:04d}"
        n += 1


def detect_repeated_message(events, cfg):
    cfg_rm = cfg["repeated_message"]
    threshold = cfg_rm["count"]
    window = cfg_rm["window_seconds"]
    findings = []
    # group by (scope, msg_template)
    groups = collections.defaultdict(list)
    for ev in events:
        if ev.get("level") not in ("warn", "error"):
            continue
        # Skip high-volume known telemetry
        if ev.get("scope") in ("breaker", "circuit") and "breaker.call" in ev.get("msg_template", ""):
            continue
        key = (ev.get("scope", ""), ev.get("msg_template", ""))
        groups[key].append(ev)
    for (scope, tmpl), evs in groups.items():
        if len(evs) < threshold:
            continue
        # Check window
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if not ts_list:
            # No parsable ts; still fire if count is high enough
            window_ok = True
        else:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            window_ok = span <= window
        if not window_ok:
            continue
        findings.append({
            "detector": "repeated_message",
            "scope": scope,
            "msg_template": tmpl,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_escalating_health(events, cfg):
    cfg_eh = cfg["escalating_health"]
    delta_min = cfg_eh["delta"]
    window = cfg_eh["window_seconds"]
    counter_re = re.compile(r"consecutive (?:failures?|errors?):\s*(\d+)")
    # group by scope (or broader key)
    groups = collections.defaultdict(list)
    for ev in events:
        m = counter_re.search(ev.get("msg", ""))
        if not m:
            continue
        counter = int(m.group(1))
        ts = parse_ts(ev.get("ts", ""))
        if ts is None:
            continue
        scope = ev.get("scope", "")
        groups[scope].append((ts, counter, ev))
    findings = []
    for scope, entries in groups.items():
        entries.sort(key=lambda x: x[0])
        # find the longest monotonically-rising run within window
        # where the counter never resets and increases by >= delta_min
        i = 0
        n = len(entries)
        while i < n:
            ts0, c0, ev0 = entries[i]
            j = i
            max_counter = c0
            while j + 1 < n:
                ts1, c1, _ = entries[j + 1]
                if (ts1 - ts0).total_seconds() > window:
                    break
                if c1 < max_counter:
                    # counter reset; this run is over
                    break
                j += 1
                if c1 > max_counter:
                    max_counter = c1
            if max_counter - c0 >= delta_min and j > i:
                cluster = entries[i:j + 1]
                findings.append({
                    "detector": "escalating_health",
                    "scope": scope,
                    "counter_min": c0,
                    "counter_max": max_counter,
                    "occurrences": len(cluster),
                    "first_seen": cluster[0][2].get("ts", ""),
                    "last_seen": cluster[-1][2].get("ts", ""),
                    "evidence_event_ids": [e[2]["id"] for e in cluster],
                })
                i = j + 1
            else:
                i += 1
    return findings


def detect_restart_loop(events, cfg):
    cfg_rl = cfg["restart_loop"]
    window = cfg_rl["followup_window_seconds"]
    restart_re = re.compile(r"restarting (?:\w+ )?(?:pipeline )?\(attempt (\d+)\)")
    restarts = []
    for ev in events:
        m = restart_re.search(ev.get("msg", ""))
        if not m:
            continue
        ts = parse_ts(ev.get("ts", ""))
        if ts is None:
            continue
        restarts.append((ts, int(m.group(1)), ev))
    restarts.sort(key=lambda x: x[0])
    findings = []
    for i in range(len(restarts)):
        ts0, att0, ev0 = restarts[i]
        cluster_tuples = [(ts0, att0, ev0)]
        last_ts = ts0
        for j in range(i + 1, len(restarts)):
            ts1, att1, ev1 = restarts[j]
            if (ts1 - last_ts).total_seconds() <= window:
                cluster_tuples.append((ts1, att1, ev1))
                last_ts = ts1
            else:
                break
        if len(cluster_tuples) >= 2:
            findings.append({
                "detector": "restart_loop",
                "scope": cluster_tuples[0][2].get("scope", ""),
                "restart_count": len(cluster_tuples),
                "max_attempt": max(c[1] for c in cluster_tuples),
                "first_seen": cluster_tuples[0][2].get("ts", ""),
                "last_seen": cluster_tuples[-1][2].get("ts", ""),
                "evidence_event_ids": [c[2]["id"] for c in cluster_tuples],
            })
    # dedupe overlapping
    deduped = []
    seen_keys = set()
    for f in findings:
        k = (f["scope"], f["first_seen"], f["last_seen"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        deduped.append(f)
    return deduped


def detect_service_unreachable(events, cfg):
    patterns = cfg["service_unreachable"]["patterns"]
    findings = []
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg):
                matched.append(ev)
                break
    if not matched:
        return findings
    # group by target (host:port or service name)
    groups = collections.defaultdict(list)
    for ev in matched:
        m = re.search(r"(?:to |@ )?(\d+\.\d+\.\d+\.\d+:\d+|127\.0\.0\.1 port \d+)", ev.get("msg", ""))
        target = m.group(1) if m else "unknown"
        groups[target].append(ev)
    for target, evs in groups.items():
        findings.append({
            "detector": "service_unreachable",
            "target": target,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_http_error_storm(events, cfg):
    cfg_h = cfg["http_error_storm"]
    threshold = cfg_h["count"]
    window = cfg_h["window_seconds"]
    # extract status code
    code_re = re.compile(r"\b([45]\d{2})\b")
    code_groups = collections.defaultdict(list)
    for ev in events:
        msg = ev.get("msg", "")
        if not any(k in msg.lower() for k in ("http", "status", "api/", "dashboard")):
            continue
        m = code_re.search(msg)
        if not m:
            continue
        code = int(m.group(1))
        ts = parse_ts(ev.get("ts", ""))
        code_groups[code].append((ts, ev))
    findings = []
    for code, entries in code_groups.items():
        ts_entries = [e for e in entries if e[0] is not None]
        if not ts_entries:
            if len(entries) >= threshold:
                findings.append({
                    "detector": "http_error_storm",
                    "status_code": code,
                    "occurrences": len(entries),
                    "first_seen": entries[0][1].get("ts", ""),
                    "last_seen": entries[-1][1].get("ts", ""),
                    "evidence_event_ids": [e[1]["id"] for e in entries],
                })
            continue
        ts_entries.sort(key=lambda x: x[0])
        # sliding window check
        for i in range(len(ts_entries)):
            j = i
            while j + 1 < len(ts_entries) and (ts_entries[j + 1][0] - ts_entries[i][0]).total_seconds() <= window:
                j += 1
            count = j - i + 1
            if count >= threshold:
                cluster = ts_entries[i:j + 1]
                findings.append({
                    "detector": "http_error_storm",
                    "status_code": code,
                    "occurrences": count,
                    "first_seen": cluster[0][1].get("ts", ""),
                    "last_seen": cluster[-1][1].get("ts", ""),
                    "evidence_event_ids": [c[1]["id"] for c in cluster],
                })
                break
    return findings


def detect_muxer_failure(events, cfg):
    patterns = cfg["muxer_failure"]["patterns"]
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg):
                matched.append(ev)
                break
    if not matched:
        return []
    findings = []
    tag_groups = collections.defaultdict(list)
    for ev in matched:
        m = re.search(r"\[(tee|flv|aost|out) @", ev.get("msg", ""))
        tag = m.group(1) if m else "misc"
        tag_groups[tag].append(ev)
    for tag, evs in tag_groups.items():
        findings.append({
            "detector": "muxer_failure",
            "ffmpeg_tag": tag,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_long_idle(events, cfg):
    cfg_li = cfg["long_idle"]
    idle_seconds = cfg_li["idle_seconds"]
    markers = cfg_li["idle_markers"]
    # find events matching any marker
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for m in markers:
            if m in msg:
                matched.append(ev)
                break
    if not matched:
        return []
    # Try to find idle duration: consecutive "still idle" events from same source
    # without an intervening "ready=true" event.
    by_source = collections.defaultdict(list)
    for ev in matched:
        by_source[ev.get("source", "")].append(ev)
    findings = []
    for source, evs in by_source.items():
        # extract timestamps; if any ts present, compute span
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if ts_list:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            if span < idle_seconds:
                continue
            poll_count = len(evs)
            first_seen = evs[0].get("ts", "")
            last_seen = evs[-1].get("ts", "")
        else:
            # No timestamps — use count heuristic for poll logs
            poll_count = len(evs)
            if poll_count < 5:
                continue
            span = poll_count * 5  # assume 5s poll spacing
            first_seen = ""
            last_seen = ""
        findings.append({
            "detector": "long_idle",
            "service": "TTS" if "tts" in source.lower() or "8800" in source else "unknown",
            "idle_seconds": int(span),
            "poll_count": poll_count,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_json_parse_failure(events, cfg):
    patterns = cfg["json_parse_failure"]["patterns"]
    matched = []
    for ev in events:
        msg = ev.get("msg", "")
        for pat in patterns:
            if re.search(pat, msg, re.IGNORECASE):
                matched.append(ev)
                break
    if not matched:
        return []
    by_scope = collections.defaultdict(list)
    for ev in matched:
        by_scope[ev.get("scope", "")].append(ev)
    findings = []
    for scope, evs in by_scope.items():
        findings.append({
            "detector": "json_parse_failure",
            "scope": scope,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


def detect_chaos_verdict(events, cfg):
    findings = []
    for ev in events:
        if ev.get("scope") == "chaos.verdict":
            m = re.match(r"verdict:\s*(.+)", ev.get("msg", ""))
            verdict_text = m.group(1) if m else ev.get("msg", "")
            findings.append({
                "detector": "chaos_verdict",
                "verdict_text": verdict_text,
                "occurrences": 1,
                "first_seen": ev.get("ts", ""),
                "last_seen": ev.get("ts", ""),
                "evidence_event_ids": [ev["id"]],
                "source_file": ev.get("source", ""),
            })
    return findings


def detect_segment_gap(events, cfg):
    """Find gaps between successive segment-start events that exceed the
    configured threshold (default 15 minutes).

    A "segment start" is any event whose msg matches one of the configured
    `starting_markers` (default: `producing ... from:`, `rendering segment`,
    `seg=N`, `[tts-render] seg=N`). We sort all matched events by ts, then
    fire one finding per adjacent pair whose gap exceeds `gap_minutes`.
    """
    cfg_sg = cfg["segment_gap"]
    markers = cfg_sg["starting_markers"]
    gap_seconds = cfg_sg["gap_minutes"] * 60
    # collect and sort
    starts = []
    for ev in events:
        msg = ev.get("msg", "") or ""
        if any(m in msg for m in markers):
            ts = parse_ts(ev.get("ts", ""))
            if ts is None:
                continue
            starts.append((ts, ev))
    starts.sort(key=lambda x: x[0])
    findings = []
    for i in range(len(starts) - 1):
        ts0, ev0 = starts[i]
        ts1, ev1 = starts[i + 1]
        gap = (ts1 - ts0).total_seconds()
        if gap <= gap_seconds:
            continue
        # extract a short marker from the previous event's msg
        marker = ev0.get("msg", "")[:120]
        findings.append({
            "detector": "segment_gap",
            "last_segment_marker": marker,
            "gap_seconds": int(gap),
            "expected_within_seconds": gap_seconds,
            "occurrences": 1,
            "first_seen": ev0.get("ts", ""),
            "last_seen": ev1.get("ts", ""),
            "evidence_event_ids": [ev0["id"], ev1["id"]],
        })
    # dedupe overlapping (defensive — shouldn't happen with sorted starts)
    deduped = []
    seen_keys = set()
    for f in findings:
        k = (f["first_seen"], f["last_seen"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        deduped.append(f)
    return deduped


def detect_browser_console_errors(events, cfg):
    cfg_bc = cfg["browser_console_errors"]
    threshold = cfg_bc["count"]
    window = cfg_bc["window_seconds"]
    # events from sources matching console/browser/agent-browser
    matched = []
    for ev in events:
        src = ev.get("source", "").lower()
        if any(s in src for s in ("console", "browser", "agent-browser")):
            if ev.get("level") in ("warn", "error"):
                matched.append(ev)
    if not matched:
        return []
    by_template = collections.defaultdict(list)
    for ev in matched:
        by_template[ev.get("msg_template", "")].append(ev)
    findings = []
    for tmpl, evs in by_template.items():
        ts_list = [parse_ts(e.get("ts", "")) for e in evs]
        ts_list = [t for t in ts_list if t is not None]
        if ts_list:
            span = (max(ts_list) - min(ts_list)).total_seconds()
            window_ok = span <= window
        else:
            window_ok = True
        if len(evs) < threshold or not window_ok:
            continue
        findings.append({
            "detector": "browser_console_errors",
            "msg_template": tmpl,
            "occurrences": len(evs),
            "first_seen": evs[0].get("ts", ""),
            "last_seen": evs[-1].get("ts", ""),
            "evidence_event_ids": [e["id"] for e in evs],
        })
    return findings


DETECTORS = [
    ("repeated_message", detect_repeated_message),
    ("escalating_health", detect_escalating_health),
    ("restart_loop", detect_restart_loop),
    ("service_unreachable", detect_service_unreachable),
    ("http_error_storm", detect_http_error_storm),
    ("muxer_failure", detect_muxer_failure),
    ("long_idle", detect_long_idle),
    ("json_parse_failure", detect_json_parse_failure),
    ("chaos_verdict", detect_chaos_verdict),
    ("browser_console_errors", detect_browser_console_errors),
    ("segment_gap", detect_segment_gap),
]


def diagnose(finding, events_by_id):
    """Assign a root cause class and a one-line diagnosis.
    Evidence is the surrounding 5 events."""
    det = finding["detector"]
    evidence_ids = finding.get("evidence_event_ids", [])
    context = [events_by_id.get(eid, {}).get("msg", "")[:200] for eid in evidence_ids]

    if det == "service_unreachable":
        return ("upstream_dependency",
                f"Target {finding.get('target','?')} refused connections "
                f"{finding['occurrences']}x. Check that the upstream service is running and reachable.")
    if det == "long_idle":
        return ("upstream_dependency" if finding.get("service") == "TTS" else "code_bug",
                f"Service {finding.get('service','?')} reported idle/warming for "
                f"~{finding['idle_seconds']}s without transitioning to ready. "
                f"Check model load, GPU availability, and warmup logs.")
    if det == "muxer_failure":
        return ("upstream_dependency",
                f"ffmpeg {finding.get('ffmpeg_tag','?')} muxer reported pipeline failures "
                f"{finding['occurrences']}x. Check RTMP target reachability and tee output health.")
    if det == "restart_loop":
        return ("code_bug" if finding.get("max_attempt", 0) >= 3 else "race_condition",
                f"Pipeline restart loop detected ({finding['restart_count']} restarts, "
                f"max attempt {finding['max_attempt']}). Underlying fault not resolved by restart.")
    if det == "escalating_health":
        return ("upstream_dependency" if "TTS" in finding.get("scope", "") else "code_bug",
                f"Health counter for {finding.get('scope','?')} escalated "
                f"{finding['counter_min']}->{finding['counter_max']} within window. "
                f"Watchdog will trigger hard restart soon.")
    if det == "http_error_storm":
        return ("code_bug",
                f"HTTP {finding['status_code']} storm ({finding['occurrences']} occurrences). "
                f"Backend route is failing; check server logs for the cause.")
    if det == "chaos_verdict":
        text = finding.get("verdict_text", "")[:160]
        return ("architecture",
                f"Chaos drill verdict: {text}. "
                f"This indicates a design-level limitation, not a runtime bug.")
    if det == "json_parse_failure":
        return ("upstream_dependency",
                f"LLM returned unparseable JSON {finding['occurrences']}x. "
                f"Check the prompt, the model version, and the parseJson fallback chain.")
    if det == "browser_console_errors":
        return ("code_bug",
                f"Dashboard console reported {finding['occurrences']} repeated errors. "
                f"Backend API may be unavailable; dashboard is keeping last-good-state.")
    if det == "repeated_message":
        msg = finding.get("msg_template", "")[:120]
        return ("code_bug",
                f"Repeated message in scope '{finding.get('scope','?')}': {msg}. "
                f"Investigate root cause; this is a sustained condition, not noise.")
    return ("unknown", "No diagnosis available.")


def severity_for(finding):
    det = finding["detector"]
    occ = finding.get("occurrences", 1)
    sev = "low"
    if det in ("chaos_verdict", "restart_loop"):
        sev = "high"
    elif det in ("muxer_failure", "service_unreachable"):
        sev = "high" if occ >= 2 else "medium"
    elif det in ("http_error_storm", "long_idle", "escalating_health"):
        sev = "high" if occ >= 5 else "medium"
    elif det == "json_parse_failure":
        sev = "medium"
    elif det == "browser_console_errors":
        sev = "medium"
    return sev


def recommended_action(finding):
    det = finding["detector"]
    if det == "service_unreachable":
        target = finding.get("target", "?")
        return (f"1. Verify {target} is running: `curl -fsS {target}/health` (or service-specific probe). "
                f"2. If the service is supposed to be local, check the process is alive (`pgrep -af <svc>`). "
                f"3. If the target is an external API, check status page and recent changes.")
    if det == "long_idle":
        return (f"1. Check the model load path for OOM/timeout. "
                f"2. Increase the watchdog warmup grace period if the load is legitimately slow. "
                f"3. Verify GPU is still attached: `nvidia-smi`.")
    if det == "muxer_failure":
        return (f"1. Verify all RTMP targets are reachable from this host. "
                f"2. Check mediamtx/Rumble endpoint health. "
                f"3. Add the specific failure mode to AGENTS.md \"Common pitfalls\".")
    if det == "restart_loop":
        return (f"1. Read the first restart's underlying error — the loop is a symptom, not the cause. "
                f"2. Add a circuit-breaker around the recurring fault. "
                f"3. If unfixable in this session, surface as BLOCKED with reproduction steps.")
    if det == "escalating_health":
        return (f"1. The watchdog will hard-restart soon; prepare for that. "
                f"2. Add a probe or alert on this counter's trajectory before it crosses the threshold.")
    if det == "http_error_storm":
        return (f"1. Capture the server-side stack trace for one of these requests. "
                f"2. Check the orchestrator HTTP route handling the affected path. "
                f"3. Add an integration test that exercises this path under load.")
    if det == "chaos_verdict":
        return (f"1. Read the full chaos summary and understand why the drill was unsatisfiable. "
                f"2. Decide: fix the architecture to make the drill satisfiable, "
                f"   OR explicitly accept the limitation in AGENTS.md and move on.")
    if det == "json_parse_failure":
        return (f"1. Inspect the raw LLM response (it should be in the orchestrator log). "
                f"2. Extend parseJson's fallback regex if the response has a new wrapping pattern. "
                f"3. If persistent, add the failure rate as a watchdog signal.")
    if det == "browser_console_errors":
        return (f"1. Check whether the dashboard's `/api/dashboard` endpoint is returning an error. "
                f"2. The dashboard's last-good-state hides this from on-air viewers; "
                f"   surface it more loudly (badge in the UI? banner?).")
    if det == "segment_gap":
        return (f"1. The producer loop has stalled silently — no crash, no restart, just silence. "
                f"2. Check the editorial + signal pipeline: is `rankUnused()` returning items? "
                f"3. Check the WS state stream: is `nextInSec` advancing? "
                f"4. Add a watchdog probe that surfaces \"no new segment in N minutes\" as a warn.")
    if det == "repeated_message":
        return (f"1. Read the surrounding context to identify the underlying fault. "
                f"2. Add a dedicated detector for this pattern if it's a recurring class. "
                f"3. Add to the relevant sub-skill's \"Known failure modes\" if it's project-specific.")
    return "Investigate."


def patch_target_for(finding):
    """Return (target_path, section_name, patch_text) or (None, None, None)."""
    det = finding["detector"]
    if det == "muxer_failure":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **ffmpeg tee muxer failures cascade.** A single `[tee @ ...] All tee outputs failed` "
                f"is followed by `[flv @ ...] Failed to update header` and the orchestrator's "
                f"`restarting pipeline (attempt 1)` log. Treat the first tee failure as the root cause; "
                f"downstream messages are consequences. Check RTMP target reachability first.")
    if det == "service_unreachable" and finding.get("target", "").endswith(":8800"):
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **TTS service can take 60-180 seconds to warm.** Distinguish \"loaded:false during warmup\" "
                f"from \"port 8800 not accepting connections at all.\" `curl: (7) Failed to connect` "
                f"means the process is gone or never started; `loaded:false` for >90s means the model "
                f"is stuck loading. Different remediation paths.")
    if det == "long_idle":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **TTS `loaded:false` for >2 minutes is a fault, not a warmup.** "
                f"The 60-180s warmup window is documented, but anything beyond that indicates "
                f"a stuck model load (CUDA OOM, broken HF download, etc.). Add a watchdog probe "
                f"that surfaces this rather than waiting for the watchdog's hard-restart threshold.")
    if det == "http_error_storm":
        return ("dashboard/src/state.ts", None,
                f"// NOTE: when `/api/dashboard` returns 500, the dashboard falls back to last-good-state. "
                f"// This hides outages from on-air viewers. Consider surfacing a degraded-mode badge "
                f"in the top bar so operators notice.")
    if det == "browser_console_errors":
        return ("dashboard/src/state.ts", None,
                f"// NOTE: console warns on every 500 are noisy and easy to miss. "
                f"// Surface a persistent degraded-mode indicator in the TopBar.")
    if det == "chaos_verdict":
        return ("orchestrator/AGENTS.md", "Architecture invariants",
                f"- **The cached SQLite handle survives rename + unlink.** "
                f"Chaos drills that try to corrupt the DB on a running orchestrator are unsatisfiable "
                f"because `better-sqlite3` keeps the inode alive via the open FD. Either accept this "
                f"limitation (and document it) or close the handle when the watchdog detects a "
                f"file-level anomaly.")
    if det == "segment_gap":
        return ("orchestrator/AGENTS.md", "Common pitfalls (for agents)",
                f"- **The producer can stall silently.** No error, no restart, no watchdog trip — "
                f"the editorial loop simply stops emitting segments. The watchdog's 5s heartbeats all "
                f"look healthy. Add a watchdog probe that watches the gap between consecutive "
                f"`producing ... from:` log lines and surfaces a warn after >15 minutes of silence.")
    return (None, None, None)


def write_patches(output_dir, findings):
    patches_dir = os.path.join(output_dir, "patches")
    os.makedirs(patches_dir, exist_ok=True)
    written = []
    seen = set()
    for f in findings:
        target = patch_target_for(f)
        if not target or not target[0]:
            continue
        path, section, text = target
        # Dedupe by (target_path, section, text-hash) — multiple findings of
        # the same detector with identical recommendations collapse to one.
        key = (path, section, hash(text))
        if key in seen:
            continue
        seen.add(key)
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", path)
        out_path = os.path.join(patches_dir, f"{safe}.md")
        with open(out_path, "a") as fh:
            if os.path.getsize(out_path) == 0:
                fh.write(f"# Suggested patches for `{path}`\n\n")
            fh.write(f"## Finding: `{f.get('detector')}` — "
                     f"{f.get('occurrences', 1)} occurrences, "
                     f"{f.get('first_seen', '?')} → {f.get('last_seen', '?')}\n\n")
            if section:
                fh.write(f"Append under `## {section}`:\n\n")
            else:
                fh.write(f"Add at an appropriate location:\n\n")
            fh.write(text + "\n\n---\n\n")
        written.append(out_path)
    return written


def build_feature_index(inventory):
    """Load features.json and return:
       features_by_id: {feature_id: {id, slug, status, tokens: set}}
       tokens_to_id: {token: feature_id}
    Where `tokens` includes the feature slug (e.g. "m1-mypy-strict-tts"),
    each worker session UUID, and any handoff filename stem. The
    tokens_to_id map is the reverse index used to find which feature(s)
    a given evidence source path belongs to.

    Returns ({}, {}) if no features.json is found.
    """
    mission_dir = inventory.get("mission_dir")
    if not mission_dir:
        return {}, {}
    features_path = os.path.join(mission_dir, "features.json")
    if not os.path.isfile(features_path):
        return {}, {}
    try:
        with open(features_path) as f:
            doc = json.load(f)
    except Exception:
        return {}, {}
    raw = doc.get("features") if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return {}, {}

    features_by_id = {}
    tokens_to_id = {}
    for feat in raw:
        fid = feat.get("id")
        if not fid:
            continue
        slug = fid
        tokens = {slug}
        for k in ("workerSessionIds", "currentWorkerSessionId", "completedWorkerSessionId"):
            v = feat.get(k)
            if isinstance(v, str):
                tokens.add(v)
            elif isinstance(v, list):
                tokens.update(v)
        # also index milestone-prefixed tokens (e.g., m1, m2)
        m = re.match(r"^(m\d+)", slug)
        if m:
            tokens.add(m.group(1))
        features_by_id[fid] = {
            "id": fid,
            "slug": slug,
            "status": feat.get("status", ""),
            "tokens": tokens,
        }
        for tok in tokens:
            tokens_to_id.setdefault(tok, set()).add(fid)
    return features_by_id, tokens_to_id


def features_affected_for(finding, events_by_id, tokens_to_id):
    """Return the count of distinct features affected by a finding.

    A finding is considered to affect a feature if any of its evidence
    events' source path contains one of the feature's tokens (slug or
    worker session UUID). Returns 0 if no features.json was loaded or
    if no token matched.
    """
    if not tokens_to_id:
        return 0
    affected = set()
    for eid in finding.get("evidence_event_ids", []):
        ev = events_by_id.get(eid, {})
        src = ev.get("source", "") or ""
        for tok, feat_ids in tokens_to_id.items():
            if tok and tok in src:
                affected.update(feat_ids)
    return len(affected)


def main():
    if len(sys.argv) < 2:
        print("usage: cluster-findings.py <output-dir> [--top N]", file=sys.stderr)
        sys.exit(2)
    output_dir = sys.argv[1]
    top_n = 10
    if "--top" in sys.argv:
        i = sys.argv.index("--top")
        top_n = int(sys.argv[i + 1])

    cfg = load_config()
    events_path = os.path.join(output_dir, "events.jsonl")
    if not os.path.exists(events_path):
        print(f"ERROR: {events_path} not found. Run parse-progress-log.sh first.", file=sys.stderr)
        sys.exit(1)
    events = []
    with open(events_path) as f:
        for line in f:
            events.append(json.loads(line))

    events_by_id = {e["id"]: e for e in events}

    # Load features.json (if inventory.json has a mission_dir) and build
    # the feature-token index used by features_affected_for() below.
    inventory_path = os.path.join(output_dir, "inventory.json")
    inventory = {}
    if os.path.isfile(inventory_path):
        try:
            with open(inventory_path) as f:
                inventory = json.load(f)
        except Exception:
            inventory = {}
    _features_by_id, tokens_to_id = build_feature_index(inventory)
    features_loaded = bool(tokens_to_id)

    # Run all detectors
    all_findings = []
    detector_counts = {}
    for name, fn in DETECTORS:
        try:
            fs = fn(events, cfg)
        except Exception as e:
            fs = []
            print(f"detector {name} crashed: {e}", file=sys.stderr)
        detector_counts[name] = len(fs)
        all_findings.extend(fs)

    # Assign id, severity, diagnosis, action
    idgen = dedup_id()
    severity_buckets = collections.Counter()
    for f in all_findings:
        f["id"] = next(idgen)
        f["severity"] = severity_for(f)
        rc, diag = diagnose(f, events_by_id)
        f["root_cause_class"] = rc
        f["diagnosis"] = diag
        f["recommended_action"] = recommended_action(f)
        # LIKELY_KNOWN heuristic: if msg_template mentions "loaded=false" + (TTS or model)
        if f["detector"] == "long_idle" and f.get("idle_seconds", 0) < 90:
            f["likely_known"] = True
        elif f["detector"] == "repeated_message" and "breaker.call" in f.get("msg_template", ""):
            f["likely_known"] = True
        elif f["detector"] == "escalating_health" and f.get("counter_max", 0) <= 2:
            f["likely_known"] = True
        else:
            f["likely_known"] = False
        severity_buckets[f["severity"]] += 1

    # Rank
    weights = cfg["ranking"]
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    for f in all_findings:
        occ = f.get("occurrences", 1)
        last_ts = parse_ts(f.get("last_seen", ""))
        recency_hours_inverse = 0
        if last_ts:
            hours = max(0.0, (now - last_ts).total_seconds() / 3600)
            recency_hours_inverse = max(0.0, 10 - hours)  # higher when recent
        features_affected = features_affected_for(f, events_by_id, tokens_to_id)
        f["distinct_features_affected"] = features_affected
        score = (occ * weights["weight_occurrences"]
                 + recency_hours_inverse * weights["weight_recency_inverse"]
                 + features_affected * weights["weight_features_affected"]
                 - (5.0 if f.get("likely_known") else 0.0) * weights["penalty_likely_known"] / 5.0)
        f["impact_score"] = round(score, 2)

    all_findings.sort(key=lambda x: x["impact_score"], reverse=True)
    primary = all_findings[:top_n]
    appendix = all_findings[top_n:]

    # Write findings.json
    with open(os.path.join(output_dir, "findings.json"), "w") as f:
        json.dump({
            "primary": primary,
            "appendix": appendix,
            "all_count": len(all_findings),
        }, f, indent=2)

    # Write summary.json
    summary = {
        "events_analyzed": len(events),
        "findings_total": len(all_findings),
        "findings_primary": len(primary),
        "severity_buckets": dict(severity_buckets),
        "detector_counts": detector_counts,
        "features_loaded": features_loaded,
        "feature_count": len(_features_by_id),
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Write patches
    patches = write_patches(output_dir, all_findings)
    summary["patch_files_written"] = len(patches)
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"findings.json: {len(all_findings)} total ({len(primary)} primary + {len(appendix)} appendix)")
    print(f"severity buckets: {dict(severity_buckets)}")
    print(f"detector counts: {detector_counts}")
    print(f"patches written: {len(patches)}")


if __name__ == "__main__":
    main()

```

## File: `scripts/render-report.py`

```
#!/usr/bin/env python3
"""render-report.py — Phase 8: render reflection.md from findings.json + events.jsonl.
Usage: render-report.py <output-dir>
"""
import json
import os
import re
import sys
import pathlib

SKILL_DIR = pathlib.Path.home() / ".factory" / "skills" / "self-reflect"
TEMPLATE_PATH = SKILL_DIR / "REPORT-TEMPLATE.md"


def load_events(output_dir):
    path = os.path.join(output_dir, "events.jsonl")
    events_by_id = {}
    with open(path) as f:
        for line in f:
            ev = json.loads(line)
            events_by_id[ev["id"]] = ev
    return events_by_id


def evidence_excerpt(events_by_id, ids, max_lines=5):
    lines = []
    for eid in ids[:max_lines]:
        ev = events_by_id.get(eid, {})
        ts = ev.get("ts", "")
        scope = ev.get("scope", "")
        msg = ev.get("msg", "")[:200]
        # strip ANSI escape codes AND NUL bytes so the rendered .md
        # stays plain text and `file` recognizes it as such
        msg = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", msg)
        msg = msg.replace("\x00", "")
        lines.append(f"[{ts}] [{scope}] {msg}")
    return "\n".join(lines)


def sanitize_for_markdown(text):
    """Strip ANSI codes and NULs from any string before it goes into the
    rendered report. Used for the title and any other rendered field."""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    text = text.replace("\x00", "")
    return text


def missed_patterns(events, all_finding_event_ids):
    """Sample warn/error events that no detector matched.
    Returns a list of (event_id, msg, suggested_detector) tuples."""
    matched_ids = set(all_finding_event_ids)
    sample = []
    for ev in events:
        if ev.get("level") not in ("warn", "error"):
            continue
        if ev["id"] in matched_ids:
            continue
        msg = ev.get("msg", "")
        suggested = "unknown"
        if "consecutive failures" in msg:
            suggested = "escalating_health"
        elif "loaded=false" in msg or "ready=false" in msg:
            suggested = "long_idle"
        elif "Failed to connect" in msg or "ECONNREFUSED" in msg:
            suggested = "service_unreachable"
        elif "tee @ " in msg or "Broken pipe" in msg or "Failed to update header" in msg:
            suggested = "muxer_failure"
        elif "did not return parseable JSON" in msg:
            suggested = "json_parse_failure"
        elif "/api/" in msg or "HTTP" in msg.upper():
            suggested = "http_error_storm"
        elif "restarting" in msg.lower():
            suggested = "restart_loop"
        elif "verdict:" in msg.lower():
            suggested = "chaos_verdict"
        elif "console" in ev.get("source", "").lower():
            suggested = "browser_console_errors"
        else:
            suggested = "repeated_message (above threshold?"
        sample.append((ev["id"], msg[:200], suggested, ev.get("scope", "")))
    return sample[:25]


def main():
    if len(sys.argv) < 2:
        print("usage: render-report.py <output-dir>", file=sys.stderr)
        sys.exit(2)
    output_dir = sys.argv[1]

    with open(os.path.join(output_dir, "findings.json")) as f:
        findings_data = json.load(f)
    with open(os.path.join(output_dir, "summary.json")) as f:
        summary = json.load(f)
    with open(os.path.join(output_dir, "inventory.json")) as f:
        inv = json.load(f)
    events_by_id = load_events(output_dir)
    events = list(events_by_id.values())

    primary = findings_data["primary"]
    appendix = findings_data["appendix"]
    sev_buckets = summary["severity_buckets"]

    # Executive summary
    if not primary:
        exec_summary = (
            "No findings matched any detector threshold. "
            "Possible causes: (a) the log corpus is too sparse, (b) thresholds in config.yaml are too strict, "
            "or (c) the detectors do not yet cover the failure shapes present in this corpus. "
            "Inspect the `Missed patterns` section below for events that should have triggered but did not."
        )
    else:
        top = primary[0]
        exec_summary = (
            f"Analyzed {summary['events_analyzed']} events from "
            f"{len(inv.get('mission_artifacts',{}).get('present',[]))} mission artifacts and "
            f"{len(inv.get('run_artifacts',{}).get('present',[]))} runtime logs. "
            f"Detected {summary['findings_total']} findings ({summary['findings_primary']} primary, "
            f"{len(appendix)} appendix). Severity: {sev_buckets}. "
            f"Highest-impact pattern: `{top['detector']}` — {top.get('diagnosis','?')}"
        )

    # Detector health table
    detector_rows = []
    for det_name in [
        "repeated_message", "escalating_health", "restart_loop",
        "service_unreachable", "http_error_storm", "muxer_failure",
        "long_idle", "json_parse_failure", "chaos_verdict", "browser_console_errors",
    ]:
        cnt = summary.get("detector_counts", {}).get(det_name, 0)
        over = "yes" if cnt > 50 else ""
        under = "yes" if cnt == 0 else ""
        detector_rows.append(f"| `{det_name}` | {cnt} | {over} | {under} |")

    # Findings sections
    findings_md = []
    for i, f in enumerate(primary, start=1):
        title = sanitize_for_markdown(f.get("diagnosis") or f.get("detector", "?"))[:120]
        evidence = evidence_excerpt(events_by_id, f.get("evidence_event_ids", []))
        sev = f.get("severity", "?")
        rc = f.get("root_cause_class", "?")
        occ = f.get("occurrences", 1)
        first = f.get("first_seen", "?")
        last = f.get("last_seen", "?")
        likely = "yes" if f.get("likely_known") else "no"
        diag = sanitize_for_markdown(f.get("diagnosis", "?"))
        action = sanitize_for_markdown(f.get("recommended_action", "?"))
        patch_tgt = patch_target_for_label(f)
        impact = f.get("impact_score", "?")
        features = f.get("distinct_features_affected", 0)
        findings_md.append(
            f"### {i}. {title}\n\n"
            f"- **Detector:** `{f.get('detector','?')}`\n"
            f"- **Severity:** {sev} ({rc})\n"
            f"- **Occurrences:** {occ}\n"
            f"- **Distinct features affected:** {features}\n"
            f"- **First seen:** {first}\n"
            f"- **Last seen:** {last}\n"
            f"- **Likely known?** {likely}\n"
            f"- **Impact score:** {impact}\n\n"
            f"**Diagnosis:** {diag}\n\n"
            f"**Evidence:**\n\n```\n{evidence}\n```\n\n"
            f"**Recommended action:** {action}\n\n"
            f"**Patch target:** {patch_tgt}\n"
        )

    # Appendix
    appendix_md = []
    for f in appendix[:20]:
        title = sanitize_for_markdown(f.get("diagnosis") or f.get("detector", "?"))[:100]
        appendix_md.append(
            f"- `{f.get('detector','?')}` ({f.get('severity','?')}, impact={f.get('impact_score','?')}): "
            f"{title} — {f.get('occurrences',1)} occurrences, "
            f"{f.get('first_seen','?')} → {f.get('last_seen','?')}"
        )

    # Missed patterns
    # Collect ALL evidence event ids from findings (not just the first 10)
    all_matched_ids = set()
    for f in primary + appendix:
        for eid in f.get("evidence_event_ids", []):
            all_matched_ids.add(eid)
    missed = missed_patterns(events, all_matched_ids)

    missed_rows = []
    for eid, msg, suggested, scope in missed:
        missed_rows.append(
            f"| `{eid}` | `{scope}` | {sanitize_for_markdown(msg)[:100]} | {suggested} |"
        )

    # Threshold tuning
    detector_counts = summary.get("detector_counts", {})
    tuning = []
    for det, cnt in detector_counts.items():
        if cnt == 0:
            tuning.append(
                f"- `{det}` fired 0 times. Either (a) the corpus doesn't contain this pattern, "
                f"(b) the threshold is too strict, or (c) the regex is too narrow. "
                f"Inspect `missed_patterns` to disambiguate."
            )
        elif cnt > 50:
            tuning.append(
                f"- `{det}` fired {cnt} times — possibly over-triggered. "
                f"Consider adding to the `What to skip` section of its detector spec."
            )
    if not tuning:
        tuning.append("- No tuning recommended.")

    # Patch file list
    patches_dir = os.path.join(output_dir, "patches")
    patch_files = []
    if os.path.isdir(patches_dir):
        for fn in sorted(os.listdir(patches_dir)):
            patch_files.append(f"- `patches/{fn}`")

    # Render — substitute known placeholders, then drop any remaining
    # placeholder section by inserting real findings in its place.
    template = TEMPLATE_PATH.read_text()
    rendered = (
        template
        .replace("{{MISSION_DIR}}", str(inv.get("mission_dir") or "(none)"))
        .replace("{{RUN_DIR}}", str(inv.get("run_dir") or "(none)"))
        .replace("{{ANALYZED_AT}}", inv.get("analyzed_at", "?"))
        .replace("{{EVENT_COUNT}}", str(summary.get("events_analyzed", 0)))
        .replace("{{FINDING_COUNT}}", f"{summary['findings_primary']} (+ {len(appendix)} appendix)")
        .replace("{{SEVERITY_BUCKETS}}", ", ".join(f"{k}={v}" for k, v in sev_buckets.items()))
        .replace("{{EXECUTIVE_SUMMARY}}", exec_summary)
        .replace("{{DETECTOR_HEALTH_ROWS}}", "\n".join(detector_rows))
        .replace("{{MORE_FINDINGS}}", "yes" if appendix else "")
        .replace("{{APPENDIX_FINDINGS}}", "\n".join(appendix_md) if appendix_md else "(none)")
        .replace("{{MISSED_PATTERNS_TABLE}}",
                 "| Event ID | Scope | Message | Suggested detector |\n"
                 "| --- | --- | --- | --- |\n" + "\n".join(missed_rows) if missed_rows else
                 "(none — every warn/error event matched at least one detector)")
        .replace("{{THRESHOLD_TUNING_SUGGESTIONS}}", "\n".join(tuning))
        .replace("{{PATCH_FILE_LIST}}", "\n".join(patch_files) if patch_files else "(no patches generated)")
    )

    # Strip any remaining placeholders (the dummy top-finding block in template)
    rendered = re.sub(r"\{\{[A-Z_]+\}\}", "", rendered)
    # Drop the placeholder finding block — it's from the template, not real data.
    rendered = re.sub(
        r"### 1\. \(see sections below\).*?(?=^## |\Z)",
        "",
        rendered,
        flags=re.DOTALL | re.MULTILINE,
    )

    # Strip the template's inert placeholder block (the comment + appendix
    # block were left over from the template). We re-add the appendix
    # AFTER the real findings, just before Self-Review.
    rendered = re.sub(
        r"<!--.*?-->\s*",
        "",
        rendered,
        flags=re.DOTALL,
    )
    # Drop the appendix section from the template — we re-add it after findings
    rendered = re.sub(
        r"\{\{#if MORE_FINDINGS\}\}.*?\{\{/if\}\}",
        "",
        rendered,
        flags=re.DOTALL,
    )

    # Insert the real findings + appendix just before "## Self-Review"
    sections_text = "\n\n".join(findings_md)
    appendix_text = ""
    if appendix_md:
        appendix_text = (
            "\n\n## Appendix: Additional Findings\n\n"
            + "\n".join(appendix_md)
            + "\n"
        )
    if "## Self-Review" in rendered:
        rendered = rendered.replace(
            "## Self-Review",
            sections_text + appendix_text + "\n\n## Self-Review",
        )
    else:
        rendered = rendered + "\n\n" + sections_text + appendix_text

    out_path = os.path.join(output_dir, "reflection.md")
    # belt-and-braces: sanitize the entire rendered text one more time
    # (in case any string slipped through individual sanitize calls)
    rendered = sanitize_for_markdown(rendered)
    with open(out_path, "w") as f:
        f.write(rendered)
    print(f"reflection.md written: {out_path}")


def patch_target_for_label(f):
    det = f.get("detector")
    if det == "muxer_failure":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "service_unreachable" and "8800" in str(f.get("target", "")):
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "long_idle":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    if det == "http_error_storm":
        return "`dashboard/src/state.ts`"
    if det == "browser_console_errors":
        return "`dashboard/src/state.ts`"
    if det == "chaos_verdict":
        return "`orchestrator/AGENTS.md` (Architecture invariants)"
    if det == "segment_gap":
        return "`orchestrator/AGENTS.md` (Common pitfalls)"
    return "(code fix — no markdown patch)"


if __name__ == "__main__":
    main()

```
