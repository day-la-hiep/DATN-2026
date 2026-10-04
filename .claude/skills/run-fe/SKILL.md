---
name: run-fe
description: Run, start, drive, and screenshot the Derma frontend (Next.js app in `fe/`, chat UI at /chats + admin book-ingest UI at /admin/documents, talks to core on :3050). Use when asked to run the frontend, start the Next dev server, check a UI change, screenshot a page, or verify fe talks to the real backend (not mock data).
---

# Run `fe` (Next.js)

All paths below are relative to `fe/`. There is no custom driver script: this is a
browser-driven web app, no `chromium-cli` binary is installed in this environment, so the
driver is the `claude-in-chrome` MCP browser tools (`navigate` + `computer` screenshot +
`read_network_requests`) — verified working below.

## Prerequisites

- Node (`node -v` — verified with v24.18.0) + pnpm (`pnpm -v` — verified with 11.9.0).
- `.env.local` (copy `.env.local.example`). Key vars actually in use:
  `NEXT_PUBLIC_API_URL=http://localhost:3050/api/v1`, `BACKEND_URL=http://localhost:3050`,
  `NEXT_PUBLIC_USE_MOCK=false` (true uses fake localStorage data instead of core — check this
  first if a page looks right but data looks canned).
- `core` backend running and reachable on :3050 (see `.claude/skills/run-core/`) — the chat
  page and `/admin/documents` both fetch real data from it.

## Setup

```bash
pnpm install   # already present in this repo — node_modules populated, skip if so
```

## Run (agent path)

```bash
# 1. dev server (skip if curl already answers — port 3000 is often the user's own dev server, reuse it, don't kill it)
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
pnpm dev > /tmp/fe.log 2>&1 &
timeout 30 bash -c 'until curl -sf http://localhost:3000 >/dev/null; do sleep 1; done'
```

Drive it with the `claude-in-chrome` MCP tools (load them first if deferred:
`ToolSearch("select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__tabs_close_mcp")`):

```
tabs_context_mcp(createIfEmpty: true)         # -> tabId
navigate(tabId, url: "http://localhost:3000/chats")   # MUST be http:// explicitly — a bare
                                                        # host defaults to https:// and hits
                                                        # "Frame ... showing error page" (no TLS here)
computer(action: "screenshot", tabId, save_to_disk: true)
navigate(tabId, url: "http://localhost:3000/admin/toc")
computer(action: "screenshot", tabId, save_to_disk: true)
tabs_close_mcp(tabId)                         # clean up when done
```

Verified 2026-10-03 against the live dev server: `/chats` renders the chat UI with real
conversation history ("Da mặt bị mụn trứng cá nên chăm sóc..."); `/admin/documents` renders the
book-ingest admin UI with two real books (Fitzpatrick's Color Atlas, FritzPatrick Clinical
Disease) and their stage progress — i.e. both pages are pulling live data from `core`, not
`NEXT_PUBLIC_USE_MOCK` fixtures.

Logs -> `/tmp/fe.log`. Stop: `lsof -ti:3000 -sTCP:LISTEN | xargs -r kill` (only if you started
it — don't kill a dev server you didn't launch).

## Lint (fastest smoke check — no server needed)

```bash
pnpm lint
```

Verified: exits with only pre-existing `@typescript-eslint/no-unused-vars` warnings in
`services/mock/mockChatService.ts` (0 errors) — treat new errors here as a real regression.

## Build

```bash
pnpm build
```

Not run in this verification pass (dev server + lint already proved the app renders); run
this before trusting a production-path change (e.g. anything in `next.config.ts`).

## Run (human path)

`pnpm dev` -> opens on http://localhost:3000, auto-reloads on save. Ctrl-C to stop.

## Gotchas

- `navigate` with a bare `localhost:3000` (no scheme) defaults to **https://**, which this
  dev server doesn't serve — screenshot then fails with `Frame with ID 0 is showing error
  page`. Always pass `http://localhost:3000/...` explicitly.
- Port 3000 (and core's 3050) are frequently already running as the user's own dev servers —
  `curl` first; reuse rather than relaunch/kill.
- `NEXT_PUBLIC_USE_MOCK=true` makes the UI look fully functional from localStorage alone with
  no backend running — if verifying an integration change, check this env var is `false` and
  that `core` is actually up, or the test proves nothing.
