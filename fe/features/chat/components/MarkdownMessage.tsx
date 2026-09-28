"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="prose prose-sm sm:prose-base max-w-none dark:prose-invert prose-p:my-2.5 prose-p:first:mt-0 prose-p:last:mb-0 prose-p:leading-relaxed prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-foreground prose-h1:font-serif prose-h2:font-serif prose-pre:rounded-xl prose-pre:border prose-pre:border-border prose-pre:bg-muted/60 prose-pre:text-foreground prose-pre:shadow-xs prose-code:before:content-none prose-code:after:content-none prose-code:font-mono prose-code:bg-muted prose-code:text-brand dark:prose-code:text-brand-secondary prose-code:rounded-md prose-code:px-1.5 prose-code:py-0.5 prose-code:text-xs prose-blockquote:rounded-r-xl prose-blockquote:border-l-2 prose-blockquote:border-brand prose-blockquote:bg-brand/5 prose-blockquote:py-1.5 prose-blockquote:px-4 prose-blockquote:not-italic prose-blockquote:text-muted-foreground prose-th:border-b prose-th:border-border prose-th:font-medium prose-th:text-xs prose-th:text-muted-foreground prose-td:border-b prose-td:border-border/50 prose-a:text-brand hover:prose-a:text-brand-secondary prose-a:font-medium prose-a:underline-offset-4">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
