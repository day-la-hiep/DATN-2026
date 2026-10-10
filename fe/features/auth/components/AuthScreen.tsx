"use client";

import { useState, type FormEvent } from "react";
import axios from "axios";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  CircleAlert,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from "lucide-react";
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

const inputClassName =
  "mt-1.5 h-12 w-full rounded-xl border border-input bg-background px-4 text-sm text-foreground shadow-sm shadow-slate-900/[0.02] outline-none transition placeholder:text-muted-foreground/60 focus:border-brand focus:ring-4 focus:ring-brand/10";

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
      const response =
        mode === "login"
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
    <main className="min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[minmax(0,1.04fr)_minmax(420px,0.96fr)]">
      <aside className="relative isolate flex min-h-[370px] flex-col overflow-hidden bg-foreground px-6 py-6 text-background sm:min-h-[410px] sm:px-10 sm:py-8 lg:sticky lg:top-0 lg:h-screen lg:min-h-[720px] lg:px-12 lg:py-10 xl:px-16">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle,rgba(255,255,255,0.12)_1px,transparent_1px)] bg-[size:30px_30px] opacity-40"
        />
        <div
          aria-hidden="true"
          className="ambient-glow -left-40 -top-40 size-[28rem] opacity-70"
        />
        <div
          aria-hidden="true"
          className="ambient-glow -bottom-48 right-0 size-[30rem] opacity-60"
        />

        <header className="relative z-10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-accent-gradient flex size-11 items-center justify-center rounded-2xl text-white shadow-accent">
              <Stethoscope className="size-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-bold tracking-[0.14em]">DERMA AI</p>
              <p className="mt-0.5 text-[11px] text-background/60">Chăm sóc da liễu</p>
            </div>
          </div>
          <span className="hidden items-center gap-2 rounded-full border border-background/15 bg-background/5 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-background/75 sm:inline-flex">
            <span className="animate-pulse-subtle size-1.5 rounded-full bg-brand" />
            Đồng hành cùng bạn
          </span>
        </header>

        <div className="relative z-10 mt-10 max-w-xl sm:mt-12 lg:mt-14">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-background/85 sm:text-xs">
            <Activity className="size-3.5 text-brand" aria-hidden="true" />
            Chăm sóc bắt đầu từ thấu hiểu
          </p>
          <h1 className="max-w-lg font-display text-[2.65rem] leading-[1.08] tracking-[-0.03em] sm:text-5xl xl:text-[3.5rem]">
            Lắng nghe làn da.
            <br />
            <span className="gradient-text">Chăm sóc từ hôm nay.</span>
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-background/70 sm:text-base">
            Theo dõi sức khỏe làn da của bạn.
          </p>
        </div>

        <div
          aria-hidden="true"
          className="relative mt-6 h-32 sm:h-40 lg:mt-auto lg:h-[270px]"
        >
          <div className="auth-orbit absolute right-0 top-[-76px] size-[250px] rounded-full border border-dashed border-brand/35 sm:right-8 sm:size-[300px] lg:right-12 lg:top-[-36px] lg:size-[360px]" />
          <div className="absolute right-12 top-[-34px] size-36 rounded-full bg-gradient-to-br from-brand/40 to-brand-secondary/5 blur-[1px] sm:right-20 sm:size-48 lg:right-24 lg:top-[-8px] lg:size-56" />
          <div className="absolute right-20 top-[-4px] size-20 rounded-full border border-background/20 bg-background/5 backdrop-blur-sm sm:right-28 sm:size-28 lg:right-36 lg:top-6 lg:size-36" />
          <div className="auth-float absolute left-0 top-2 rounded-2xl border border-background/15 bg-background/10 p-3 shadow-xl backdrop-blur-lg sm:left-4 sm:top-5 sm:p-4 lg:left-2 lg:top-8">
            <div className="flex items-center gap-3">
              <div className="bg-accent-gradient flex size-10 items-center justify-center rounded-xl text-white">
                <ShieldCheck className="size-5" />
              </div>
              <div>
                <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-background/55">
                  Hồ sơ cá nhân
                </p>
                <p className="mt-1 text-xs font-semibold text-background sm:text-sm">
                  Theo dõi hành trình da
                </p>
              </div>
            </div>
          </div>
          <div className="auth-float-delayed absolute bottom-0 right-0 rounded-2xl border border-background/15 bg-[#0f172a]/80 p-3 shadow-2xl backdrop-blur-xl sm:right-2 sm:p-4 lg:bottom-5 lg:right-8">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-xl bg-background/10 text-brand">
                <Stethoscope className="size-4" />
              </div>
              <div>
                <p className="text-xs font-semibold text-white">Thông tin tham khảo</p>
                <p className="mt-1 text-[10px] text-white/55">Kết nối kiến thức da liễu</p>
              </div>
              <ArrowRight className="ml-2 size-4 text-brand" />
            </div>
          </div>
          <div className="absolute bottom-2 left-[46%] hidden grid-cols-3 gap-1.5 sm:grid">
            {Array.from({ length: 9 }, (_, index) => (
              <span key={index} className="size-1 rounded-full bg-brand/70" />
            ))}
          </div>
        </div>

        <footer className="relative z-10 mt-5 flex items-center gap-3 border-t border-background/15 pt-4 text-[11px] leading-5 text-background/65 sm:mt-6 lg:mt-4">
          <ShieldCheck className="size-4 shrink-0 text-brand" aria-hidden="true" />
          <p>
            Nội dung AI chỉ mang tính tham khảo, không thay thế chẩn đoán y khoa.
          </p>
        </footer>
      </aside>

      <section className="relative flex items-center justify-center overflow-hidden px-5 py-10 sm:px-8 sm:py-14 lg:min-h-screen lg:px-10 xl:px-14">
        <div
          aria-hidden="true"
          className="ambient-glow -right-48 top-0 size-[30rem] opacity-50"
        />
        <div className="auth-enter relative z-10 w-full max-w-[460px] rounded-[1.65rem] bg-gradient-to-br from-brand/45 via-brand/10 to-brand/5 p-px shadow-xl shadow-brand/5">
          <div className="rounded-[calc(1.65rem-1px)] bg-card p-5 sm:p-8">
            <div className="mb-7 flex items-center gap-3">
              <div className="bg-accent-gradient flex size-10 items-center justify-center rounded-xl text-white shadow-accent">
                <LockKeyhole className="size-4" aria-hidden="true" />
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Khu vực tài khoản
                </p>
              </div>
            </div>

            <div className="mb-6">
              <h2 className="font-display text-3xl leading-tight tracking-[-0.02em] sm:text-4xl">
                {isRegister ? (
                  <>
                    Tạo tài khoản
                    <br />
                    <span className="gradient-text">của bạn.</span>
                  </>
                ) : (
                  <>
                    Chào mừng
                    <br />
                    <span className="gradient-text">bạn trở lại.</span>
                  </>
                )}
              </h2>
            </div>

            <div
              className="mb-6 grid grid-cols-2 gap-1 rounded-xl border border-border bg-muted/70 p-1"
              aria-label="Chọn hình thức tài khoản"
            >
              <button
                type="button"
                aria-pressed={!isRegister}
                disabled={isSubmitting}
                onClick={() => switchMode("login")}
                className={`min-h-11 rounded-lg px-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 ${
                  !isRegister
                    ? "bg-card text-brand shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Đăng nhập
              </button>
              <button
                type="button"
                aria-pressed={isRegister}
                disabled={isSubmitting}
                onClick={() => switchMode("register")}
                className={`min-h-11 rounded-lg px-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 ${
                  isRegister
                    ? "bg-card text-brand shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Đăng ký
              </button>
            </div>

            <form
              key={mode}
              onSubmit={handleSubmit}
              className="auth-enter space-y-4"
              noValidate
              aria-busy={isSubmitting}
            >
              {isRegister && (
                <>
                  <label
                    htmlFor="auth-full-name"
                    className="block text-sm font-medium text-foreground"
                  >
                    Họ và tên
                    <span className="relative block">
                      <UserRound
                        className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <input
                        id="auth-full-name"
                        name="full_name"
                        autoComplete="name"
                        required
                        maxLength={255}
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                        placeholder="Nguyễn Văn An"
                        className={`${inputClassName} pl-10`}
                      />
                    </span>
                  </label>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <label
                      htmlFor="auth-dob"
                      className="block text-sm font-medium text-foreground"
                    >
                      Ngày sinh
                      <span className="relative block">
                        <CalendarDays
                          className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <input
                          id="auth-dob"
                          name="dob"
                          type="date"
                          autoComplete="bday"
                          required
                          value={dob}
                          onChange={(event) => setDob(event.target.value)}
                          max={new Date().toISOString().slice(0, 10)}
                          className={`${inputClassName} min-w-0 pl-10 pr-2`}
                        />
                      </span>
                    </label>
                    <label
                      htmlFor="auth-gender"
                      className="block text-sm font-medium text-foreground"
                    >
                      Giới tính
                      <select
                        id="auth-gender"
                        name="gender"
                        autoComplete="sex"
                        value={gender}
                        onChange={(event) =>
                          setGender(event.target.value as "male" | "female")
                        }
                        className={inputClassName}
                      >
                        <option value="female">Nữ</option>
                        <option value="male">Nam</option>
                      </select>
                    </label>
                  </div>
                </>
              )}

              <label
                htmlFor="auth-username"
                className="block text-sm font-medium text-foreground"
              >
                Tên đăng nhập
                <input
                  id="auth-username"
                  name="username"
                  autoComplete="username"
                  required
                  minLength={isRegister ? 3 : 1}
                  maxLength={64}
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Nhập tên đăng nhập"
                  className={inputClassName}
                />
              </label>

              <label
                htmlFor="auth-password"
                className="block text-sm font-medium text-foreground"
              >
                Mật khẩu
                <span className="relative block">
                  <input
                    id="auth-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    required
                    minLength={isRegister ? 6 : 1}
                    maxLength={128}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={isRegister ? "Tối thiểu 6 ký tự" : "Nhập mật khẩu"}
                    className={`${inputClassName} pr-12`}
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((visible) => !visible)}
                    className="absolute inset-y-0 right-1 flex min-h-11 min-w-11 items-center justify-center self-center rounded-lg text-muted-foreground transition hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    {showPassword ? (
                      <EyeOff className="size-4" aria-hidden="true" />
                    ) : (
                      <Eye className="size-4" aria-hidden="true" />
                    )}
                  </button>
                </span>
              </label>

              {isRegister && (
                <label
                  htmlFor="auth-confirm-password"
                  className="block text-sm font-medium text-foreground"
                >
                  Xác nhận mật khẩu
                  <input
                    id="auth-confirm-password"
                    name="password_confirmation"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    required
                    minLength={6}
                    maxLength={128}
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    placeholder="Nhập lại mật khẩu"
                    className={inputClassName}
                  />
                </label>
              )}

              {errorMessage && (
                <div
                  role="alert"
                  className="flex items-start gap-2.5 rounded-xl border border-destructive/20 bg-destructive/5 px-3.5 py-3 text-sm leading-5 text-destructive"
                >
                  <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  <p>{errorMessage}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="group flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[var(--brand)] to-[var(--brand-secondary,#4d7cff)] px-4 text-sm font-semibold text-brand-foreground shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:brightness-110 hover:shadow-accent-lg active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-65"
              >
                {isSubmitting ? (
                  <>
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    {isRegister ? "Đang tạo tài khoản..." : "Đang đăng nhập..."}
                  </>
                ) : (
                  <>
                    {isRegister ? "Tạo tài khoản" : "Đăng nhập"}
                    <ArrowRight
                      className="size-4 transition-transform group-hover:translate-x-1"
                      aria-hidden="true"
                    />
                  </>
                )}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-muted-foreground">
              {isRegister ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => switchMode(isRegister ? "login" : "register")}
                className="min-h-11 rounded-md px-1 font-semibold text-brand underline decoration-brand/40 underline-offset-4 transition hover:decoration-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-60"
              >
                {isRegister ? "Đăng nhập" : "Đăng ký ngay"}
              </button>
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
