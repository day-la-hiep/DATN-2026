"use client";

import { create } from "zustand";

interface ComposerState {
  /** prompt được chèn sẵn vào ô nhập chat (vd: yêu cầu tạo skill) */
  draft: string;
  setDraft: (value: string) => void;
}

export const useComposerStore = create<ComposerState>((set) => ({
  draft: "",
  setDraft: (value) => set({ draft: value }),
}));
