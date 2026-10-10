---
name: derma-fe-conventions
description: Conventions for the Derma `fe/` frontend (Next.js App Router) — folder layout (`app/` vs `features/` vs `services/` vs `components/ui/`), the two state patterns in use (Zustand store for chat/SSE, TanStack Query hooks for the admin document-ingest pipeline), and the step-by-step way to add a page, a feature, a UI primitive, an SSE event type, or an admin-pipeline endpoint. Use whenever the user asks to add or modify a component, page, store, API call, hook, or SSE event in `fe/`, asks where frontend code should live, or how data flows from a Next.js page down to the backend — even if they don't say "convention".
---

# Derma `fe/` — layout and conventions

Paths are relative to `fe/`. To run/drive/screenshot the app, use `/run-fe`. Two unrelated
features live side by side with **different state patterns** — pick the one that matches
what you're touching, don't mix them.

`fe/CLAUDE.md` is stale (references `@tanstack/react-query` as if unused everywhere, `quill`/
`html-to-docx`/`mammoth` deps that aren't in `package.json`, and an old flat `services/`-only
structure) — trust this skill and the code over it.

## Layout

| Path | Owns | Must not |
|---|---|---|
| `app/` | Next.js App Router routes only (`page.tsx` = thin, imports a feature component) | hold business logic or API calls |
| `app/providers.tsx` | app-wide providers: `ThemeProvider`, `TooltipProvider`, `AccessGate`, `Toaster` | |
| `app/access-gate.tsx` | login gate: shows `features/auth` `AuthScreen` until a JWT is stored (see Gotchas) | |
| `components/ui/` | shadcn primitives (`components.json`: style `new-york`, baseColor `neutral`) — generated/edited via shadcn conventions | hold feature-specific logic |
| `features/<name>/` | one folder per feature: `types.ts`, `api.ts` (axios calls + `unwrap`), `hooks.ts` (TanStack Query) or `store.ts` (Zustand), `constants.ts`, `components/` | import another feature's internals directly (go through its exported hooks/store) |
| `services/` | cross-feature infra: `client.ts` (axios singleton + auth interceptor), `endpoints.ts` (chat REST paths), `chat.sse.ts` (SSE client, implements `ChatService`), `apiAdapters.ts` (wire ↔ domain mapping), `index.ts` (mock/real `ChatService` factory), `mock/` | be feature-specific business logic |
| `hooks/` | generic cross-feature hooks (e.g. `use-mobile.ts`) | feature-specific hooks (those go in `features/<name>/hooks.ts`) |
| `lib/utils.ts` | `cn()` (clsx+tailwind-merge), `formatRelativeTime`, `formatBytes` | |
| `types/` | ambient `.d.ts` for untyped packages (e.g. `html-to-docx.d.ts`) | domain types (those go in `features/<name>/types.ts`) |

Path alias: `@/*` → repo root (`fe/`), e.g. `@/components/ui/button`, `@/features/chat/store`.

## Two state patterns — pick per feature

**Chat (`features/chat/`)** — one large Zustand store (`store.ts`, ~800 lines, not split into
slices) that calls `chatService` (`services/index.ts`, swaps between `chatSse` and
`mockChatService` on `NEXT_PUBLIC_USE_MOCK`) directly from store actions, and subscribes to SSE
via `chatService.onEvent()`. No TanStack Query here — the store *is* the cache, because SSE
pushes deltas that must mutate specific message/reasoning-step objects in place, which doesn't
fit a query-invalidation model. Components read via `useChatStore()` selectors.

**Admin / document-ingest (`features/document-pipeline/`)** — plain REST + TanStack Query. `api.ts`
exports one object (`documentApi`) of axios calls, each piped through `unwrap<T>()` (backend wraps
every response in `{ data: T }` — `ApiResponse[T]` on the Python side, see
`derma-core-conventions`). `hooks.ts` wraps each call in `useQuery`/`useMutation`, centralizes
query keys (`qk`), and polls (`refetchInterval`) while a pipeline stage is `running` instead of
needing a push channel. `useRefreshDocument` is the one place that invalidates — call it from every
mutation's `onSuccess`, don't invalidate ad hoc in components.

**Rule of thumb:** server pushes deltas you must splice into existing state in real time → a
Zustand store like chat's. Everything else (CRUD + polling) → TanStack Query hooks like
document-pipeline's.

## The chat SSE flow (frontend side)

```
store.sendMessage() → chatService.sendMessage() [services/chat.sse.ts]
  1. POST /conversations/{id}/messages → gets real userMessage + assistantMessage (status=queued) ids
  2. fires chatService._openStream() in the background (not awaited) → GET .../stream (SSE)
     → parses `data: <json>\n\n` frames → ChatStreamEvent → impl.listeners (store subscribed via onEvent)
store's onEvent handler switches on event.type (message.delta / reasoning.step_* / message.question /
  message.tool_result / message.done / document.*) and mutates messagesByConversation[conversationId] in place
```

Backend side of this flow (RabbitMQ/worker/Redis) is documented in `derma-core-conventions`; the
event `type` strings and payload shapes are the contract between the two — change
`features/chat/types.ts`'s `FlatStreamEvent` and the backend's `emit()` calls together. Note:
the **mock** service (`services/mock/mockChatService.ts`) does not emit every event the real one
does (e.g. no `message.tool_result`, uses `reasoning.step_completed` + `choice` instead of the
real `message.question`) — a UI change that only works against the mock will break against the
real backend; verify against both, or at least check `NEXT_PUBLIC_USE_MOCK=false` before calling
a chat UI change done (see `/run-fe`).

## Recipes

**Add a page/route** — folder+`page.tsx` under `app/` (App Router); keep it thin, just import
and render a component from the matching `features/<name>/components/`. `"use client"` at the
top of the feature component if it uses hooks/state (App Router defaults to server components).

**Add a feature** — new `features/<name>/` with `types.ts` (domain types), `api.ts` (axios calls
via `@/services/client`'s `api`, each response piped through an `unwrap<T>` like
`toc-pipeline/api.ts`'s), `hooks.ts` (TanStack Query wrapping `api.ts`) or `store.ts` (Zustand,
if it needs push-driven state), `components/` for its UI. Don't reach into another feature's
`store.ts`/`api.ts` internals from outside — export what's needed from `hooks.ts`/`store.ts`.

**Add a UI primitive** — shadcn convention: lives in `components/ui/`, styled with Tailwind
classes composed via `cn()` from `@/lib/utils`, variants via `class-variance-authority` (see
`components/ui/button.tsx` for the pattern). Icons from `lucide-react` (`components.json`
`iconLibrary`).

**Add a new SSE event type** — add the variant to `FlatStreamEvent` in `features/chat/types.ts`
(payload shape must match what the backend's `emit()` sends, see `derma-core-conventions`'s "Add
middleware"), handle it in the store's event switch (`features/chat/store.ts`), and update
`services/mock/mockChatService.ts` if the mock should simulate it too (chat UI dev often happens
against the mock first).

**Add an admin-pipeline endpoint** (`features/document-pipeline/`) — add the call to `documentApi` in
`api.ts` (through `unwrap<T>`), add a `useQuery`/`useMutation` wrapper in `hooks.ts` (mutations
call `useRefreshDocument(documentId)` in `onSuccess`, `toast.error(errorMessage(e))` in `onError`), use
the hook from a component in `components/`.

## Code style

- Path alias `@/*`, never deep relative imports (`../../../`) across feature boundaries.
- Comments are Vietnamese, explain *why* (a backend contract detail, a UI/race-condition
  reason), not what — match the surrounding file; see `services/chat.sse.ts` and
  `features/document-pipeline/api.ts` for the density expected. No long block comments at the top
  of a file or above a function/component (no JSDoc essays); one short line at most.
- `pnpm lint` (ESLint) should be clean of errors (pre-existing `no-unused-vars` warnings in
  `services/mock/mockChatService.ts` for intentionally-unused mock params are known-acceptable).
- Error messages shown to users go through a `errorMessage(e)`-style helper that prefers the
  backend's FastAPI `detail` field (see `features/document-pipeline/api.ts`) — don't show raw axios
  errors.

## Gotchas

- `NEXT_PUBLIC_USE_MOCK=true` makes the whole chat UI work from `localStorage` with zero backend
  calls — great for isolated UI work, but don't trust it to validate an integration change (see
  `/run-fe`).
- Auth is JWT login/register (`features/auth`, backend `/auth/*`): `app/access-gate.tsx` shows `AuthScreen` until `services/client.ts` has a token, which it attaches as `Authorization: Bearer` (interceptor clears it on 401). The server only issues tokens; chat/document routes do not require one yet. Conversations use the logged-in account's id (`getCurrentUserId()` in `services/client.ts`) as `user_id`; logout reloads the page so the chat store never leaks one account's data to the next.
- `services/chat.sse.ts` uses raw `fetch` + manual SSE frame parsing (`\n\n`-delimited `data:`
  lines), not `EventSource` — because it needs to send a custom `Authorization` header, which
  `EventSource` can't do.
- Binary downloads (page images, chunk export) go through axios with `responseType: "blob"` and
  `timeout: 0` (see `features/document-pipeline/api.ts`'s `pageImageUrl`/`exportChunks`) because they
  need the `Authorization` header too — a plain `<img src="...">`/`<a href="...">` can't attach it.
