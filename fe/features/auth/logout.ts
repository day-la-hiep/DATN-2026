import { api, clearAuthSession, REFRESH_TOKEN_STORAGE_KEY } from "@/services/client";

export async function logout(): Promise<void> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
  if (refreshToken) {
    try {
      await api.post("/auth/logout", { refresh_token: refreshToken });
    } catch {
      // xoá phiên cục bộ dù không gọi được API
    }
  }
  clearAuthSession();
  // store còn dữ liệu của tài khoản cũ; tải lại để tài khoản sau không thấy
  window.location.reload();
}
