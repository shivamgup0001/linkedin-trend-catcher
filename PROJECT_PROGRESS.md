# LinkedIn Trend Catcher — Project Progress

This is the living handoff document for the project. Read it before starting new
work, then update it before finishing a feature so future work begins from the
current state rather than reconstructing project history.

Last updated: 2026-09-24

## Current status

The project has a complete mocked/tested pipeline for discovering LinkedIn posts
from keywords, hashtags, creator activity pages, and company post pages. It can
parse and identify posts, persist observations and engagement snapshots in
MongoDB, refresh saved posts, rank growth, record collection diagnostics, and
display results in a read-only Streamlit dashboard.

The multi-source pipeline was verified against live LinkedIn pages after the
parallel development work. A healthy run completed across all nine enabled
pilot sources, but the original workload was too aggressive: up to 100 direct
refreshes plus 30 candidates from each source every three hours. LinkedIn later
logged the account out after detecting high activity. The final two scheduled
runs therefore produced no usable observations.

The LaunchAgent is intentionally **unloaded** and its future interval is now
configured for twelve hours. The saved LinkedIn
session currently redirects to the login page and must be renewed manually.
Authentication fail-fast behavior and lower limits are implemented and mocked;
do not restart scheduled collection until they pass a controlled live run.

Verification at this checkpoint:

- `python3 -m unittest discover -s tests -v`: **84 tests passed**
- Tests are mocked/unit-level and do not contact LinkedIn or MongoDB.
- Live multi-source verification succeeded before the account session was
  invalidated; later failures were operational/authentication failures rather
  than evidence that every source collector broke simultaneously.
- Python compilation passed at the preceding company-source checkpoint; the
  full suite imports and executes the current Python modules successfully.
- The working tree contains substantial uncommitted work. Check `git status`
  before editing, and do not discard or overwrite those changes.

## End-to-end flow

```text
config/keywords.yaml
        |
        v
load and validate DiscoverySource objects
        |
        v
dispatch source adapter (keyword / hashtag / creator / company)
        |
        v
navigate -> detect expired session -> wait -> scroll -> collect candidates
        |
        v
filter candidates -> parse post -> resolve canonical URL
        |
        v
persist post metadata + source attribution + engagement snapshot
        |
        +------> directly refresh saved LinkedIn URLs
        |
        +------> calculate weighted engagement growth
        |
        +------> persist run/source diagnostics and show dashboard
```

Ordinary discovery-source failures are isolated and later sources continue.
Authentication challenges and HTTP 429 responses stop the full run. Candidate
processing defaults to 5 items per source.

## What is built

### Discovery configuration

- `DiscoverySourceType` supports `keyword`, `hashtag`, `creator`, and `company`.
- Structured YAML supports enabled/disabled sources.
- Legacy top-level `keywords:` configuration remains supported.
- Values are normalized and deduplicated without reordering.
- Creator URLs must match LinkedIn `/in/.../` profiles.
- Company URLs must match LinkedIn `/company/.../` pages.
- Unknown sections, fields, malformed values, and mixed legacy/structured
  formats are rejected with configuration errors.
- At this checkpoint, the checked-in configuration enables 2 keywords,
  2 hashtags, 3 creators, and 2 companies. Re-check the YAML before a run.

Key files:

- `config/discovery_source.py`
- `config/config_loader.py`
- `config/keywords.yaml`

### Source-specific discovery

- Keyword discovery adapts the existing LinkedIn content search.
- Hashtag discovery generates an encoded `#hashtag` content-search URL.
- Creator discovery generates `/in/<slug>/recent-activity/all/` URLs.
- Company discovery generates `/company/<slug>/posts/?feedView=all` URLs.
- URL generation uses structured URL parsing/building.
- Login, signup, authwall, and checkpoint redirects report an expired session.
- Logged-out controls on otherwise normal-looking URLs are also detected.
- Shared navigation waits for the LinkedIn workspace and supports known layout
  fallbacks.
- Empty result sets return empty locators without failing the entire run.
- Unsupported creator/company layouts are surfaced through per-source status.
- Existing scrolling and candidate collection components are reused.

Key files:

- `collector/source_page.py` — shared navigation/auth/workspace helpers
- `collector/source_adapter.py` — adapter registry and keyword adapter
- `collector/hashtag_source.py`
- `collector/creator_source.py`
- `collector/company_source.py`
- `collector/search.py`
- `collector/scroller.py`
- `collector/collector.py`

### Orchestration and isolation

- `main.py` loads every enabled source and dispatches the matching adapter.
- Sources run sequentially, each in its own page.
- Pages are closed even when loading or candidate processing fails.
- One broken source does not prevent later sources from running.
- Candidate errors are recorded without aborting the source.
- `--max-candidates-per-source` limits work independently per source and records
  truncation as a diagnostic skip reason.
- Supported modes are `all`, `discover`, and `refresh`.
- An optional in-process interval exists, though external scheduling is
  recommended.

### Parsing and post identity

- Parses author, author URL, post text, relative post age, reactions, comments,
  reposts, post URL, and LinkedIn activity ID when available.
- Supports person, company, and school author links.
- Resolves canonical URLs through LinkedIn's “Copy link to post” menu when
  available, with DOM-based extraction as fallback.
- Normalizes LinkedIn post URLs and strips query/fragment tracking data.
- Extracts activity IDs from URLs, encoded URNs, DOM attributes, and known
  hidden live-video markup.
- Rejects navigation/recommendation list items that are not posts.
- Parses comma-separated and compact metric counts such as `1,234` and `2.5K`.
- Uses identity priority: LinkedIn activity ID, canonical LinkedIn URL, then a
  stable content fingerprint.
- Promotes a previously fingerprinted record when a stronger identity later
  becomes available.

Key files:

- `collector/parser.py`
- `collector/collector.py`
- `models/post.py`
- `database/mongo.py`

### Persistence and source attribution

MongoDB uses three logical collections:

- Main post collection from `COLLECTION_NAME`: post metadata and current
  tracking state.
- `post_snapshots`: timestamped engagement observations.
- `collection_runs`: run-level and per-source diagnostics.

Implemented behavior:

- Unique post identity and unique `(post_id, observed_at)` snapshots.
- Every post retains all distinct discovery origins in `discovery_sources`.
- Source attribution stores type/value and, for creators/companies, name/URL.
- Repeated discovery does not duplicate attribution.
- Legacy `keyword` behavior remains compatible.
- A non-keyword source does not overwrite an existing legacy keyword.
- Refresh success/failure state and failure counts are saved.
- Refresh targets are bounded by post age and limit.

### Direct refresh and growth ranking

- Saved `/feed/update/` and `/posts/` URLs can be revisited directly.
- Refresh results distinguish successful, missing, unavailable, and exceptional
  outcomes and persist diagnostics.
- Engagement growth compares a current snapshot with an eligible earlier
  baseline, not merely the immediately previous snapshot.
- Default weights are reactions `1`, comments `3`, and reposts `5`.
- Ranking now separates stabilized absolute Momentum from relative
  Breakout. Both apply a six-hour rate floor and evidence-based confidence so
  short observation intervals do not dominate the results.
- Minimum observation window, minimum growth, maximum post age, and refresh
  limits are configurable through CLI flags.
- Fingerprint-only posts can be observed again through discovery but cannot be
  directly refreshed after disappearing from discovery results.

Key files:

- `collector/tracker.py`
- `analytics/growth.py`
- `analytics/trend_analyzer.py`

### Diagnostics

- Every collection run starts and finishes a persisted diagnostic record.
- Run status supports running, completed, partial, and failed outcomes.
- Per-source status supports completed, empty, partial, and failed outcomes.
- Counters include candidates, truncation, valid posts, saved posts, canonical
  URLs, directly refreshable posts, skips, and quality warnings.
- Errors are structured, bounded in number, and truncated to avoid unbounded
  diagnostic documents.
- A top-level exception still finalizes the persisted run as failed.

Key file: `models/collection_run.py`

### Dashboard

- Read-only Streamlit dashboard backed by MongoDB.
- Overview metrics for total posts, directly refreshable posts, snapshot depth,
  refresh failures, and latest observation.
- Trending table with keyword, author, refresh, source-type, and source-value
  filters.
- Post detail view with metadata, source attribution, exact LinkedIn URL, and
  engagement history.
- Post detail offers a newest-first selector for every saved post and preserves
  table selections across Streamlit reruns.
- Collection Health view backed by persisted run and per-source diagnostics.
- Dashboard data functions support both new multi-source documents and legacy
  keyword-only documents.

Key files:

- `dashboard.py`
- `dashboard_data.py`

### Scheduling

- `scripts/run_once.sh` runs one headless `all` cycle.
- `scheduler/com.linkedin-trend-catcher.plist` provides a macOS launch agent
  configured for a three-hour interval.
- Logs go to `/tmp/linkedin-trend-catcher.log` and
  `/tmp/linkedin-trend-catcher.error.log`.
- The plist currently contains an absolute local project path and must be
  updated if the project moves or is installed for another user.
- The LaunchAgent is currently unloaded by design after LinkedIn logged the
  account out for high activity.

### Experimental AI/reporting code

- `analytics/report_printer.py`, `ai/prompt_builder.py`, and `ai/summarizer.py`
  exist from an earlier reporting path.
- They are **not wired into the current collection/dashboard orchestration**.
- `Summarizer` currently targets Gemini, contains an unused OpenAI import, and
  its SDK dependencies are not listed in `requirements.txt`. Treat this area as
  experimental until it is deliberately integrated and tested.

### Agent development aids

- `AGENTS.md` contains concise repository-wide instructions for future coding
  agents, including safety boundaries, architecture conventions, and standard
  verification commands.
- `.agents/skills/linkedin-collector-development/SKILL.md` provides a focused
  workflow for discovery, navigation, parsing, canonical URL, and refresh
  changes.
- The skill deliberately excludes dashboard-only, analytics-only, and
  documentation-only work so unrelated tasks do not load unnecessary context.

## Setup and commands

Required environment values:

```text
MONGO_URI
DB_NAME
COLLECTION_NAME
```

The ignored `.env` file is the expected local location. The LinkedIn browser
session is stored under ignored `data/auth/linkedin_state.json` after the first
interactive login.

Install:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Run tests without live collection:

```bash
python3 -m unittest discover -s tests -v
```

Run collection only when a controlled live run is intended:

```bash
python3 main.py --mode discover
python3 main.py --mode discover --headless --max-candidates-per-source 30
python3 main.py --mode refresh --headless
python3 main.py --mode all --headless
```

Run dashboard:

```bash
python3 -m streamlit run dashboard.py
```

Useful CLI controls:

- `--mode {all,discover,refresh}`
- `--headless`
- `--max-candidates-per-source`
- `--max-post-age-days`
- `--min-window-hours`
- `--min-growth`
- `--refresh-limit`
- `--interval-hours`

All positive numeric options are validated by the CLI.

## Test coverage map

- `tests/test_config_loader.py`: structured/legacy config, normalization,
  validation, deduplication.
- `tests/test_hashtag_source.py`: hashtag URL, validation, expiry, empty/success.
- `tests/test_creator_source.py`: activity URL, validation, expiry, layout
  fallback, empty/success.
- `tests/test_company_source.py`: posts URL, validation, expiry, unsupported,
  empty/success.
- `tests/test_discovery_integration.py`: four-source dispatch, shared pipeline,
  per-source limits, failure isolation, dashboard compatibility.
- `tests/test_source_attribution.py`: normalized source storage, deduplication,
  multi-source attribution, identity promotion, legacy compatibility.
- `tests/test_tracking.py`: parsing, identity, metrics, candidates, growth.
- `tests/test_auth.py` and `tests/test_session.py`: startup validation, logged-out
  layouts, authentication URLs, and rate-limit detection.
- `tests/test_diagnostics.py`: run lifecycle, aggregation, error bounds.
- `tests/test_dashboard.py`: overview, trends, filters, details, run health.

## Known gaps and risks

1. **Safe live re-verification is pending.** Multi-source collection worked in
   a live run, but the saved session has since expired. A fresh low-volume smoke
   test is required after manual login and authentication hardening.
2. **LinkedIn automation is inherently brittle.** UI/DOM changes can invalidate
   selectors even when unit tests remain green.
3. **No end-to-end MongoDB integration test exists.** Persistence behavior is
   tested with fakes, not a real database instance.
4. **No CI configuration is present.** Tests are currently run manually.
5. **Current work is uncommitted.** Preserve the dirty worktree and make a
   deliberate reviewed checkpoint commit before larger refactors.
6. **Experimental AI reporting is incomplete.** Dependencies and orchestration
   need cleanup before use.
7. **Scheduler path is machine-specific.** Installation should eventually
   generate or document the correct absolute path.
8. **Operational compliance needs review.** Before production use, confirm the
   collection approach complies with LinkedIn terms, organizational policies,
   applicable privacy requirements, and rate limits.
9. **Safety controls still need live verification.** Startup session validation,
   authentication/rate-limit fail-fast behavior, 15 refreshes, 5 candidates per
   source, a 5-day tracking window, and a 12-hour schedule are implemented and
   mocked but have not yet been exercised against the renewed session.

## Recommended next steps

- [ ] Review the current dirty diff and create a coherent checkpoint commit.
- [x] Add authentication validation before collection and fail fast on login,
      signup, cold-join, checkpoint, or logged-out layouts.
- [x] Reduce refresh and per-source candidate limits, lengthen the schedule,
      and stop immediately after authentication or HTTP 429 warnings.
- [ ] Renew the LinkedIn session manually, then perform a small controlled smoke
      test for one source of each type.
- [ ] Record observed LinkedIn layouts and fix selectors only where evidence
      shows a mismatch.
- [ ] Verify one real MongoDB write/read cycle in a non-production database.
- [ ] Run the dashboard against that test data and verify source/health views.
- [ ] Add CI for unit tests and compilation checks.
- [ ] Decide whether to finish or remove the experimental AI reporting path.
- [ ] Improve scheduler portability and deployment documentation.

## Update protocol for future work

For every meaningful change:

1. Read this file before editing code.
2. Update **Current status** if the overall state changed.
3. Update the relevant capability section and file list.
4. Update **Test coverage map** when tests are added or moved.
5. Update **Known gaps and risks** and **Recommended next steps**.
6. Run the appropriate tests and record the exact result.
7. Add a short dated entry below.

Do not mark something complete merely because code exists. Record whether it is
unit-tested, integration-tested, and live-verified separately.

## Progress log

### 2026-09-24 — Collection safety limits and fail-fast handling

- Added startup validation for saved LinkedIn sessions and shared detection for
  login, signup, authwall, checkpoint, and logged-out layouts.
- Authentication challenges and HTTP 429 responses now stop refresh/discovery
  immediately instead of failing every remaining target or source.
- Reduced defaults to 15 refreshes, 5 candidates per source, and a 5-day
  tracking window; changed the dormant LaunchAgent interval to 12 hours.
- Ran the complete mocked suite (84 tests) without contacting LinkedIn or
  restarting the scheduler. A fresh login and controlled live run remain next.

### 2026-09-24 — Stabilized Momentum and Breakout ranking

- Replaced hourly-rate ordering with separate absolute Momentum and relative
  Breakout views while retaining the raw growth fields for compatibility.
- Added a six-hour denominator floor and low/medium/high confidence based on
  observation duration and snapshot depth.
- Updated dashboard controls, table columns, terminal output, defaults, and
  ranking documentation.
- Ran the complete mocked suite (75 tests), compilation, diff checks, and a
  read-only local Streamlit smoke test for both ranking views.
- Ranking still needs calibration against future real observations; LinkedIn
  collection and the scheduler remained stopped during this work.

### 2026-09-24 — Private dashboard deployment and post selection

- Deployed the read-only dashboard from the private GitHub repository to
  Streamlit Community Cloud with MongoDB credentials stored as platform
  secrets rather than committed files.
- Kept the deployed app private with viewer access controlled by invitation.
- Added a persistent, searchable Post Detail selector so the view no longer
  depends exclusively on a temporary Trending Posts table selection.

### 2026-09-24 — Automation paused after LinkedIn account logout

- Verified the integrated keyword, hashtag, creator, and company pipeline in a
  live run before the session failure.
- Observed progressive workspace failures followed by two runs with 0/100
  refresh successes and no discovery results.
- Confirmed with a read-only feed probe that the saved session redirects to the
  LinkedIn login page.
- Identified missing `/signup/cold-join` and logged-out-layout detection, plus
  the absence of fail-fast behavior after authentication loss.
- Unloaded the three-hour LaunchAgent. No automated refresh or discovery task
  is currently scheduled.
- Next action: harden authentication handling and resume only with conservative
  limits and a longer interval.

### 2026-09-24 — Repository agent guidance added

- Added `AGENTS.md` with project memory, safety, architecture, and verification
  rules.
- Added one focused repository skill for LinkedIn collector development.
- Kept the instructions small and routed detailed project state to this living
  progress document.

### 2026-09-24 — Living project handoff created

- Audited the current project structure and integration path.
- Documented all four discovery sources, orchestration, parsing, persistence,
  source attribution, refresh, ranking, diagnostics, dashboard, and scheduling.
- Recorded experimental components and known operational gaps separately.
- Ran the complete mocked test suite: 70 tests passed.

### 2026-09-23 — Company source discovery

- Added isolated company source discovery.
- Added deterministic company posts URL generation using structured parsing.
- Added company source validation and login/checkpoint detection.
- Reused the shared scroller and candidate collector.
- Added graceful empty and unsupported-page behavior.
- Added mocked company-source tests without running live collection.

### Entry template

```markdown
### YYYY-MM-DD — Short feature name

- What changed.
- Important design decision.
- Tests/checks run and their results.
- Remaining limitation or next action.
```
