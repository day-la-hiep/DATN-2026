import { Hint } from "@/components/ui/hint";
import { MarkdownMessage } from "@/features/chat/components/MarkdownMessage";

export function AiSummaryView({ summary }: { summary: string }) {
  return (
    <section className="space-y-2 px-4 pb-4">
      <Hint side="left" content="Tóm tắt và nhận định do AI tổng hợp từ hội thoại. Chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa.">
        <h4 className="w-fit font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
          Nhận định AI <span className="text-brand">· gợi ý</span>
        </h4>
      </Hint>
      <div className="rounded-xl border border-brand/20 bg-brand/[0.03] p-3.5">
        <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-xs prose-headings:font-semibold prose-p:text-[12px] prose-p:leading-relaxed prose-li:text-[12px] prose-li:leading-relaxed prose-strong:text-foreground prose-h2:text-sm prose-h2:mt-3 prose-h2:mb-1.5 prose-h3:text-xs prose-h3:mt-2 prose-h3:mb-1 prose-ol:my-1 prose-ul:my-1">
          <MarkdownMessage content={summary} />
        </div>
      </div>
    </section>
  );
}
