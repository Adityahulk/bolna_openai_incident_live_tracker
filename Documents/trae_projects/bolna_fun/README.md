# OpenAI Status Watcher

Small, dependency-free Python script that efficiently tracks the OpenAI Status Page (`https://status.openai.com`) and prints new incident updates and component status changes to the console.

## Why This Is Efficient

- Uses HTTP conditional requests (`ETag`, `Last-Modified`) so the server replies `304 Not Modified` when nothing changed — no wasteful downloads.
- Honors `Cache-Control: max-age` from the server to adapt the sleep interval dynamically.
- Adds jitter to sleep times to avoid thundering herds when scaled across many status pages.

This approach is effectively event-like: you only re-fetch when the server signals a change, which scales well to 100+ providers, especially for those that do not offer webhooks or SSE.

## What It Prints

- On component status change or new incident update:
  - `[YYYY-MM-DD HH:MM:SS] Product: <component name>`
  - `Status: <latest incident update body or readable status>`

Example:

```
[2025-11-03 14:32:00] Product: OpenAI API - Chat Completions
Status: Degraded performance due to upstream issue
```

## Quick Start

Prerequisites: Python 3.8+.

Commands:

- One-shot check:
  - `python3 status_watcher.py --once`
- One-shot with initial logging of current non-operational components:
  - `python3 status_watcher.py --once --bootstrap-log`
- Continuous watch (recommended):
  - `python3 status_watcher.py --bootstrap-log`

Notes:

- Continuous mode sleeps based on `Cache-Control: max-age`. If there’s no change, the server may return `304 Not Modified` and the script remains quiet.
- You’ll only see output when a status changes or a new incident update appears.

## Making It Live

### macOS (launchd)

Run as a background service that starts at login and restarts automatically.

1. Create `~/Library/LaunchAgents/com.openai.statuswatcher.plist` with content:

```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.openai.statuswatcher</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/python3</string>
      <string>/Users/yourname/Documents/trae_projects/bolna_fun/status_watcher.py</string>
      <string>--bootstrap-log</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/yourname/Documents/trae_projects/bolna_fun</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PYTHONUNBUFFERED</key>
      <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/yourname/Library/Logs/openai-status.out</string>
    <key>StandardErrorPath</key>
    <string>/Users/yourname/Library/Logs/openai-status.err</string>
  </dict>
  </plist>
```

2. Load and start:

```
launchctl load -w ~/Library/LaunchAgents/com.openai.statuswatcher.plist
launchctl list | grep statuswatcher
```

3. View logs:

```
tail -f ~/Library/Logs/openai-status.out
```

### Linux (systemd)

Create `/etc/systemd/system/openai-status.service`:

```
[Unit]
Description=OpenAI Status Watcher

[Service]
WorkingDirectory=/opt/openai-status
ExecStart=/usr/bin/python3 /opt/openai-status/status_watcher.py --bootstrap-log
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and check logs:

```
sudo systemctl daemon-reload
sudo systemctl enable --now openai-status.service
journalctl -u openai-status.service -f
```

### Container/Cloud (optional)

Wrap in a tiny container to run anywhere. Example `Dockerfile`:

```
FROM python:3.11-slim
WORKDIR /app
COPY status_watcher.py ./
CMD ["python", "status_watcher.py", "--bootstrap-log"]
```

Run: `docker build -t openai-status . && docker run --rm openai-status`

## Internals

Core functions and responsibilities:

- `request_summary` performs conditional GETs and returns status/headers/body: `status_watcher.py:25`–`status_watcher.py:43`.
- `parse_max_age` extracts `max-age` from headers to set sleep interval: `status_watcher.py:14`–`status_watcher.py:23`.
- `run_loop` drives the continuous watcher, honoring `304` and `Cache-Control`: `status_watcher.py:180`–`status_watcher.py:270`.
- `latest_update_text_for_component` picks the most recent update text relevant to a component: `status_watcher.py:49`–`status_watcher.py:89`.
- `component_names_for_incident` maps incident payloads to component names: `status_watcher.py:91`–`status_watcher.py:114`.
- `main` handles CLI flags `--once` and `--bootstrap-log`: `status_watcher.py:272`–`status_watcher.py:287`.

Data source:

- Summary endpoint: `https://status.openai.com/api/v2/summary.json` (components + incidents).

Behavior details:

- On first run, it seeds a set of seen incident update IDs to avoid re-printing historical items.
- On each cycle, it:
  - Detects component status changes and prints non-operational changes using latest incident text when available.
  - Detects new incident updates (by ID) and prints one line per affected component.
  - Sleeps for `max-age` seconds (+/− jitter) or `Retry-After` on error.

## Scaling to 100+ Status Pages

- Keep the same strategy for other providers using their summary/JSON endpoints.
- Use an async loop (e.g., `aiohttp`) to multiplex requests while still sending conditional headers.
- Respect per-provider `max-age` and add jitter; avoid fixed polling intervals.
- If a provider offers webhooks, route webhook events to the same printing logic.

## Troubleshooting

- No output in continuous mode usually means there are no changes; verify with `--once` to see the next planned check.
- Use `--bootstrap-log` to print current non-operational components at startup.
- Check network connectivity and ensure Python can reach `status.openai.com`.