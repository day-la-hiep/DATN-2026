import { CircleDot } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ClinicalFact } from "../types";
import { FACT_TYPE_CONFIG } from "../constants";

interface ClinicalFactListProps {
  facts: ClinicalFact[];
}

export function ClinicalFactList({ facts }: ClinicalFactListProps) {
  if (facts.length === 0) return null;

  return (
    <div className="px-4 pb-3">
      <div className="flex items-center gap-2 mb-2.5">
        <CircleDot className="size-3 text-brand" />
        <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground font-semibold">
          Dữ kiện lâm sàng trích xuất ({facts.length})
        </p>
      </div>
      <div className="space-y-2">
        {facts.map((fact) => {
          const cfg = FACT_TYPE_CONFIG[fact.factType];
          const Icon = cfg.icon;
          return (
            <div
              key={fact.id}
              className={cn(
                "rounded-lg border p-2.5 transition-all hover:shadow-xs",
                cfg.colorClass
              )}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <Icon className="size-3" />
                <span className="text-[10px] font-semibold uppercase tracking-wide">
                  {cfg.label}
                </span>
              </div>
              <p className="text-xs font-medium leading-snug">
                {fact.templateLabel}
              </p>
              <p className="text-[11px] leading-relaxed mt-0.5 opacity-85">
                {fact.detail}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
