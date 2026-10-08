import { FileText } from "lucide-react";
import { MarkdownMessage } from "@/features/chat/components/MarkdownMessage";

interface AiSummaryViewProps {
  summary: string;
}

export function AiSummaryView({ summary }: AiSummaryViewProps) {
  return (
    <div className="px-4 pb-4">
      <div className="flex items-center gap-2 mb-2.5">
        <FileText className="size-3 text-brand" />
        <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">
          Tóm tắt & Nhận định AI
        </p>
      </div>
      <div className="rounded-xl border border-brand/20 bg-brand/[0.02] dark:bg-brand/[0.05] p-3.5 shadow-xs">
        <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-xs prose-headings:font-semibold prose-p:text-[12px] prose-p:leading-relaxed prose-li:text-[12px] prose-li:leading-relaxed prose-strong:text-foreground prose-h2:text-sm prose-h2:mt-3 prose-h2:mb-1.5 prose-h3:text-xs prose-h3:mt-2 prose-h3:mb-1 prose-ol:my-1 prose-ul:my-1">
          <MarkdownMessage content={summary} />
        </div>
      </div>
    </div>
  );
}
