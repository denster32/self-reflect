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
