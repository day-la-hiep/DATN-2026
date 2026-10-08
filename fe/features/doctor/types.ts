/**
 * Types cho màn hình bác sĩ — báo cáo tư vấn (consultation report).
 *
 * Map từ database schema: `consultation_sessions`, `pre_consultation_reports`,
 * `clinical_facts`, `clinical_fact_templates`, `patient_profiles`, `messages`.
 */

/* ────────── Patient Profile ────────── */

export interface PatientProfile {
  id: string;
  fullName: string;
  dob: string;
  gender: "male" | "female";
}

/* ────────── Clinical Facts ────────── */

export type ClinicalFactType =
  | "symptom"
  | "lesion"
  | "history"
  | "medication"
  | "allergy"
  | "image_finding"
  | "other";

export interface ClinicalFact {
  id: string;
  templateLabel: string;
  factType: ClinicalFactType;
  detail: string;
  status: "active" | "superseded";
  createdAt: string;
}

/* ────────── Pre-Consultation Report ────────── */

export interface PreConsultationReport {
  id: string;
  summary: string;
  createdAt: string;
}

/* ────────── Consultation Session ────────── */

export type ConsultationStatus = "pending" | "active" | "resolved";

export interface ConsultationSession {
  id: string;
  conversationId: string;
  conversationTitle: string;
  patient: PatientProfile;
  doctorId: string | null;
  status: ConsultationStatus;
  reason: string;
  requestedAt: string;
  startedAt: string | null;
  resolvedAt: string | null;
  report: PreConsultationReport | null;
  clinicalFacts: ClinicalFact[];
}

/* ────────── Chat Message (read-only cho bác sĩ) ────────── */

export interface DoctorViewMessage {
  id: string;
  conversationId?: string;
  sender: "patient" | "ai" | "doctor";
  content: string;
  messageType: string;
  createdAt: string;
  attachments?: { id: string; name: string; url?: string }[];
}
