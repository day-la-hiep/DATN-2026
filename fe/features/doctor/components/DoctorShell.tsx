"use client";

import { ListTree, MessageSquareText, Stethoscope } from "lucide-react";
import { usePathname } from "next/navigation";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";

const NAV: ShellNavItem[] = [
  { href: "/doctor", label: "Ca tư vấn", hint: "Xem báo cáo AI và hội thoại", icon: MessageSquareText, exact: true },
  { href: "/doctor/documents", label: "Số hóa sách giáo khoa", hint: "Chuẩn bị tri thức cho trợ lý AI", icon: ListTree },
];

export function DoctorShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <AppShell brandLabel="Bác sĩ" brandIcon={Stethoscope} navTitle="Khu bác sĩ" nav={NAV} fullBleed={pathname === "/doctor"}>
      {children}
    </AppShell>
  );
}
