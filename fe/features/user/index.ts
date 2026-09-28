export interface User {
  id: string;
  name: string;
  email: string;
}

/** User giả lập — sau này thay bằng dữ liệu từ API auth */
export const CURRENT_USER: User = {
  id: "user-1",
  name: "Nguyễn Văn An",
  email: "an.nguyen@example.com",
};

export function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "U";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  const first = parts[0][0];
  const last = parts[parts.length - 1][0];
  return `${first}${last}`.toUpperCase();
}
