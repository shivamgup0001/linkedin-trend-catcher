---
name: linkedin-collector-development
description: Implement or revise LinkedIn discovery, navigation, scrolling, candidate collection, parsing, canonical URL, or direct-refresh behavior in this repository. Use for collector-facing changes; do not use for dashboard-only, analytics-only, or documentation-only tasks.
---

# LinkedIn Collector Development

Use this workflow to change collection behavior without coupling discovery,
parsing, and persistence or accidentally contacting LinkedIn.

## Establish the contract

Read only the relevant parts of `PROJECT_PROGRESS.md`, then inspect the target
module, its closest sibling implementation, and its tests.

Keep these boundaries:

- Source adapters validate a `DiscoverySource`, navigate, wait, scroll, and
  return a Playwright `Locator` of unparsed candidates.
- Shared navigation, authentication-page detection, and candidate-loading
  behavior belongs in `collector/source_page.py` when more than one adapter
  needs it.
- `LinkedInCollector` identifies candidate elements.
- `LinkedInParser` extracts post data and resolves canonical URLs.
- `main.py` orchestrates sources, isolates failures, records diagnostics, and
  applies per-source candidate limits.
- `MongoDB` owns identity promotion, attribution, and persistence.

Do not move parsing or database writes into source adapters.

## Implement safely

- Preserve the public `load_candidates(page, source) -> Locator` adapter
  contract.
- Reuse the existing scroller and candidate collector.
- Use `urllib.parse` for URLs and validate LinkedIn host/path structure.
- Detect login and checkpoint redirects after navigation and after a timed-out
  workspace wait, because redirects may complete late.
- Treat legitimate empty results as data, not failures.
- Surface unsupported layouts through existing source status/diagnostics so the
  orchestrator can isolate the failed source.
- Preserve canonical identity and multi-source attribution behavior.

Do not run a browser, live collection, or real database write unless the user
explicitly asks for that operation. Mocked Playwright and database tests are the
default verification path.

## Verify and hand off

Add or update focused tests for the behavior being changed. Cover validation,
deterministic URLs, expired sessions, successful candidates, and empty or
unsupported pages when relevant.

Run focused tests first, then:

```bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/linkedin_trend_catcher_pycache python3 -m compileall -q .
```

Update `PROJECT_PROGRESS.md` when the change affects capabilities, architecture,
test totals, known gaps, or next steps. In the final handoff, state whether the
result is mocked-only, database-integrated, or live-verified.
