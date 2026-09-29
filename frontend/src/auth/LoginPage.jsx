import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { login, toErrorMessage } from "../api/client";
import AuthLayout, {
  AuthField,
  AuthInput,
  PasswordInput,
  PRIMARY_BUTTON_CLASS,
} from "./AuthLayout";
import { isSocialLoginConfigured, startSocialLogin } from "./oauth";
import { saveSession } from "./session";

/** 카카오 로그인 버튼 (카카오 디자인 가이드: #FEE500, 검정 말풍선 심볼, 85% 검정 레이블) */
function KakaoButton({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative flex h-12 w-full items-center justify-center rounded-xl bg-[#FEE500] text-sm font-semibold text-black/85 transition-[filter] hover:brightness-95"
    >
      <svg viewBox="0 0 24 24" className="absolute left-4 h-5 w-5" aria-hidden="true">
        <path
          fill="#000000"
          d="M12 3C6.48 3 2 6.47 2 10.75c0 2.77 1.86 5.2 4.66 6.57l-.95 3.48c-.08.3.26.54.52.37l4.16-2.75c.53.07 1.07.11 1.61.11 5.52 0 10-3.47 10-7.78S17.52 3 12 3z"
        />
      </svg>
      카카오 로그인
    </button>
  );
}

/** 네이버 로그인 버튼 (네이버 디자인 가이드: #03C75A, 흰색 N 로고) */
function NaverButton({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative flex h-12 w-full items-center justify-center rounded-xl bg-[#03C75A] text-sm font-semibold text-white transition-[filter] hover:brightness-95"
    >
      <svg viewBox="0 0 24 24" className="absolute left-[18px] h-3.5 w-3.5" aria-hidden="true">
        <path fill="#FFFFFF" d="M16.27 12.84 7.46 0H0v24h7.73V11.16L16.54 24H24V0h-7.73z" />
      </svg>
      네이버 로그인
    </button>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(location.state?.error ?? "");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("이메일과 비밀번호를 입력해 주세요.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      saveSession(await login({ email: email.trim(), password }));
      navigate(location.state?.from ?? "/onboarding", { replace: true });
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSocial = (provider) => {
    if (!isSocialLoginConfigured(provider)) {
      setError("소셜 로그인이 아직 설정되지 않았어요. 이메일로 로그인해 주세요.");
      return;
    }
    startSocialLogin(provider);
  };

  return (
    <AuthLayout title="로그인" description="핀만 찍으면 최적 경로를 찾아드려요.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField label="이메일" htmlFor="login-email">
          <AuthInput
            id="login-email"
            type="email"
            autoComplete="email"
            placeholder="example@pinroute.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoFocus
          />
        </AuthField>
        <AuthField label="비밀번호" htmlFor="login-password">
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            placeholder="비밀번호"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </AuthField>

        {error && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </p>
        )}

        <button type="submit" disabled={submitting} className={PRIMARY_BUTTON_CLASS}>
          {submitting ? "로그인하는 중..." : "로그인"}
        </button>
        <Link
          to="/signup"
          className="block w-full rounded-xl border border-slate-200 px-5 py-3.5 text-center text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
        >
          회원가입
        </Link>
      </form>

      <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />
        간편 로그인
        <span className="h-px flex-1 bg-slate-200" />
      </div>

      <div className="space-y-2.5">
        <KakaoButton onClick={() => handleSocial("kakao")} />
        <NaverButton onClick={() => handleSocial("naver")} />
      </div>
    </AuthLayout>
  );
}
