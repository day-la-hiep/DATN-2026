"use client";

import { ArrowLeft, ChevronRight, Loader2, Settings2 } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { EmptyState, StateBadge } from "@/features/document-pipeline/components/bits";
import { errorMessage, documentApi } from "@/features/document-pipeline/api";
import { ChunkBrowser } from "@/features/document-pipeline/components/ChunkBrowser";
import { FigureBrowser } from "@/features/document-pipeline/components/FigureBrowser";
import { PagePreview } from "@/features/document-pipeline/components/PagePreview";
import { hasRunOptions, RunDialog } from "@/features/document-pipeline/components/RunDialog";
import { SettingsDialog } from "@/features/document-pipeline/components/SettingsDialog";
import { StageLogDialog } from "@/features/document-pipeline/components/StageLogDialog";
import { StagePanel } from "@/features/document-pipeline/components/StagePanel";
import { TocEditor } from "@/features/document-pipeline/components/TocEditor";
import { STEP_INFO, STEP_ORDER } from "@/features/document-pipeline/constants";
import { useDocument, useData, useStageActions } from "@/features/document-pipeline/hooks";
import type { Document, Stage, StepId, TocEntry } from "@/features/document-pipeline/types";

const HAS_RESULT = ["pending_review", "approved", "stale"];

/** Một dòng tóm tắt dưới tên bước trên thanh các bước. */
function stepLine(stage: Stage): string {
  const s = stage.summary ?? {};
  if (stage.state === "running") return stage.progress?.message || "đang xử lý";
  if (!HAS_RESULT.includes(stage.state)) return "chưa có kết quả";
  if (stage.stage_id === "ingest") return `${s.pages ?? "?"} trang`;
  if (stage.stage_id === "toc") return `${s.entries ?? "?"} mục`;
  if (stage.stage_id === "chunks") return `${s.chunks ?? "?"} đoạn`;
  return `${s.points ?? "?"} đoạn đã lưu`;
}

function Stepper({ doc, step, onPick }: { doc: Document; step: StepId; onPick: (s: StepId) => void }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" aria-label="Các bước xử lý">
      {STEP_ORDER.map((id, i) => {
        const stage = doc.stages.find((s) => s.stage_id === id) as Stage;
        const Icon = STEP_INFO[id].icon;
        const active = id === step;
        return (
          <li key={id} className="relative">
            <button
              type="button"
              onClick={() => onPick(id)}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex w-full cursor-pointer items-center gap-3 rounded-2xl border p-3 text-left transition-colors",
                active ? "border-brand/50 bg-brand/5" : "border-border bg-card hover:border-brand/30"
              )}
            >
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-xl",
                  stage.state === "approved" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground",
                  active && stage.state !== "approved" && "bg-brand/10 text-brand"
                )}
              >
                <Icon className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">{i + 1}</span>
                  <span className="truncate text-sm font-semibold tracking-tight text-foreground">{STEP_INFO[id].label}</span>
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{stepLine(stage)}</span>
              </span>
              <StateBadge state={stage.state} />
            </button>
            {i < STEP_ORDER.length - 1 && (
              <ChevronRight className="pointer-events-none absolute top-1/2 -right-2.5 z-10 hidden size-4 -translate-y-1/2 text-muted-foreground sm:block" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function defaultStep(doc: Document): StepId {
  if (doc.running_stage) return doc.running_stage;
  return STEP_ORDER.find((id) => doc.stages.find((s) => s.stage_id === id)?.state !== "approved") ?? "chunks";
}

export default function TocDocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = use(params);
  const documentQuery = useDocument(documentId);
  const { run, cancel, approve } = useStageActions(documentId);
  const [picked, setPicked] = useState<StepId | null>(null);
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [logStage, setLogStage] = useState<StepId | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const data = documentQuery.data;
  const tocStage = data?.stages.find((s) => s.stage_id === "toc");
  const tocReady = Boolean(tocStage && HAS_RESULT.includes(tocStage.state));
  const toc = useData(documentId, "toc", {}, () => documentApi.toc(documentId), tocReady);

  if (documentQuery.isError) {
    return (
      <EmptyState
        title="Không mở được sách"
        hint={errorMessage(documentQuery.error)}
        action={
          <Button variant="outline" asChild>
            <Link href="/doctor/documents">Về danh sách</Link>
          </Button>
        }
      />
    );
  }
  if (!data) return <Skeleton className="h-96 rounded-2xl" />;

  const step = picked ?? defaultStep(data);
  const stage = data.stages.find((s) => s.stage_id === step) as Stage;
  const hasResult = HAS_RESULT.includes(stage.state);
  const busy = run.isPending || cancel.isPending || approve.isPending;
  const runningName = data.running_stage ? STEP_INFO[data.running_stage].label : null;
  const nextStep = STEP_ORDER[STEP_ORDER.indexOf(step) + 1];

  const selected = toc.data?.entries.find((e) => e.id === selectedId) ?? null;
  const page = previewPage ?? selected?.page ?? (step === "toc" ? toc.data?.toc_pages[0] : undefined) ?? 1;
  const caption =
    step === "toc" && selected ? (
      <>
        <span className="font-medium text-foreground">{selected.title}</span> · trang in {selected.page_printed ?? "—"}
        {selected.page != null && selected.page === page && (
          <>
            {" "}→ trang {selected.page} trong file · {selected.anchored ? "đã định vị" : "chưa định vị"}
          </>
        )}
      </>
    ) : step === "toc" && toc.data?.toc_pages.includes(page) ? (
      "Trang mục lục"
    ) : undefined;

  const pick = (s: StepId) => {
    setPicked(s);
    setPreviewPage(null);
  };
  const onSelectEntry = (e: TocEntry) => {
    setSelectedId(e.id);
    setPreviewPage(e.page ?? null);
  };
  const startRun = () => (hasRunOptions(step) ? setRunOpen(true) : run.mutate({ stage: step }));

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <Link href="/doctor/documents" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-3.5" /> Sách
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate font-serif text-2xl font-bold tracking-tight text-foreground">{data.title}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
              <span>{documentId}</span>
              {data.pdf_pages != null && <span>{data.pdf_pages} trang</span>}
              {runningName && (
                <span className="inline-flex items-center gap-1 text-brand">
                  <Loader2 className="size-3 animate-spin" /> đang xử lý: {runningName}
                </span>
              )}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
            <Settings2 /> Cài đặt
          </Button>
        </div>
      </div>

      <Stepper doc={data} step={step} onPick={pick} />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="min-w-0 space-y-4">
          <StagePanel
            stage={stage}
            busy={busy}
            anotherRunning={Boolean(data.running_stage) && data.running_stage !== step}
            onRun={startRun}
            onCancel={() => cancel.mutate(step)}
            onApprove={() => approve.mutate(step)}
            onLog={() => setLogStage(step)}
            onNext={nextStep ? () => pick(nextStep) : undefined}
          />

          {step === "ingest" && hasResult && <FigureBrowser documentId={documentId} onPreview={(p) => setPreviewPage(p)} />}
          {step === "toc" &&
            (hasResult && toc.data ? (
              <TocEditor documentId={documentId} doc={toc.data} selectedId={selectedId} onSelect={onSelectEntry} onPreview={(p) => setPreviewPage(p)} />
            ) : (
              !["running"].includes(stage.state) && (
                <EmptyState
                  title="Chưa đọc mục lục"
                  hint="Nhấn Bắt đầu để AI đọc mục lục."
                />
              )
            ))}
          {step === "index" && !hasResult && stage.state !== "running" && (
            <EmptyState
              title="Chưa lưu vào kho tri thức"
              hint="Làm sau khi đã xác nhận Chia đoạn."
            />
          )}
          {step === "chunks" &&
            (hasResult ? (
              <ChunkBrowser documentId={documentId} toc={toc.data} previewPage={page} onPreview={(p) => setPreviewPage(p)} />
            ) : (
              stage.state !== "running" && (
                <EmptyState title="Chưa có đoạn nội dung" hint="Làm sau khi đã xác nhận Đọc nội dung và Mục lục." />
              )
            ))}
        </div>

        {data.source_file && (
          <div className="h-[32rem] xl:sticky xl:top-6 xl:h-[calc(100vh-3rem)]">
            <PagePreview
              documentId={documentId}
              page={page}
              total={data.pdf_pages}
              caption={caption}
              highlightLine={selected && selected.page === page && selected.anchored ? selected.anchor_line : null}
              onPage={setPreviewPage}
            />
          </div>
        )}
      </div>

      <RunDialog
        key={`${step}-${runOpen}`}
        stage={stage}
        open={runOpen}
        onOpenChange={setRunOpen}
        pending={run.isPending}
        onRun={(options) => {
          setRunOpen(false);
          run.mutate({ stage: step, options });
        }}
      />
      <StageLogDialog documentId={documentId} stage={logStage} running={data.running_stage === logStage} onClose={() => setLogStage(null)} />
      <SettingsDialog documentId={documentId} open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
