import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "/api/v1",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});


// Nơi để thêm interceptor sau này: gắn access token, refresh token,
// map lỗi HTTP -> thông báo hiển thị, v.v.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // TODO: xử lý lỗi tập trung khi nối backend thật
    return Promise.reject(error);
  }
);
