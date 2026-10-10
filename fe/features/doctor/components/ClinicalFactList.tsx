import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { FACT_TYPE_CONFIG } from "../constants";
import type { ClinicalFact } from "../types";

export function ClinicalFactList({ facts }: { facts: ClinicalFact[] }) {
  if (!facts || facts.length === 0) return null;

  return (
    <section className="space-y-2 px-4 pb-4">
      <h4 className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
        Dữ kiện <span className="text-brand">{facts.length}</span>
      </h4>
      <ul className="space-y-1.5">
        {facts.map((fact) => {
          const cfg = FACT_TYPE_CONFIG[fact.factType] ?? FACT_TYPE_CONFIG.other;
          const Icon = cfg.icon;
          return (
            <li key={fact.id}>
              <Hint
                side="left"
                content={
                  <div className="space-y-1">
                    <p className="font-medium">{cfg.label}: {fact.templateLabel}</p>
                    <p>{fact.detail}</p>
                    <p className="text-muted-foreground">{cfg.hint}</p>
                  </div>
                }
              >
                <div className="flex items-start gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-muted/60">
                  <span className={cn("mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border", cfg.colorClass)}>
                    <Icon className="size-3" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium text-foreground">{fact.templateLabel}</span>
                    <span className="line-clamp-1 block text-[11px] text-muted-foreground">{fact.detail}</span>
                  </span>
                </div>
              </Hint>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
