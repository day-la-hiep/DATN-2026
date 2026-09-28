"use client";

import { create } from "zustand";

export type Brand = "blue" | "emerald" | "violet" | "red";

export const BRAND_OPTIONS: { id: Brand; label: string; color: string }[] = [
  { id: "blue", label: "Xanh dương", color: "oklch(0.546 0.245 262.881)" },
  { id: "emerald", label: "Ngọc lục bảo", color: "oklch(0.696 0.17 162.48)" },
  { id: "violet", label: "Tím", color: "oklch(0.541 0.281 293.009)" },
  { id: "red", label: "Đỏ", color: "oklch(0.577 0.245 27.325)" },
];

const STORAGE_KEY = "derma-ai-brand";

function isBrand(value: string | null): value is Brand {
  return value === "blue" || value === "emerald" || value === "violet" || value === "red";
}

export function getStoredBrand(): Brand {
  if (typeof window === "undefined") return "blue";
  const raw = localStorage.getItem(STORAGE_KEY);
  return isBrand(raw) ? raw : "blue";
}

export function applyBrand(brand: Brand) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = brand;
}

interface BrandState {
  brand: Brand;
  setBrand: (brand: Brand) => void;
}

export const useBrandStore = create<BrandState>((set) => ({
  brand: getStoredBrand(),
  setBrand: (brand) => {
    applyBrand(brand);
    localStorage.setItem(STORAGE_KEY, brand);
    set({ brand });
  },
}));
