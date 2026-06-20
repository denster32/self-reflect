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
