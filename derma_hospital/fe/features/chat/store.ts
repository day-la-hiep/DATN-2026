"use client";

import { create } from "zustand";
import { chatService } from "@/services";
import { MODEL_OPTIONS } from "./constants";
import type {
  ChatMessage,
  ChatStreamEvent,
  Conversation,
  FileAttachment,
  MessageChoice,
  MessageSelectionRef,
  ReasoningStep,
} from "./types";

function generateId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const MAX_SAVED_TITLE_LENGTH = 50;

import type { SkillOption } from "./constants";

export interface ConversationInputState {
  value: string;
  selectedSkill: SkillOption | null;
  files: FileAttachment[];
  pendingSelection: MessageSelectionRef | MessageSelectionRef[] | null;
}

export const DEFAULT_INPUT_STATE: ConversationInputState = {
  value: "",
  selectedSkill: null,
  files: [],
  pendingSelection: null,
};

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  messagesByConversation: Record<string, ChatMessage[]>;
  /** số luồng AI đang chạy theo từng hội thoại -> cho phép gửi song song */
  activeStreams: Record<string, number>;
  /** Quản lý trạng thái khung nhập (draft text, skill, files, pendingSelection) theo từng conversationId */
  inputsByConversation: Record<string, ConversationInputState>;
  connected: boolean;
  loadingConversations: boolean;
  loadingMessages: boolean;
  initialized: boolean;
  selectedModelId: string;

  init: () => Promise<void>;
  /** Vào trạng thái "hội thoại mới" (chưa tạo record); tạo thật khi gửi tin đầu tiên */
  startNewChat: () => void;
  selectConversation: (id: string) => Promise<void>;
  setModel: (modelId: string) => void;
  /** Lấy input state hiện tại của hội thoại */
  getInputState: (convId?: string | null) => ConversationInputState;
  /** Cập nhật input state cho hội thoại */
  setInputState: (
    convId: string | null,
    patch: Partial<ConversationInputState>
  ) => void;
  sendMessage: (
    content: string,
    options?: {
      attachments?: FileAttachment[];
      selection?: MessageSelectionRef | MessageSelectionRef[];
    }
  ) => void;
  /** Lưu bản chỉnh sửa văn bản soạn sẵn (canvas) vào message + database */
  updateDocument: (
    messageId: string,
    content: string,
    isCanvas?: boolean
  ) => Promise<void>;
  /** Người dùng chọn hoặc tự nhập phương án cho câu hỏi agent đưa ra */
  answerChoice: (
    messageId: string,
    answer: { optionId: string; label: string; custom?: boolean }
  ) => void;
  hasActiveStream: (conversationId: string) => boolean;
}

function normalizeStreamEvent(rawEvent: ChatStreamEvent): import("./types").FlatStreamEvent {
  if ("metadata" in rawEvent && rawEvent.metadata) {
    const envelope = rawEvent as import("./types").ConversationStreamEvent;
    const clientMessageId = envelope.corr_id ?? "";
    const messageId = envelope.message_id ?? "";
    const conversationId = envelope.conversation_id;
    const meta = envelope.metadata;
    const status = meta.status;

    if (status === "message.started") {
      return {
        type: "message.started",
        corrId: clientMessageId,
        clientMessageId,
        conversationId,
        messageId,
      };
    }
    if (status === "message.steered") {
      return {
        type: "message.steered",
        corrId: clientMessageId,
        conversationId,
        messageId,
        content: meta.content,
      };
    }
    if (status === "message.delta") {
      return {
        type: "message.delta",
        messageId,
        conversationId,
        delta: meta.content,
      };
    }
    if (status === "message.done") {
      return {
        type: "message.done",
        messageId,
        conversationId,
      };
    }
    if (status === "reasoning.step_started") {
      const rMeta = meta as import("./types").ReasoningMetadata;
      return {
        type: "reasoning.step_started",
        messageId,
        conversationId,
        stepId: rMeta.stepId ?? `${messageId}-step-1`,
        title: rMeta.title,
        stepType: rMeta.stepType ?? (rMeta.toolMetadata?.name === "ask_tool" ? "tool_call" : "default"),
        choice: rMeta.choice,
      };
    }
    if (status === "reasoning_step_delta") {
      const rMeta = meta as import("./types").ReasoningMetadata;
      return {
        type: "reasoning.step_delta",
        messageId,
        conversationId,
        stepId: rMeta.stepId ?? `${messageId}-step-1`,
        delta: rMeta.content,
      };
    }
    if (status === "reasoning.step_completed") {
      const rMeta = meta as import("./types").ReasoningMetadata;
      return {
        type: "reasoning.step_completed",
        messageId,
        conversationId,
        stepId: rMeta.stepId ?? `${messageId}-step-1`,
        stepType: rMeta.stepType,
        choice: rMeta.choice,
      };
    }
  }

  return rawEvent as import("./types").FlatStreamEvent;
}

export const useChatStore = create<ChatState>((set, get) => {
  function patchMessage(
    messageId: string,
    patch: (message: ChatMessage) => ChatMessage
  ) {
    set((state) => {
      const messagesByConversation = { ...state.messagesByConversation };
      for (const convId of Object.keys(messagesByConversation)) {
        const list = messagesByConversation[convId];
        const index = list.findIndex((m) => m.id === messageId);
        if (index === -1) continue;
        const next = [...list];
        next[index] = patch(next[index]);
        messagesByConversation[convId] = next;
        return { messagesByConversation };
      }
      return state;
    });
  }

  function handleEvent(rawEvent: ChatStreamEvent) {
    const event = normalizeStreamEvent(rawEvent);
    switch (event.type) {
      case "message.queued": {
        set((state) => {
          const messagesByConversation = { ...state.messagesByConversation };
          for (const convId of Object.keys(messagesByConversation)) {
            const list = messagesByConversation[convId];
            const index = list.findIndex((m) => m.id === event.corrId);
            if (index === -1) continue;
            const next = [...list];
            next[index] = { ...next[index], id: event.messageId, status: "queued" };
            messagesByConversation[convId] = next;
            return { messagesByConversation };
          }
          return state;
        });
        break;
      }
      case "message.started": {
        set((state) => {
          const messagesByConversation = { ...state.messagesByConversation };
          for (const convId of Object.keys(messagesByConversation)) {
            const list = messagesByConversation[convId];
            const index = list.findIndex((m) => m.id === event.corrId || m.id === event.messageId);
            if (index === -1) continue;
            const next = [...list];
            next[index] = { ...next[index], id: event.messageId, status: "streaming" };
            messagesByConversation[convId] = next;
            return { messagesByConversation };
          }
          return state;
        });
        break;
      }
      case "reasoning.step_started": {
        const step: ReasoningStep = {
          id: event.stepId,
          title: event.title,
          content: "",
          status: "processing",
          type: event.stepType ?? "default",
          choice: event.choice,
        };
        const isToolAsk = step.type === "tool_call" || step.type === "tool_ask" || !!event.choice;

        patchMessage(event.messageId, (m) => {
          const list = m.reasoning ?? [];
          const exists = list.some((s) => s.id === step.id);
          const updated = exists
            ? list.map((s) => (s.id === step.id ? { ...s, ...step, choice: step.choice ?? s.choice } : s))
            : [...list, step];

          const stepChoice = event.choice || step.choice;
          const nextChoice = stepChoice ? { ...(m.choice || {}), ...stepChoice } : m.choice;
          const nextStatus = (isToolAsk || !!nextChoice) ? "question" : m.status;

          return {
            ...m,
            status: nextStatus,
            choice: nextChoice,
            reasoning: updated,
          };
        });

        if (isToolAsk && event.choice) {
          set((state) => ({
            activeStreams: {
              ...state.activeStreams,
              [event.conversationId]: Math.max(
                0,
                (state.activeStreams[event.conversationId] ?? 0) - 1
              ),
            },
          }));
        }
        break;
      }
      case "reasoning.step_delta": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          reasoning: (m.reasoning ?? []).map((step) =>
            step.id === event.stepId
              ? { ...step, content: `${step.content}${event.delta}` }
              : step
          ),
        }));
        break;
      }
      case "reasoning.step_completed": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          reasoning: (m.reasoning ?? []).map((step) =>
            step.id === event.stepId
              ? {
                  ...step,
                  status: "done",
                  choice: event.choice
                    ? { ...step.choice, ...event.choice }
                    : step.choice,
                }
              : step
          ),
          choice:
            event.choice && m.choice
              ? { ...m.choice, ...event.choice }
              : m.choice,
        }));
        break;
      }
      case "message.delta": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          content: `${m.content}${event.delta}`,
        }));
        break;
      }
      case "message.steered": {
        set((state) => {
          const messagesByConversation = { ...state.messagesByConversation };
          for (const convId of Object.keys(messagesByConversation)) {
            const list = messagesByConversation[convId];
            const index = list.findIndex((m) => m.id === event.corrId);
            if (index === -1) continue;

            const next = [...list];
            const exists = next.some((m) => m.id === event.messageId);
            if (!exists) {
              const userSteerMsg: ChatMessage = {
                id: event.messageId,
                conversationId: convId,
                role: "user",
                content: event.content,
                status: "done",
                createdAt: new Date().toISOString(),
                isOptionResponse: true,
              };
              next.splice(index, 0, userSteerMsg);
            }
            messagesByConversation[convId] = next;
            return { messagesByConversation };
          }
          return state;
        });
        break;
      }
      case "message.done": {
        patchMessage(event.messageId, (m) => {
          const existingList = m.reasoning ?? [];
          const incomingList = event.reasoning ?? [];

          if (incomingList.length === 0) {
            return { ...m, status: "done" };
          }

          const existingMap = new Map(existingList.map((s) => [s.id, s]));
          const mergedList: ReasoningStep[] = incomingList.map((incStep) => {
            const exStep = existingMap.get(incStep.id);
            if (!exStep) return incStep;

            const baseChoice = incStep.choice || exStep.choice;
            const mergedChoice: MessageChoice | undefined = baseChoice
              ? {
                  questionId: incStep.choice?.questionId || exStep.choice?.questionId || "",
                  question: incStep.choice?.question || exStep.choice?.question || "",
                  options: incStep.choice?.options || exStep.choice?.options || [],
                  answered: incStep.choice?.answered || exStep.choice?.answered,
                }
              : undefined;

            return {
              ...exStep,
              ...incStep,
              type: incStep.type || exStep.type || (mergedChoice ? "tool_call" : "default"),
              choice: mergedChoice,
            };
          });

          // Giữ lại các bước đã tồn tại nếu chưa có trong incomingList
          const incomingMap = new Map(incomingList.map((s) => [s.id, s]));
          for (const exStep of existingList) {
            if (!incomingMap.has(exStep.id)) {
              mergedList.push(exStep);
            }
          }

          return {
            ...m,
            status: "done",
            reasoning: mergedList,
          };
        });
        set((state) => ({
          activeStreams: {
            ...state.activeStreams,
            [event.conversationId]: Math.max(
              0,
              (state.activeStreams[event.conversationId] ?? 0) - 1
            ),
          },
          conversations: state.conversations.map((c) =>
            c.id === event.conversationId
              ? { ...c, updatedAt: new Date().toISOString() }
              : c
          ),
        }));
        break;
      }
      case "document.started": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          document: {
            id: event.documentId,
            title: event.title,
            content: "",
          },
        }));
        break;
      }
      case "document.delta": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          document: m.document
            ? { ...m.document, content: `${m.document.content}${event.delta}` }
            : m.document,
        }));
        break;
      }
      case "document.done": {
        patchMessage(event.messageId, (m) => ({
          ...m,
          document: event.document ?? m.document,
        }));
        break;
      }
    }
  }

  return {
    conversations: [],
    activeId: null,
    messagesByConversation: {},
    activeStreams: {},
    inputsByConversation: {},
    connected: false,
    loadingConversations: false,
    loadingMessages: false,
    initialized: false,
    selectedModelId: MODEL_OPTIONS[0].id,

    getInputState(convId) {
      const key = convId ?? get().activeId ?? "new";
      return get().inputsByConversation[key] ?? DEFAULT_INPUT_STATE;
    },

    setInputState(convId, patch) {
      const key = convId ?? get().activeId ?? "new";
      set((s) => {  
        const current = s.inputsByConversation[key] ?? DEFAULT_INPUT_STATE;
        const next = { ...current, ...patch };
        return {
          inputsByConversation: {
            ...s.inputsByConversation,
            [key]: next,
          },
        };
      });
    },

    async init() {
      if (get().initialized) return;
      set({ loadingConversations: true });

      try {
        await chatService.connect();
        set({ connected: true });
      } catch (error) {
        console.warn("Không kết nối được service, tiếp tục ở chế độ offline", error);
        set({ connected: false });
      }

      chatService.onEvent(handleEvent);

      try {
        const conversations = await chatService.getConversations();
        const first = conversations[0];
        set({
          conversations,
          activeId: first?.id ?? null,
          initialized: true,
          loadingConversations: false,
        });
        if (first) {
          await get().selectConversation(first.id);
        }
      } catch (error) {
        console.error("Không tải được danh sách hội thoại", error);
        set({ loadingConversations: false, initialized: true });
      }
    },

    startNewChat() {
      set({ activeId: null });
    },

    async selectConversation(id) {
      const state = get();
      if (state.messagesByConversation[id]) {
        set({ activeId: id });
        return;
      }
      set({ activeId: id, loadingMessages: true });
      try {
        const messages = await chatService.getMessages(id);
        set((s) => ({
          messagesByConversation: { ...s.messagesByConversation, [id]: messages },
          loadingMessages: false,
        }));
      } catch (error) {
        console.error("Không tải được tin nhắn", error);
        set({ loadingMessages: false });
      }
    },

    setModel(modelId) {
      set({ selectedModelId: modelId });
    },

    sendMessage(content, options) {
      const trimmed = content.trim();
      if (!trimmed) return;

      // chưa có hội thoại (trạng thái "hội thoại mới") -> tạo record trước,
      // rồi gửi tin đầu tiên vào hội thoại vừa tạo
      if (!get().activeId) {
        const newChatDraft = get().getInputState("new");
        void (async () => {
          try {
            const conversation = await chatService.createConversation({
              userId: "user-1",
              // Không seed initMessage ở đây — sendMessage bên dưới sẽ gửi tin
              // đầu tiên (tránh trùng lặp user message ở turn đầu).
              initMessage: "",
              title: trimmed.slice(0, MAX_SAVED_TITLE_LENGTH),
            });
            set((s) => ({
              conversations: [conversation, ...s.conversations],
              activeId: conversation.id,
              messagesByConversation: {
                ...s.messagesByConversation,
                [conversation.id]: [],
              },
              inputsByConversation: {
                ...s.inputsByConversation,
                [conversation.id]: newChatDraft,
                new: DEFAULT_INPUT_STATE,
              },
            }));
            get().sendMessage(content, options);
          } catch (error) {
            console.error("Không tạo được hội thoại mới", error);
          }
        })();
        return;
      }

      const { activeId, activeStreams, selectedModelId } = get();
      if (!activeId) return;

      const attachments = options?.attachments?.length
        ? options.attachments
        : undefined;
      const selection = options?.selection;

      // Reset input state cho conversation này sau khi bấm gửi
      get().setInputState(activeId, DEFAULT_INPUT_STATE);

      const nowIso = new Date().toISOString();
      const userMessage: ChatMessage = {
        id: `user-${generateId()}`,
        conversationId: activeId,
        role: "user",
        content: trimmed,
        attachments,
        selectionRef: selection,
        createdAt: nowIso,
        status: "done",
      };
      const clientMessageId = generateId();
      const assistantMessage: ChatMessage = {
        id: clientMessageId,
        conversationId: activeId,
        role: "assistant",
        content: "",
        createdAt: nowIso,
        status: "streaming",
      };

      set((state) => {
        const currentList = state.messagesByConversation[activeId] ?? [];
        const isStreaming = (activeStreams[activeId] ?? 0) > 0;
        const nextList = [...currentList];

        if (isStreaming) {
          // If streaming, find the active assistant message and insert steer userMessage BEFORE it
          const asstIdx = nextList.findIndex(
            (m) => m.role === "assistant" && m.status !== "done"
          );
          if (asstIdx !== -1) {
            nextList.splice(asstIdx, 0, userMessage);
          } else {
            nextList.push(userMessage);
          }
        } else {
          // New turn: append userMessage and assistantMessage
          nextList.push(userMessage, assistantMessage);
        }

        return {
          messagesByConversation: {
            ...state.messagesByConversation,
            [activeId]: nextList,
          },
          activeStreams: {
            ...state.activeStreams,
            [activeId]: (activeStreams[activeId] ?? 0) + 1,
          },
          conversations: state.conversations.map((c) => {
            const shouldRename = c.id === activeId && !c.title.trim();
            return {
              ...c,
              updatedAt: nowIso,
              title: shouldRename
                ? trimmed.slice(0, MAX_SAVED_TITLE_LENGTH)
                : c.title,
            };
          }),
        };
      });

      Promise.resolve(
        chatService.sendMessage({
          conversationId: activeId,
          corrId: clientMessageId,
          clientMessageId,
          content: trimmed,
          modelId: selectedModelId,
          attachments,
          selection,
        })
      ).catch(() => {
        console.error("Gửi tin nhắn thất bại");
        patchMessage(clientMessageId, (m) => ({
          ...m,
          status: "done",
          content: m.content || "Đã có lỗi khi gửi yêu cầu, vui lòng thử lại.",
        }));
        set((state) => ({
          activeStreams: {
            ...state.activeStreams,
            [activeId]: Math.max(
              0,
              (state.activeStreams[activeId] ?? 0) - 1
            ),
          },
        }));
      });
    },

    answerChoice(messageId, answer) {
      const state = get();
      let target: ChatMessage | undefined;
      let convId = "";
      for (const [cid, list] of Object.entries(state.messagesByConversation)) {
        const found = list.find((m) => m.id === messageId);
        if (found) {
          target = found;
          convId = cid;
          break;
        }
      }
      if (!target?.choice || target.choice.answered) return;

      let answerLabelText = answer.label;
      if (answer.optionId === "skip") {
        answerLabelText = "Bỏ qua";
      } else if (answer.custom) {
        answerLabelText = `${answer.label} (Tự nhập)`;
      }

      const answeredObj = { optionId: answer.optionId, label: answerLabelText, custom: answer.custom };

      // Đánh dấu câu trả lời đã chọn trực tiếp vào reasoning step & choice của tin nhắn assistant
      patchMessage(messageId, (m) => {
        const reasoningList = m.reasoning ?? [];
        const updatedReasoning = reasoningList.map((rs) =>
          rs.choice ? { ...rs, choice: { ...rs.choice, answered: answeredObj } } : rs
        );
        return {
          ...m,
          status: "streaming",
          isOptionResponse: true,
          content: "",
          reasoning: updatedReasoning,
          choice: m.choice ? { ...m.choice, answered: answeredObj } : undefined,
        };
      });

      const nowIso = new Date().toISOString();
      set((s) => ({
        activeStreams: {
          ...s.activeStreams,
          [convId]: (s.activeStreams[convId] ?? 0) + 1,
        },
        conversations: s.conversations.map((c) =>
          c.id === convId ? { ...c, updatedAt: nowIso } : c
        ),
      }));

      Promise.resolve(
        chatService.answerQuestion({
          conversationId: convId,
          questionId: target.choice.questionId,
          optionId: answer.optionId,
          label: answerLabelText,
          custom: answer.custom,
        })
      ).catch(() => {
        console.error("Gửi câu trả lời thất bại");
        patchMessage(messageId, (m) => ({
          ...m,
          status: "done",
          content: m.content || "Đã có lỗi khi gửi yêu cầu, vui lòng thử lại.",
        }));
        set((s) => ({
          activeStreams: {
            ...s.activeStreams,
            [convId]: Math.max(0, (s.activeStreams[convId] ?? 0) - 1),
          },
        }));
      });
    },

    async updateDocument(messageId, content, isCanvas) {
      const state = get();
      let target: ChatMessage | undefined;
      for (const list of Object.values(state.messagesByConversation)) {
        const found = list.find((m) => m.id === messageId);
        if (found) {
          target = found;
          break;
        }
      }
      if (!target?.document) return;

      const nextCanvas = isCanvas ?? target.document.isCanvas ?? false;
      patchMessage(messageId, (m) => ({
        ...m,
        document: {
          ...m.document!,
          content,
          isCanvas: nextCanvas,
        },
      }));

      try {
        await chatService.updateDocument({
          messageId,
          content,
          isCanvas: nextCanvas,
        });
      } catch (error) {
        console.error("Lưu văn bản thất bại", error);
      }
    },

    hasActiveStream(conversationId) {
      return (get().activeStreams[conversationId] ?? 0) > 0;
    },
  };
});
