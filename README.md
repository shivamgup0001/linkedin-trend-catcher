# LinkedIn Trend Catcher

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Set `MONGO_URI`, `DB_NAME`, and `COLLECTION_NAME` in `.env`. Configure discovery sources in `config/keywords.yaml`.

## Discovery Configuration

Discovery configuration supports keywords, hashtags, creators, and companies. Each enabled source runs sequentially through the same parsing, canonical-URL, persistence, and diagnostics pipeline.

```yaml
discovery:
  keywords:
    - value: SaaS
      enabled: true
  hashtags:
    - value: aiagents
      enabled: false
  creators:
    - name: Example Creator
      profile_url: https://www.linkedin.com/in/example/
      enabled: false
  companies:
    - name: Example Company
      page_url: https://www.linkedin.com/company/example/
      enabled: false
```

The legacy `keywords:` list remains supported during migration. Duplicate sources are removed in configuration order, hashtags may include an optional leading `#`, and creator/company entries require matching LinkedIn profile URLs.

## Run

```bash
python3 main.py
python3 main.py --mode discover
python3 main.py --mode refresh --headless
python3 main.py --mode discover --headless --max-candidates-per-source 30
```

The default `all` mode directly refreshes saved activity URLs and then searches for new posts. The first run opens a browser for manual LinkedIn login and saves the session in `data/auth`. Later runs can use `--headless`. Each run stores post metadata in the configured collection and engagement history in `post_snapshots`.

The ranking compares the current reading with the newest baseline that is at least one hour old. It weights gained reactions, comments, and reposts at 1, 3, and 5 points, then divides by elapsed hours. By default, it requires three weighted points of growth and a post age of no more than seven days. Configure these with `--min-window-hours`, `--min-growth`, and `--max-post-age-days`.

During discovery, the collector uses each post's Copy link to post action to obtain its canonical URL and activity ID. DOM extraction is used as a fallback. When LinkedIn exposes neither, it creates a deterministic fingerprint from the normalized author and post text. Activity URLs are refreshed directly. Fingerprinted posts can be compared when they reappear in search results, but cannot be revisited directly if they disappear from those results.

Each source is isolated: a failed source is recorded in `collection_runs` and later sources continue. Candidate processing defaults to 30 items per source. Post documents retain all keyword, hashtag, creator, and company origins in `discovery_sources` while keeping the legacy `keyword` field compatible.

## Dashboard

Run the read-only dashboard with the same MongoDB settings:

```bash
python3 -m streamlit run dashboard.py
```

The dashboard reads post metadata, `post_snapshots`, persisted `collection_runs`, and the active discovery configuration. It does not collect, refresh, or modify data. The Collection Health tab shows recent run counters, refresh outcomes, and bounded error details.

## macOS Scheduling

The included launch agent runs one collection every three hours without keeping the Python process alive:

```bash
chmod +x scripts/run_once.sh
cp scheduler/com.linkedin-trend-catcher.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.linkedin-trend-catcher.plist
```

Logs are written to `/tmp/linkedin-trend-catcher.log` and `/tmp/linkedin-trend-catcher.error.log`. To remove the schedule:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.linkedin-trend-catcher.plist
```
