import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Báo cáo tư vấn bác sĩ | Derma AI",
  description: "Màn hình bác sĩ xem báo cáo AI kết luận từ hội thoại với bệnh nhân",
};

export default function DoctorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
