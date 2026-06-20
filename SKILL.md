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
