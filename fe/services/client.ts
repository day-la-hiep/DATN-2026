import axios from "axios";

/** JWT phiên đăng nhập, lưu sau khi login/register thành công; interceptor gắn vào mọi request. */
export const ACCESS_TOKEN_STORAGE_KEY = "derma-auth-access-token";
export const REFRESH_TOKEN_STORAGE_KEY = "derma-auth-refresh-token";
export const AUTH_USER_STORAGE_KEY = "derma-auth-user";
export const AUTH_STATE_EVENT = "derma-auth-state-change";

export type AuthenticatedUser = {
  id: string;
  username: string;
  full_name: string;
  dob: string;
  gender: "male" | "female";
  role: string;
};

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

export function getAuthenticatedUser(): AuthenticatedUser | null {
  if (typeof window === "undefined") return null;
  try {
    const user = localStorage.getItem(AUTH_USER_STORAGE_KEY);
    return user ? (JSON.parse(user) as AuthenticatedUser) : null;
  } catch {
    return null;
  }
}

/** Id tài khoản đang đăng nhập (rỗng khi chưa có phiên) — thay cho id cứng trước đây. */
export function getCurrentUserId(): string {
  return getAuthenticatedUser()?.id ?? "";
}

export function setAuthSession(
  accessToken: string,
  refreshToken: string,
  user: AuthenticatedUser
): void {
  try {
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
    localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(user));
  } catch {
    // Phiên hiện tại vẫn có thể dùng access token nếu localStorage bị chặn.
  }
  window.dispatchEvent(new Event(AUTH_STATE_EVENT));
}

export function clearAuthSession(): void {
  try {
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    localStorage.removeItem(AUTH_USER_STORAGE_KEY);
  } catch {
    // no-op
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_STATE_EVENT));
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
    const url = error?.config?.url ?? "";
    const isCredentialSubmission = /^\/auth\/(login|register)$/.test(url);
    if (error?.response?.status === 401 && !isCredentialSubmission) {
      clearAccessToken();
      if (typeof window !== "undefined") {
        window.location.reload();
      }
    }
    return Promise.reject(error);
  }
);
