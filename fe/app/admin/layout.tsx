import type { Metadata } from "next";
import { AdminShell } from "@/features/document-pipeline/components/AdminShell";

export const metadata: Metadata = {
  title: "Quản trị tài liệu | Derma AI",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
