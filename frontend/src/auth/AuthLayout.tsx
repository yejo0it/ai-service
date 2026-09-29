import { useState, type InputHTMLAttributes, type ReactNode } from "react";
import { PinRouteAppIcon, PinRouteMark, PinRouteWordmark } from "../brand/Logo";

interface AuthLayoutProps {
  title: string;
  description?: string;
  children: ReactNode;
}

/**
 * 로그인·회원가입 공통 split 레이아웃.
 * 왼쪽은 브랜드 배너, 오른쪽은 폼. 좁은 화면에서는 배너를 숨기고 폼 위에 작은 로고를 둔다.
 */
export default function AuthLayout({ title, description, children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen bg-white">
      <aside className="relative hidden flex-1 items-center justify-center overflow-hidden bg-gradient-to-br from-indigo-600 via-indigo-600 to-violet-600 lg:flex">
        {/* 배경의 큰 마크 — 브랜드 패턴으로 은은하게만 보이게 한다. */}
        <PinRouteMark
          size={560}
          className="pointer-events-none absolute -bottom-32 -right-32 opacity-10"
        />
        <div className="relative flex flex-col items-center gap-6 text-center">
          <PinRouteAppIcon size={112} inverse className="shadow-[0_14px_36px_rgba(30,27,75,0.35)]" />
          <div>
            <PinRouteWordmark tone="light" className="text-[40px] leading-none" />
            <p className="mt-3 text-sm text-indigo-100">핀만 찍으면, 경로는 알아서</p>
          </div>
        </div>
      </aside>

      <main className="flex w-full items-center justify-center px-5 py-10 sm:px-8 lg:w-[520px] lg:shrink-0 xl:w-[560px]">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <PinRouteAppIcon size={30} />
            <PinRouteWordmark className="text-[22px]" />
          </div>
          <header className="mb-6">
            <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}

interface AuthFieldProps {
  label: string;
  /** 연결할 입력칸 id */
  htmlFor: string;
  error?: string;
  hint?: string;
  success?: string;
  children: ReactNode;
}

/** 폼 입력 한 칸 (라벨 + 입력 + 안내/에러). 온보딩 Field와 같은 톤이다. */
export function AuthField({ label, htmlFor, error, hint, success, children }: AuthFieldProps) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-rose-600">{error}</p>
      ) : success ? (
        <p className="mt-1 text-xs text-emerald-600">{success}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>
      )}
    </div>
  );
}

const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 " +
  "placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 " +
  "focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500";

export type AuthInputProps = InputHTMLAttributes<HTMLInputElement> & {
  /** 값이 있으면 입력칸 테두리를 에러 색으로 바꾼다(메시지는 AuthField가 보여준다). */
  error?: string;
};

export function AuthInput({ error, className = "", ...props }: AuthInputProps) {
  const errorClass = error ? "border-rose-400 focus:border-rose-500 focus:ring-rose-100" : "";
  return <input {...props} className={`${INPUT_CLASS} ${errorClass} ${className}`} />;
}

/** 비밀번호 입력. 오른쪽 눈 아이콘으로 입력값을 보이거나 숨긴다. */
export function PasswordInput(props: Omit<AuthInputProps, "type">) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <AuthInput {...props} type={visible ? "text" : "password"} className="pr-12" />
      <button
        type="button"
        onClick={() => setVisible((previous) => !previous)}
        aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
        aria-pressed={visible}
        title={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
        className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-xl text-slate-400 transition-colors hover:text-slate-600 focus-visible:text-indigo-600 focus-visible:outline-none"
      >
        <i className={`far ${visible ? "fa-eye" : "fa-eye-slash"}`} aria-hidden="true" />
      </button>
    </div>
  );
}

export const PRIMARY_BUTTON_CLASS =
  "w-full rounded-xl bg-indigo-600 px-5 py-3.5 text-sm font-semibold text-white transition-colors " +
  "hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300";

/** 입력칸 옆 보조 버튼(중복 확인, 인증요청 등) */
export const SIDE_BUTTON_CLASS =
  "shrink-0 rounded-xl border border-indigo-200 px-3.5 text-sm font-medium text-indigo-600 " +
  "transition-colors hover:border-indigo-400 hover:bg-indigo-50 " +
  "disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400 disabled:hover:bg-transparent";
