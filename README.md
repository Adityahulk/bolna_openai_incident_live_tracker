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


## Troubleshooting

- No output in continuous mode usually means there are no changes; verify with `--once` to see the next planned check.
- Use `--bootstrap-log` to print current non-operational components at startup.
- Check network connectivity and ensure Python can reach `status.openai.com`.