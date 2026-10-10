import { Hint } from "@/components/ui/hint";
import type { PatientProfile } from "../types";

export function PatientInfoCard({ patient, reason }: { patient: PatientProfile; reason: string }) {
  const dob = patient?.dob ? new Date(patient.dob).toLocaleDateString("vi-VN") : "Chưa cập nhật";
  const gender = patient?.gender === "female" ? "Nữ" : "Nam";

  return (
    <div className="space-y-1">
      <Hint side="left" content={`Ngày sinh: ${dob}`}>
        <p className="w-fit text-sm font-semibold text-foreground">
          {patient?.fullName ?? "Chưa rõ"} <span className="font-normal text-muted-foreground">· {gender}</span>
        </p>
      </Hint>
      <Hint side="left" content={`Lý do tư vấn: ${reason || "chưa ghi"}`}>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{reason}</p>
      </Hint>
    </div>
  );
}
