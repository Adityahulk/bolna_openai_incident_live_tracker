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

## Technical Deep Dive

### Architecture Overview

- Single-process watcher that pulls the OpenAI Status summary endpoint (`/api/v2/summary.json`).
- Event-like behavior using HTTP caching primitives rather than fixed-interval polling.
- Output goes to STDOUT (and in Docker, appended persistently to `/data/openai-status.log`).

### Event-Like Strategy (HTTP Caching)

- Conditional GET:
  - Sends `If-None-Match` with the last `ETag` and `If-Modified-Since` with the last `Last-Modified`.
  - If the server has no changes, it returns `304 Not Modified` with no body. The watcher sleeps and does not print.
  - When a change exists, the server returns `200 OK` with fresh JSON; the watcher processes and prints updates.
  - Code: `status_watcher.py:25`–`status_watcher.py:43`, check for `304`: `status_watcher.py:187`–`status_watcher.py:193`.

- Adaptive interval:
  - Reads `Cache-Control: max-age=<n>` to determine how long to sleep before the next conditional request.
  - Adds small jitter to avoid synchronized requests across many watchers.
  - Code: parse header `status_watcher.py:14`–`status_watcher.py:23`, sleep logic `status_watcher.py:259`–`status_watcher.py:261`.

### Printing Rules

- Component status changes:
  - When a component transitions to a non-operational status (e.g., `degraded_performance`, `partial_outage`), print the product name and latest relevant incident update text if available.
  - Code: `status_watcher.py:219`–`status_watcher.py:233`.

- New incident updates:
  - Each incident update has a unique ID. The watcher keeps a set of seen update IDs to avoid repeating old messages.
  - On a new update, print one line per affected component with the update text.
  - Code: selection `status_watcher.py:233`–`status_watcher.py:258`, seeding seen IDs `status_watcher.py:201`–`status_watcher.py:207`.

### State Management

- ETag/Last-Modified: Stored in local variables in the loop and passed as conditional headers.
- `SEEN` set: Holds incident update IDs already printed to prevent duplicate output.
  - Initialization and use: `status_watcher.py:277`–`status_watcher.py:283`, `status_watcher.py:201`–`status_watcher.py:207`, `status_watcher.py:248`–`status_watcher.py:258`.
- Previous component status: Maintains a map of component ID to last seen status to detect changes.
  - Code: `status_watcher.py:219`–`status_watcher.py:233`.

### Error Handling and Backoff

- If an HTTP error occurs, the watcher sleeps with a backoff, honoring `Retry-After` when provided.
- Code: `status_watcher.py:263`–`status_watcher.py:270`.

### Scaling to 100+ Providers

- Why this scales:
  - Conditional requests mean zero payload transfer when nothing changes.
  - Adaptive sleep respects each provider’s suggested cadence.
  - Jitter prevents synchronized load spikes.

- Async multiplexing (optional enhancement):
  - Use `asyncio` + `aiohttp` to manage a list of status endpoints.
  - Keep per-URL state: last `ETag`, last `Last-Modified`, seen update IDs, and previous component statuses.
  - Bound concurrency per host, honor `Retry-After`, and maintain jitter per URL.
  - The printing logic remains identical; only the transport becomes async.

- Webhooks/SSE:
  - Some providers offer webhooks; when available, consume them to achieve true push events.
  - This watcher is already efficient in the absence of webhooks.
