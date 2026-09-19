import axios from "axios";

/**
 * Shared-token auth đơn giản (bảo vệ bản demo khi deploy cho người ngoài test — xem
 * `core/app/core/auth.py`). Token nhập 1 lần qua `AccessGate` (`app/access-gate.tsx`),
 * lưu localStorage, tự gắn vào mọi request qua interceptor bên dưới.
 */
export const ACCESS_TOKEN_STORAGE_KEY = "derma-ai-access-token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string): void {
  try {
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  } catch {
    // localStorage có thể bị chặn (private mode...) — bỏ qua, request sẽ tự 401 lại.
  }
}

export function clearAccessToken(): void {
  try {
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    // no-op
  }
}

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "/api/v1",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Nơi để thêm interceptor sau này: refresh token, map lỗi HTTP -> thông báo hiển thị, v.v.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      // Token sai/hết hạn — xoá để AccessGate hỏi lại, không loop 401 vô tận.
      clearAccessToken();
      if (typeof window !== "undefined") {
        window.location.reload();
      }
    }
    return Promise.reject(error);
  }
);
