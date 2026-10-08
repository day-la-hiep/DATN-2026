"use client";

import { useState, type FormEvent } from "react";
import axios from "axios";
import { ArrowRight, Eye, EyeOff, LockKeyhole, ShieldCheck, Stethoscope } from "lucide-react";
import { api, setAuthSession } from "@/services/client";

type AuthMode = "login" | "register";

type AuthResponse = {
  data: {
    access_token: string;
    refresh_token: string;
    user: {
      id: string;
      username: string;
      full_name: string;
      dob: string;
      gender: "male" | "female";
      role: string;
    };
  };
};

type AuthScreenProps = {
  onAuthenticated: () => void;
};

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: { msg?: string }) => item.msg)
        .filter(Boolean)
        .join(" ");
    }
    if (!error.response) return "Không kết nối được máy chủ. Vui lòng thử lại.";
  }
  return "Đã xảy ra lỗi. Vui lòng thử lại.";
}

export function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState<"male" | "female">("female");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    setErrorMessage("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");

    const normalizedUsername = username.trim();
    if (!normalizedUsername || !password.trim()) {
      setErrorMessage("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.");
      return;
    }
    if (mode === "register") {
      if (!fullName.trim() || !dob) {
        setErrorMessage("Vui lòng điền đầy đủ thông tin đăng ký.");
        return;
      }
      if (password.length < 6) {
        setErrorMessage("Mật khẩu cần có ít nhất 6 ký tự.");
        return;
      }
      if (password !== confirmation) {
        setErrorMessage("Mật khẩu xác nhận chưa khớp.");
        return;
      }
    }

    setIsSubmitting(true);
    try {
      const response = mode === "login"
        ? await api.post<AuthResponse>("/auth/login", {
            username: normalizedUsername,
            password,
          })
        : await api.post<AuthResponse>("/auth/register", {
            username: normalizedUsername,
            password,
            full_name: fullName.trim(),
            dob,
            gender,
          });

      setAuthSession(
        response.data.data.access_token,
        response.data.data.refresh_token,
        response.data.data.user
      );
      onAuthenticated();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <main className="relative grid min-h-screen bg-background text-foreground lg:grid-cols-[1.06fr_0.94fr]">
      <section className="relative flex min-h-[34vh] flex-col justify-between overflow-hidden bg-brand px-6 py-7 text-brand-foreground sm:px-10 sm:py-9 lg:min-h-screen lg:px-14 lg:py-12 xl:px-20">
        <div className="pointer-events-none absolute inset-0 opacity-[0.13] [background-image:linear-gradient(rgba(255,255,255,0.2)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.2)_1px,transparent_1px)] [background-size:42px_42px]" />
        <div className="pointer-events-none absolute -right-20 top-1/3 h-72 w-72 rotate-12 border border-white/20 sm:h-96 sm:w-96" />
        <div className="pointer-events-none absolute -right-8 top-[39%] h-56 w-56 rotate-12 border border-white/15 sm:h-72 sm:w-72" />

        <div className="relative z-10 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center border border-white/25 bg-white/10">
            <Stethoscope className="size-5" aria-hidden="true" />
          </div>
          <span className="text-sm font-semibold tracking-[0.12em]">DERMA AI</span>
        </div>

        <div className="relative z-10 max-w-xl py-10 lg:py-16">
          <p className="mb-5 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-white/75">
            <span className="h-px w-8 bg-white/75" />
            Chăm sóc da liễu
          </p>
          <h1 className="max-w-lg font-serif text-4xl leading-[1.12] sm:text-5xl lg:text-6xl">
            Hiểu làn da,<br />chăm sóc đúng cách.
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-white/80 sm:text-base">
            Không gian hỗ trợ theo dõi sức khỏe làn da và kết nối tư vấn chuyên môn.
          </p>
        </div>

        <div className="relative z-10">
          <div className="grid h-28 grid-cols-3 gap-2 sm:gap-3 lg:h-48 lg:grid-cols-[1.2fr_0.8fr] lg:grid-rows-2">
            <a
              href="https://commons.wikimedia.org/wiki/File:0601_Acne_Vulgaris.jpg"
              target="_blank"
              rel="noreferrer"
              aria-label="Ảnh mụn trứng cá, tác giả Dr. Gandikota Raghurama Rao"
              className="group relative min-w-0 overflow-hidden rounded-md border border-white/30 bg-cover bg-center shadow-lg lg:row-span-2"
              style={{ backgroundImage: "url(https://upload.wikimedia.org/wikipedia/commons/f/f4/0601_Acne_Vulgaris.jpg)" }}
            >
              <span className="absolute inset-x-0 bottom-0 bg-black/55 px-2 py-1.5 text-[10px] font-medium text-white sm:text-xs">Mụn trứng cá</span>
            </a>
            <a
              href="https://commons.wikimedia.org/wiki/File:Dermatitis_atopica_01.JPG"
              target="_blank"
              rel="noreferrer"
              aria-label="Ảnh viêm da cơ địa, tác giả AfroBrazilian"
              className="group relative min-w-0 overflow-hidden rounded-md border border-white/30 bg-cover bg-center shadow-lg"
              style={{ backgroundImage: "url(https://upload.wikimedia.org/wikipedia/commons/6/63/Dermatitis_atopica_01.JPG)" }}
            >
              <span className="absolute inset-x-0 bottom-0 bg-black/55 px-2 py-1.5 text-[10px] font-medium text-white sm:text-xs">Viêm da cơ địa</span>
            </a>
            <a
              href="https://commons.wikimedia.org/wiki/File:Psoriasis_with_typical_silver_scaly_appearance.jpg"
              target="_blank"
              rel="noreferrer"
              aria-label="Ảnh vảy nến, tác giả Ali zeki"
              className="group relative min-w-0 overflow-hidden rounded-md border border-white/30 bg-cover bg-center shadow-lg"
              style={{ backgroundImage: "url(https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/Psoriasis_with_typical_silver_scaly_appearance.jpg/500px-Psoriasis_with_typical_silver_scaly_appearance.jpg)" }}
            >
              <span className="absolute inset-x-0 bottom-0 bg-black/55 px-2 py-1.5 text-[10px] font-medium text-white sm:text-xs">Vảy nến</span>
            </a>
          </div>
          <p className="mt-2 text-[9px] leading-4 text-white/75 sm:text-[10px]">
            Ảnh: Dr. Gandikota Raghurama Rao (CC BY 4.0), AfroBrazilian (CC BY-SA 3.0), Ali zeki (CC BY 4.0) · Wikimedia Commons
          </p>
        </div>

        <div className="relative z-10 hidden items-end justify-between gap-8 border-t border-white/20 pt-5 text-xs leading-5 text-white/75 lg:flex">
          <p className="max-w-sm">Thông tin AI cung cấp chỉ mang tính tham khảo, không thay thế chẩn đoán y khoa.</p>
          <ShieldCheck className="mb-1 size-5 shrink-0" aria-hidden="true" />
        </div>
      </section>

      <section className="flex min-h-[66vh] items-center justify-center bg-background px-5 py-10 sm:px-10 lg:min-h-screen lg:px-12">
        <div className="w-full max-w-[420px]">
          <div className="mb-8 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.13em] text-brand">
            <LockKeyhole className="size-4" aria-hidden="true" />
            Tài khoản bảo mật
          </div>

          <div className="mb-7">
            <h2 className="font-serif text-3xl leading-tight text-foreground sm:text-4xl">
              {isRegister ? "Tạo tài khoản" : "Chào mừng trở lại"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {isRegister ? "Bắt đầu hồ sơ chăm sóc da của bạn." : "Đăng nhập để tiếp tục vào Derma AI."}
            </p>
          </div>

          <div className="mb-7 grid grid-cols-2 border-b border-border" role="tablist" aria-label="Chọn hình thức tài khoản">
            <button
              type="button"
              role="tab"
              aria-selected={!isRegister}
              onClick={() => switchMode("login")}
              className={`border-b-2 px-3 py-3 text-sm font-medium transition-colors ${!isRegister ? "border-brand text-brand" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              Đăng nhập
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isRegister}
              onClick={() => switchMode("register")}
              className={`border-b-2 px-3 py-3 text-sm font-medium transition-colors ${isRegister ? "border-brand text-brand" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              Đăng ký
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {isRegister && (
              <>
                <label className="block space-y-1.5 text-sm font-medium text-foreground">
                  Họ và tên
                  <input
                    autoComplete="name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Nguyễn Văn An"
                    className="h-12 w-full border border-input bg-card px-3.5 text-sm text-foreground outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15"
                  />
                </label>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <label className="block space-y-1.5 text-sm font-medium text-foreground">
                    Ngày sinh
                    <input
                      type="date"
                      value={dob}
                      onChange={(event) => setDob(event.target.value)}
                      max={new Date().toISOString().slice(0, 10)}
                      className="h-12 w-full min-w-0 border border-input bg-card px-3 text-sm text-foreground outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15"
                    />
                  </label>
                  <label className="block space-y-1.5 text-sm font-medium text-foreground">
                    Giới tính
                    <select
                      value={gender}
                      onChange={(event) => setGender(event.target.value as "male" | "female")}
                      className="h-12 w-full border border-input bg-card px-3 text-sm text-foreground outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/15"
                    >
                      <option value="female">Nữ</option>
                      <option value="male">Nam</option>
                    </select>
                  </label>
                </div>
              </>
            )}

            <label className="block space-y-1.5 text-sm font-medium text-foreground">
              Tên đăng nhập
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Tên đăng nhập"
                minLength={isRegister ? 3 : 1}
                maxLength={64}
                className="h-12 w-full border border-input bg-card px-3.5 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-brand focus:ring-2 focus:ring-brand/15"
              />
            </label>

            <label className="block space-y-1.5 text-sm font-medium text-foreground">
              Mật khẩu
              <span className="relative block">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={isRegister ? "Tối thiểu 6 ký tự" : "Nhập mật khẩu"}
                  minLength={isRegister ? 6 : 1}
                  maxLength={128}
                  className="h-12 w-full border border-input bg-card px-3.5 pr-12 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-brand focus:ring-2 focus:ring-brand/15"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-brand"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </span>
            </label>

            {isRegister && (
              <label className="block space-y-1.5 text-sm font-medium text-foreground">
                Xác nhận mật khẩu
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  placeholder="Nhập lại mật khẩu"
                  className="h-12 w-full border border-input bg-card px-3.5 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-brand focus:ring-2 focus:ring-brand/15"
                />
              </label>
            )}

            {errorMessage && (
              <p role="alert" className="border-l-2 border-[#b54436] bg-[#fff0ec] px-3 py-2.5 text-sm leading-5 text-[#8d3026]">
                {errorMessage}
              </p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="group flex h-12 w-full items-center justify-center gap-2 bg-brand px-4 text-sm font-semibold text-brand-foreground transition hover:opacity-90 disabled:cursor-wait disabled:opacity-65"
            >
              {isSubmitting ? "Đang xử lý..." : isRegister ? "Tạo tài khoản" : "Đăng nhập"}
              {!isSubmitting && <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isRegister ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
            <button
              type="button"
              onClick={() => switchMode(isRegister ? "login" : "register")}
              className="font-semibold text-brand underline decoration-brand/40 underline-offset-4 hover:opacity-80"
            >
              {isRegister ? "Đăng nhập" : "Đăng ký ngay"}
            </button>
          </p>
          <p className="mt-8 text-center text-[11px] leading-5 text-muted-foreground lg:hidden">
            Thông tin AI chỉ mang tính tham khảo, không thay thế chẩn đoán y khoa.
          </p>
        </div>
      </section>
    </main>
  );
}
