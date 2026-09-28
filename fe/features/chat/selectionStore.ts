import { create } from "zustand";
import type { MessageSelectionRef } from "./types";
import { useChatStore } from "./store";

interface SelectionState {
  /** đoạn bôi đen đầu tiên (giữ cho tương thích ngược) */
  pending: MessageSelectionRef | null;
  /** danh sách đoạn đang chờ hỏi — tối đa 1 / mỗi `source` (1 tin nhắn + 1 canvas) */
  pendingSelections: MessageSelectionRef[];
  setPending: (ref: MessageSelectionRef | null) => void;
  addPendingSelection: (ref: MessageSelectionRef) => void;
  removePendingSelection: (index: number) => void;
  clearPendingSelections: () => void;
}

function syncToInput(list: MessageSelectionRef[]) {
  const activeId = useChatStore.getState().activeId;
  useChatStore.getState().setInputState(activeId, { pendingSelection: list });
}

export const useSelectionStore = create<SelectionState>((set, get) => ({
  pending: null,
  pendingSelections: [],
  setPending: (ref) => {
    const list = ref ? [ref] : [];
    set({ pending: ref, pendingSelections: list });
    syncToInput(list);
  },
  /** Thêm / thay thế đoạn trích dẫn cho `source` tương ứng (tối đa 1 mỗi loại). */
  addPendingSelection: (ref) => {
    const others = get().pendingSelections.filter((r) => r.source !== ref.source);
    // giữ thứ tự: tin nhắn trước, canvas sau
    const next = [...others, ref].sort((a, b) =>
      a.source === b.source ? 0 : a.source === "message" ? -1 : 1
    );
    set({ pending: next[0] ?? null, pendingSelections: next });
    syncToInput(next);
  },
  removePendingSelection: (index) => {
    const next = get().pendingSelections.filter((_, i) => i !== index);
    set({ pending: next[0] ?? null, pendingSelections: next });
    syncToInput(next);
  },
  clearPendingSelections: () => {
    set({ pending: null, pendingSelections: [] });
    syncToInput([]);
  },
}));
