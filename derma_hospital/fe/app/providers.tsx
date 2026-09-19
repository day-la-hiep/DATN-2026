"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { AccessGate } from "./access-gate";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <TooltipProvider>
        <AccessGate>{children}</AccessGate>
        <Toaster position="top-center" richColors />
      </TooltipProvider>
    </ThemeProvider>
  );
}
