# CLAUDE.md — Frontend (fe/)

Guidance for working with the Next.js frontend in this repository. For full project context, see the root-level `CLAUDE.md`.

## 📂 Frontend Structure

```
fe/
├── app/              → Next.js App Router (page routes)
├── components/       → React components
│   ├── ui/          → UI primitives (buttons, inputs, etc.)
│   ├── editor/      → Document editor integration
│   └── onlyoffice/  → OnlyOffice embedded viewer
├── features/        → Feature-specific logic
│   └── chat/        → Chat feature (store, types)
├── services/        → API clients & utilities
│   ├── mock/        → Mock services for development
│   ├── chat.sse.ts  → SSE client for streaming events
│   └── endpoints.ts → API base config
├── hooks/           → Custom React hooks
├── lib/             → Utilities
│   └── documents/   → Document manipulation
├── types/           → TypeScript type definitions
└── public/          → Static assets
```

## 🎯 Key Components & Files

### Chat Feature (`fe/features/chat/`)
- **`store.ts`** — Zustand store for chat state (conversations, messages, UI state)
- **`types.ts`** — Chat type definitions (Message, Conversation, StreamEvent)

### Services
- **`chat.sse.ts`** — SSE client that subscribes to `GET /api/v1/conversations/{id}/stream` and emits events
- **`endpoints.ts`** — API client with base URL and auth headers
- **`mock/mockChatService.ts`** — In-memory mock for testing without backend

### UI Components
- Standard component library in `components/ui/` (built with Radix & Tailwind)
- Editor integration: `components/editor/` for document editing
- OnlyOffice viewer: `components/onlyoffice/`

---

## 🚀 Development Commands

```bash
# Development server (auto-reload)
pnpm dev
# → Open http://localhost:3000

# Build for production
pnpm build

# Production server
pnpm start

# Lint code
pnpm lint

# Type check (via TypeScript)
pnpm tsc --noEmit
```

---

## 🔄 Chat Flow (Frontend Perspective)

### 1. User sends message
- User types in chat input → calls `store.sendMessage(text)`
- Message is optimistically added to store (UI updates immediately)

### 2. Subscribe to stream
- Once request is sent, frontend calls `chat.sse.ts` to subscribe to `GET /api/v1/conversations/{id}/stream`
- SSE opens WebSocket-like connection, awaits `data: <JSON>\n\n` events

### 3. Handle events
- `services/chat.sse.ts` parses each SSE event (type: "message.delta", "message.done", etc.)
- Updates Zustand store in real-time as chunks arrive
- UI re-renders automatically (React reactivity)

### 4. Event types to handle
See `features/chat/types.ts` for full list. Common ones:
- `message.started` — Agent started processing
- `message.delta` — Text chunk received
- `message.done` — Agent finished, full message available
- `error` — Error occurred

---

## 📦 Key Dependencies

- **`next@16`** — React framework with SSR, API routes, file-based routing
- **`@tanstack/react-query@5`** — Server state management (replaced SWR)
- **`zustand@5`** — Client state (store.ts)
- **`zod@4`** — Schema validation for type-safe API responses
- **`tailwindcss@4`** — Utility CSS with dark mode support
- **`axios@1.19`** — HTTP client
- **`dayjs@1.11`** — Date formatting
- **`quill@2.0`** — Rich text editor
- **`html-to-docx@1.8`**, **`mammoth@1.12`** — Document conversion

---

## 🎨 Styling & Theme

- **Tailwind CSS v4** with custom config
- **Dark mode**: Implemented via `next-themes` provider
- **UI components**: Radix UI primitives styled with Tailwind

### Adding Dark Mode Support

Components should use Tailwind's `dark:` prefix:
```tsx
<div className="bg-white dark:bg-slate-900">...</div>
```

---

## 🧪 Testing the Chat Flow

### Option 1: With Backend Running
```bash
# Terminal 1: Start backend
cd core && python main.py

# Terminal 2: Start frontend
cd fe && pnpm dev
```

### Option 2: With Mock Service
Edit `fe/services/chat.sse.ts` or use `services/mock/mockChatService.ts` for:
- Offline development
- Testing without agent service running
- Predictable test data

---

## 📝 Common Frontend Tasks

### Adding a New Chat UI Component
1. Create file in `components/ui/ComponentName.tsx`
2. Use Tailwind for styling, export from `components/ui/index.ts` if it's a shared primitive
3. Compose in page or feature components

### Updating Chat Store
1. Edit `features/chat/store.ts` (Zustand actions)
2. Add types to `features/chat/types.ts` if needed
3. Use `const { conversations, sendMessage } = useChatStore()` in components

### Handling a New Stream Event
1. Add to `ConversationStreamEvent` type in `features/chat/types.ts`
2. Update handler in `services/chat.sse.ts` to dispatch to store
3. Update Zustand store action to handle the event

---

## 🔗 Integration with Backend

**SSE Subscription URL**: `GET /api/v1/conversations/{conversation_id}/stream`

**Request Format**:
```http
GET /api/v1/conversations/abc123/stream
Accept: text/event-stream
```

**Response Format** (Server-Sent Events):
```
data: {"type": "message.started", "timestamp": "2026-08-30T..."}

data: {"type": "message.delta", "data": "The recommended treatment..."}

data: {"type": "message.done", "id": "msg_xyz"}
```

---

## 🐛 Debugging

### Check SSE Connection
```tsx
// In browser DevTools → Network tab
// Filter by "Type: fetch" or "Type: event-stream"
// Open the request to see real-time events as they arrive
```

### Zustand DevTools Integration
```bash
# Use browser Redux DevTools extension to inspect store mutations
pnpm add zustand-devtools --save-dev
```

### Console Logging
- Add `console.log()` in `services/chat.sse.ts` to debug incoming events
- Add logging in store.ts actions to trace state updates

---

## 📖 See Also

- Root `CLAUDE.md` for full stack architecture
- `API_Contract.md` for complete API specification
- `fe/README.md` for Next.js specifics
- `fe/docs/backend-contract.md` for API endpoint reference

