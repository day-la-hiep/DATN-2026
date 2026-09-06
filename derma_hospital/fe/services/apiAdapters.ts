/**
 * Adapter: DTO trên wire của Core Backend (camelCase — mọi response DTO kế thừa
 * `CamelModel`, xem `core/app/dto/common.py`/`core/app/dto/message.py`/
 * `core/app/dto/conversation.py`) <-> model nội bộ của store Frontend.
 *
 * Store + component giữ nguyên `ChatMessage` phẳng; chỉ tầng service này biết cấu trúc
 * `metadata` đa hình của backend.
 */
import {
  MAX_ATTACHMENTS,
  MAX_SELECTIONS_TOTAL,
} from "@/features/chat/constants";
import type {
  ChatMessage,
  ChatRole,
  Conversation,
  MessageChoice,
  MessageStatus,
  ReasoningStep,
  ReasoningStepStatus,
  ReasoningStepType,
  SelectionSource,
  SendMessageInput,
} from "@/features/chat/types";

/* ----------------------------- Wire DTOs ----------------------------- */

export interface ApiConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ApiSelectionRef {
  /** backend `MessageSelectionRefDto.source` hiện chỉ nhận `"message"` — gửi
   * `"canvas"`/`"document"` sẽ bị 422 (tính năng canvas/document chưa có ở backend). */
  source: SelectionSource;
  refId: string;
  text: string;
  start?: number | null;
  end?: number | null;
}

export interface ApiFileAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
}

export interface ApiReasoningStep {
  id?: string | null;
  title?: string;
  content?: string;
  status?: string;
  type?: string;
  choice?: MessageChoice | null;
}

/** Khớp `MessageMetadataDto` (`core/app/dto/message.py`) — 1 shape dùng chung cho cả
 * message user lẫn assistant, field nào không áp dụng thì `undefined`. */
export interface ApiMessageMetadata {
  reasoning?: ApiReasoningStep[] | null;
  selectionRef?: ApiSelectionRef[] | null;
  attachments?: ApiFileAttachment[] | null;
  choice?: MessageChoice | null;
  isOptionResponse?: boolean | null;
}

export interface ApiChatMessage {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  metadata?: ApiMessageMetadata | null;
  createdAt: string;
}

/** Khớp `SendMessageInput` (`core/app/dto/message.py`) verbatim — không có
 * `metadata`/`answer`, `attachments`/`selection` nằm top-level. */
export interface ApiSendMessageBody {
  clientMessageId: string;
  content: string;
  modelId?: string;
  attachments?: ApiFileAttachment[];
  selection?: ApiSelectionRef | ApiSelectionRef[];
}

/* ----------------------------- Mappers ------------------------------ */

export function toConversation(a: ApiConversation): Conversation {
  return {
    id: a.id,
    title: a.title ?? "",
    createdAt: a.createdAt,
    updatedAt: a.updatedAt ?? a.createdAt,
  };
}

export function toChatMessage(a: ApiChatMessage): ChatMessage {
  const role: ChatRole = a.role === "user" ? "user" : "assistant";
  const meta = a.metadata ?? undefined;

  const reasoning: ReasoningStep[] | undefined = meta?.reasoning
    ? meta.reasoning.map((s, i) => ({
        id: s.id ?? `${a.id}-step-${i + 1}`,
        title: s.title ?? "Suy luận",
        content: s.content ?? "",
        status: (s.status as ReasoningStepStatus) ?? "done",
        type: (s.type as ReasoningStepType) ?? "default",
        choice: s.choice ?? undefined,
      }))
    : undefined;

  return {
    id: a.id,
    conversationId: a.conversationId,
    role,
    content: a.content ?? "",
    createdAt: a.createdAt,
    // Giữ nguyên status thật từ backend ("question"/"pending"/"queued"...) — KHÔNG
    // hard-code "done", để UI khôi phục đúng trạng thái khi F5 giữa chừng 1 turn.
    status: a.status,
    reasoning,
    choice: meta?.choice ?? undefined,
    isOptionResponse: meta?.isOptionResponse ?? undefined,
    selectionRef:
      role === "user" && meta?.selectionRef
        ? meta.selectionRef.map((r) => ({
            source: r.source ?? "message",
            refId: r.refId,
            text: r.text,
            start: r.start ?? undefined,
            end: r.end ?? undefined,
          }))
        : undefined,
    attachments: role === "user" ? meta?.attachments ?? undefined : undefined,
  };
}

export function toSendMessageBody(input: SendMessageInput): ApiSendMessageBody {
  const selection = input.selection
    ? Array.isArray(input.selection)
      ? input.selection
      : [input.selection]
    : undefined;

  const selectionRef: ApiSelectionRef[] | undefined = selection
    ?.slice(0, MAX_SELECTIONS_TOTAL)
    .map((s) => ({
      source: s.source,
      refId: s.refId,
      text: s.text,
      start: s.start,
      end: s.end,
    }));

  const attachments: ApiFileAttachment[] | undefined = input.attachments
    ?.slice(0, MAX_ATTACHMENTS)
    .map((x) => ({ id: x.id, name: x.name, size: x.size, type: x.type }));

  return {
    // Backend yêu cầu `clientMessageId` bắt buộc — store hiện chỉ set `corrId`, fallback
    // sang đó để không phải sửa mọi call site.
    clientMessageId: input.clientMessageId ?? input.corrId,
    content: input.content,
    modelId: input.modelId,
    attachments,
    selection: selectionRef,
  };
}
