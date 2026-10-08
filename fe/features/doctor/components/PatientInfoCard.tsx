import type { PatientProfile } from "../types";

interface PatientInfoCardProps {
  patient: PatientProfile;
  reason: string;
}

export function PatientInfoCard({ patient, reason }: PatientInfoCardProps) {
  const formattedDob = new Date(patient.dob).toLocaleDateString("vi-VN");

  return (
    <div className="rounded-xl border border-border bg-card/80 p-3 shadow-xs">
      <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
        Thông tin bệnh nhân
      </p>
      <div className="grid grid-cols-2 gap-y-1.5 gap-x-3 text-xs">
        <div>
          <span className="text-muted-foreground">Họ tên:</span>{" "}
          <span className="font-medium text-foreground">{patient.fullName}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Giới:</span>{" "}
          <span className="font-medium text-foreground">
            {patient.gender === "male" ? "Nam" : "Nữ"}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Ngày sinh:</span>{" "}
          <span className="font-medium text-foreground">{formattedDob}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Lý do:</span>{" "}
          <span className="font-medium text-foreground line-clamp-1">{reason}</span>
        </div>
      </div>
    </div>
  );
}
