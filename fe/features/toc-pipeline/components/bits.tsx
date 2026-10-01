"use client";

import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { STATE_INFO } from "../constants";
import type { StageState } from "../types";

export function StateBadge({ state, className }: { state: StageState; className?: string }) {
  const info = STATE_INFO[state];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium whitespace-nowrap",
        info.tone,
        className
      )}
    >
      {state === "running" && <span className="size-1.5 rounded-full bg-brand animate-pulse" />}
      {info.label}
    </span>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 z-10 size-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? "Tìm..."}
        className="h-9 rounded-xl pl-9 text-xs"
      />
    </div>
  );
}

/** Nhóm nút lọc kiểu chip (một lựa chọn). */
export function Chips<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
            value === o.value
              ? "border-brand/40 bg-brand/10 text-brand"
              : "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          {o.label}
          {o.count !== undefined && (
            <span className="font-mono text-[10px] opacity-70 tabular-nums">{o.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
      <span className="tabular-nums">
        {total === 0 ? "0 mục" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} / ${total}`}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-xs" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Trang trước">
          <ChevronLeft />
        </Button>
        <span className="min-w-14 text-center tabular-nums">
          {page} / {pages}
        </span>
        <Button variant="outline" size="icon-xs" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Trang sau">
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border bg-card/40 px-6 py-14 text-center">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {hint && <p className="max-w-md text-xs leading-relaxed text-muted-foreground">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Lưới số liệu tóm tắt (key → value) cho summary của từng bước. */
export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data).filter(([, v]) => v !== null && v !== undefined);
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
      {rows.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="truncate text-[11px] text-muted-foreground">{humanKey(k)}</dt>
          <dd className="truncate font-mono text-xs text-foreground tabular-nums" title={formatValue(v)}>
            {formatValue(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function humanKey(k: string) {
  return /\s/.test(k) ? k : k.replace(/([A-Z])/g, " $1").toLowerCase();
}

function formatValue(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-border bg-card p-4 sm:p-5", className)}>
      {(title || action) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>}
            {description && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export const selectCls =
  "h-7 cursor-pointer rounded-lg border border-border bg-background px-2 text-[11px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
