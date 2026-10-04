---
name: derma-pipeline-conventions
description: Conventions for the Derma document-ingest pipeline (`core/pipeline/document_ingest/` — PDF document → table-of-contents-anchored chunks → Qdrant, admin UI at /admin/documents) — the 4-stage model (ingest/toc/chunks/index), the StageContext contract, the `app/dto/base/document.py` business entities (`Document`/`DocumentChunk`/`ProcessStage`/`ProcessStageOverride`), where transformation logic vs infra clients vs persistence go, and how to add or modify a stage. Use whenever the user asks to add/modify a pipeline stage, touches `pipeline/document_ingest/`, `app/services/document_*.py`, `app/repositories/document_repository.py`, asks about document/book/TOC/chunk ingestion, or asks where document-ingest code should live — even if they don't say "pipeline" or "convention".
---

# Derma document-ingest pipeline (`pipeline/document_ingest/`) — conventions

Paths are relative to `core/`. Turns an uploaded PDF (currently: textbooks, `Document.type ==
"book"`) into table-of-contents-anchored chunks in Qdrant, reviewed stage-by-stage by a human via
`/admin/documents` (FE: `derma-fe-conventions`'s `features/document-pipeline/`). No CLI — Core runs each stage
in a background thread; everything lives in Postgres (`documents`, `document_stages`,
`document_overrides`) + MinIO (`derma-documents` bucket) + Qdrant (`derma_document_chunks`), never
on local disk except a PDF scratch copy.

Renamed from `book_ingest`/`Book*` on 2026-10-04 (see migration
`20261004_6e7b779ba7c1_rename_book_entities_to_document.py`) once `app/dto/base/document.py`'s
`Document` entity became generic across upload types, not just books — see
`derma-core-conventions`'s `dto/base` section. `type="book"` is still the only type this pipeline
processes; other `Document.type` values (`image`, `video`, `other`) are plain chat attachments with
no pipeline.

```
PDF → ingest (text/page)  → toc (LLM reads TOC, human reviews) → mapping (rule-based offset+anchor) → chunks → index (Qdrant)
```

| Stage | Module | Output (in MinIO `document/<document_id>/`) | LLM |
|---|---|---|---|
| `ingest` | `stages/ingest.py` | `pages.jsonl` | no |
| `toc` | `stages/toc.py` + `mapping.py` | `toc.auto.json` (machine), `toc.json` (+ overrides + offset + anchor) | reads a few dozen TOC pages |
| `chunks` | `stages/chunks.py` | `chunks.jsonl`, `review/chunks.json` | no |
| `index` | `stages/index.py` (+ `DocumentService`) | `index.json` + points in Qdrant | no (local embedding) |

Stage order/deps live in `app/models/document_stage.py` (`STAGES`, `downstream()`) — the single
source of truth, shared by repository, runner, and API. `toc` does **not** depend on `ingest`:
reading the TOC only needs a handful of OCR'd pages, so a user can try it immediately without
waiting for the whole document. `mapping.py` (offset+anchor) is re-run on demand (`reapply`)
whenever the TOC changes or `pages.jsonl` becomes available — it's rule-based, cheap, no LLM.

States: `not_started → running → pending_review → approved`; `failed`/`cancelled` on error;
`stale` when an upstream stage reruns after this one already has a result. A stage only runs once
every dependency is `approved`.

## Business entities vs ORM vs wire DTO

Per `derma-core-conventions`'s `dto/base` rule, this pipeline has three layers for the same data,
and they are NOT the same class even when field sets overlap:

| Layer | Classes | Lives in |
|---|---|---|
| Business entity (source of truth) | `Document` (holds `source_file`/`ingested_file: File` + `chunks`), `DocumentChunk`, `ProcessStage`, `ProcessStageOverride`; `File` (shared, MinIO object: `file_name`, `storage_key`, `content_type`, `size`, `created_at`) | `app/dto/base/document.py`, `app/dto/base/file.py` |
| ORM / Postgres schema | `Document`, `DocumentStage`, `DocumentOverride` | `app/models/document.py` |
| API wire contract (snake_case, same-meaning fields named as in `dto/base`) | `DocumentOutput`, `DocumentSummary`, `StageOutput`, `ChunkListOutput` (response) / `DocumentSettings`, `TocUpdate`, `RunStageInput` (request) | `app/dto/response/document.py`, `app/dto/request/document.py` |

`DocumentService` builds the `dto/base` entity from the ORM row first (`_document()`,
`_process_stages()`), then maps entity → wire DTO (`_stage_output()`) before returning from an
endpoint — don't skip the entity step and build the wire DTO directly from the ORM row. The ORM
class is also literally named `Document`/`DocumentStage`/`DocumentOverride` (same names as the
entity layer, different module) — `app/services/document_service.py` doesn't import both at once,
so there's no clash there, but if a future change needs both in one file, alias the ORM import
(`from app.models.document import Document as DocumentOrm`).

## Three-layer split (this is the part people get wrong)

> User's own rule: "`pipeline/` chỉ tập trung logic xử lý/biến đổi dữ liệu" — pipeline is
> transformation logic ONLY. Everything else (clients, persistence, control flow) goes in `app/`.

| Layer | Owns | Lives in |
|---|---|---|
| **Transform** (pure-ish, takes `StageContext`, returns a summary dict) | read input → transform → write output via `ctx.files`/`ctx.meta`/`ctx.overrides`/`ctx.log`/`ctx.progress` | `pipeline/document_ingest/stages/{ingest,toc,chunks,index}.py`, `mapping.py` (rule-based offset+anchor, pure function `build_toc`), `hierarchy.py`, `textutil.py`, `profile.py` |
| **Infra clients** (generic, no document logic, one class per service) | MinIO (`app/infra/minio_client.py`), Qdrant (`qdrant_client.py`), LLM-returns-JSON (`llm_client.py`), Docling OCR (`docling_client.py`), embedding (`embedding_client.py`) | `app/infra/*_client.py` |
| **Persistence + control** | `DocumentRepository` (stateless — every method takes `document_id`; Postgres CRUD for `documents`/`document_stages`, file access via `files_for(document_id)`), `DocumentOverrideRepository` (override CRUD for `document_overrides`, composed as `DocumentRepository.overrides`), `DocumentService` (CRUD + chunk/Qdrant business logic, builds `dto/base` entities), `DocumentIngestPipelineService` (run/stop/approve/reapply, builds `StageContext`, owns the background threads) | `app/repositories/document_repository.py`, `app/repositories/document_override_repository.py`, `app/services/document_service.py`, `app/services/document_ingest_pipeline_service.py` |
| **API/DTO** | `/admin/documents/*` routes, Pydantic contracts | `app/api/document_api.py`, `app/dto/request/document.py`, `app/dto/response/document.py` |
| **Instance lifecycle** | `get_document_service()`, `get_document_ingest_pipeline_service()` — lazy singleton per process | `app/api/deps.py` |

A stage module only ever touches `ctx: StageContext` — it never imports `app.infra`/`app.services`
directly (the clients it needs arrive pre-built through the context). That's what keeps
`pipeline/` swappable/testable in isolation (tests use `MemoryMinio` + SQLite + in-memory Qdrant +
a fake embedder, no real service running — see Testing below).

## `StageContext` (`pipeline/document_ingest/stages/__init__.py`)

Every stage is a module with `run(ctx: StageContext) -> dict` (a summary dict shown to the
reviewer) and, if it supports re-applying overrides without an LLM call, `reapply(ctx) -> dict`.

- `ctx.document_id: str` / `ctx.files: FileStoreService` — the id and a `FileStoreService` already
  scoped to `document/<document_id>/` (`DocumentRepository.files_for`) — no stateful "handle" object,
  `DocumentIngestPipelineService.make_ctx()` builds these fresh per run.
- `ctx.meta() -> dict` / `ctx.overrides(stage_id) -> dict` — bound callables reading Postgres
  (`DocumentRepository.meta`/`DocumentOverrideRepository.get`) for this `document_id`.
- `ctx.profile: Profile` — this document's settings (`app/models/document_profile.py`).
- `ctx.llm` / `ctx.docling` / `ctx.embedding` / `ctx.vectors` — injected clients, `None` if not
  configured for this run; use `ctx.require_llm()` etc. to get-or-raise `StageError` with a
  reviewer-facing message.
- `ctx.local_pdf()` — materializes `source.pdf` to a local temp path for tools that need a real
  file (pdftotext, Docling, pypdf); cleaned up with the document.
- `ctx.progress(done, total, message)` — rate-limited (~2/s) write to `document_stages.progress`;
  also calls `ctx.check_cancel()`, so put it inside any loop you want Stop/cancel to interrupt.
- `ctx.log(message)` — appends to the stage's log (`logs/` in MinIO), shown in the UI's "xem log".
- Raise `StageError(msg)` for anything the reviewer can fix themselves (bad option, missing file) —
  shown verbatim in the UI. Anything else propagates as an unhandled exception → stage `failed`.

## Recipes

**Modify an existing stage** — edit the stage module only if the change is pure
transformation (parsing, chunking rule, mapping logic). If it needs a new external capability
(another LLM call shape, a new file format), add/extend the matching `app/infra/*_client.py`
first, thread it through `StageContext` (add the field in `stages/__init__.py`, wire it in
`DocumentIngestPipelineService.make_ctx()`), then use `ctx.require_x()` in the stage.

**Add a stage** — add an entry to `STAGES` in `app/models/document_stage.py` (id, title, `deps`,
`llm`, `outputs`) — this is what drives dependency gating and the UI stepper. Add
`pipeline/document_ingest/stages/<id>.py` with `run(ctx)` (+ `reapply(ctx)` if applicable). No
other registration needed — `DocumentIngestPipelineService` resolves the module by `importlib`
from the stage id.

**Add a document setting** — field in `Profile` (`app/models/document_profile.py`, Pydantic), read
it via `ctx.profile.<section>.<field>` in the stage; surface it in the settings UI
(`derma-fe-conventions`'s `features/document-pipeline/components/SettingsDialog.tsx` + `types.ts`).

**Add/change a `dto/base` field** (`Document`/`DocumentChunk`/`ProcessStage`/`ProcessStageOverride`)
— propose it and get user approval FIRST (`derma-core-conventions`'s `dto/base` gate), then update:
the entity in `app/dto/base/document.py` → the ORM model in `app/models/document.py` (new Alembic
migration) → `DocumentService`'s entity builders (`_document()`/`_process_stages()`) → the wire DTO
mapping (`_stage_output()`) → `app/dto/request|response/document.py` if the API shape changes.

**Add an admin-pipeline API field/endpoint** — DTO in `app/dto/request/document.py` (input) or
`app/dto/response/document.py` (output) → method on
`DocumentService`/`DocumentIngestPipelineService`/`DocumentRepository` (whichever owns that data)
→ route in `app/api/document_api.py` (all routes already sit behind `require_app_token`).
Mirror in FE's `features/document-pipeline/api.ts` + `hooks.ts` (see `derma-fe-conventions`).

## Storage layout (MinIO `document/<document_id>/`)

`source.pdf`, `page_img/p<N>.png` (whole-page renders for the admin page-preview, NOT extracted
embedded figures — see below), `pages.jsonl`, `toc.auto.json`, `toc.json`, `chunks.jsonl`,
`index.json`, `status.json`, `overrides/`, `review/`, `logs/`, `docling_parts/` (OCR checkpoint —
lets a killed `ingest` resume without re-OCRing finished pages). LLM cache: `_cache/llm/`. Chunks
are embedded locally (384-dim) and upserted into Qdrant collection `derma_document_chunks`
(`settings.QDRANT_DOCUMENT_COLLECTION`), payload carries `document_id`, part/section/topic, page,
`source_pdf`. Deleting a document deletes both the MinIO objects and the Qdrant points; rerunning
`index` replaces all of a document's points.

**No embedded-figure extraction**: `ingest`'s docling branch keeps only
`{heading, text, list, caption, table, toc}` labelled blocks (`stages/ingest.py`'s
`_BODY_LABELS`) — any `picture`/`figure` block Docling detects is dropped. If asked to add image
extraction, that's new work in `stages/ingest.py`'s docling branch (keep `picture` blocks, crop
and write to MinIO, e.g. `document/<document_id>/figures/`), not something already wired up.

## Concurrency & control flow

`run_stage` runs synchronously in the calling thread; the API's `start_stage` spawns a daemon
thread and returns immediately — FE polls `GET /documents/{id}` for progress (see
`derma-fe-conventions`'s `useDocument`/`useDocuments` polling). Each run gets its own
`threading.Event` for cancellation (`ctx.cancel`, checked via `ctx.check_cancel()`/`ctx.progress`).
If Core restarts mid-run, `_reconcile` in `DocumentIngestPipelineService` marks orphaned `running`
stages `failed` (no thread survives a process restart) so they can be retried; `ingest`'s
`docling_parts/` checkpoint means that retry doesn't re-OCR already-finished pages.
`document_stages`/`document_overrides` writes happen under a Postgres row lock (`FOR UPDATE`)
because Core and background stage threads write concurrently.

## Testing

`python -m unittest pipeline.document_ingest.tests.test_document_pipeline pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index`
— verified 2026-10-04, 37 tests pass. Uses `tests/memory_infra.py`'s `MemoryMinio` + a temp SQLite
file (in place of Postgres) + `QdrantClient(":memory:")` + a fake embedder — no real
MinIO/Postgres/Qdrant service needs to be running for these tests.

## Code style

Same as `derma-core-conventions` (Vietnamese comments explaining *why*, basic-mode pyright, async
I/O) — this pipeline lives inside `core/` and follows the same rules. Module docstrings here tend
to front-load the non-obvious design decision (e.g. `mapping.py`'s docstring explains the
offset/anchor algorithm before any code) — match that when adding a module. Stage-level prose
("sách", "cuốn sách") still refers to the book being processed — that's fine to leave as-is since
the pipeline genuinely only processes `type="book"` documents today; only identifiers (`book_id`,
`BookService`, table/route names) were renamed to `document_*`, not the descriptive Vietnamese text.
