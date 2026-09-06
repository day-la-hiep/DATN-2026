"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1.5 prose-headings:my-2 prose-pre:rounded-lg prose-pre:border prose-pre:border-border prose-pre:bg-muted prose-pre:text-foreground prose-code:before:content-none prose-code:after:content-none prose-a:text-brand">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
