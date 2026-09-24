# Repository Instructions

## Project memory

- Use `PROJECT_PROGRESS.md` for architecture, completed capabilities, known
  gaps, and next steps when the task affects product behavior or structure.
- After a meaningful feature, fix, or operational verification, update the
  relevant sections and append a dated progress-log entry.
- Do not load the entire progress file for trivial edits when the relevant code
  is already clear.

## Safety and scope

- Preserve the existing dirty worktree. Never discard unrelated user or agent
  changes.
- Do not print, commit, or expose `.env` values or LinkedIn session state under
  `data/auth/`.
- Unit tests are mocked and safe to run without approval.
- Do not run live LinkedIn collection, browser login, scheduler installation,
  or real MongoDB writes unless the user explicitly requests that operation.
- Keep collectors isolated: source collectors navigate and return candidate
  locators; parsing, persistence, diagnostics, and orchestration stay in their
  existing layers.

## Development conventions

- Reuse shared behavior in `collector/source_page.py`, existing scrolling, and
  `LinkedInCollector` instead of duplicating it.
- Build and validate URLs with `urllib.parse`; do not assemble user-provided
  URLs through unchecked string concatenation.
- Preserve per-source failure isolation and legacy keyword compatibility.
- Add mocked tests for success, validation, authentication expiry, empty data,
  and unsupported layouts when those cases apply.
- For collector, navigation, parser, canonical URL, or refresh changes, use the
  `linkedin-collector-development` repository skill.

## Verification

- Run focused tests while iterating, then run the full suite for behavior
  changes:

  ```bash
  python3 -m unittest discover -s tests -v
  ```

- Run compilation with a sandbox-safe cache when Python files change:

  ```bash
  PYTHONPYCACHEPREFIX=/tmp/linkedin_trend_catcher_pycache python3 -m compileall -q .
  ```

- Report what was tested and clearly distinguish mocked, database-integration,
  and live LinkedIn verification.
