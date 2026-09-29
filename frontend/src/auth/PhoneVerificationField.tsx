import { useEffect, useState } from "react";
import { requestPhoneCode, toErrorMessage, verifyPhoneCode } from "../api/client";
import { AuthField, AuthInput, SIDE_BUTTON_CLASS } from "./AuthLayout";
import { PHONE_PATTERN } from "./validation";

/** 인증을 마친 번호와, 백엔드에 phone_verification_token으로 넘길 토큰 */
export interface VerifiedPhone {
  phone: string;
  token: string;
}

interface PhoneVerificationFieldProps {
  id: string;
  /** 제출 검증·서버에서 온 에러 (인증 과정의 에러는 컴포넌트가 직접 보여준다) */
  error?: string;
  /** 인증을 마치면 { phone, token }, 번호를 다시 입력하면 null */
  onVerifiedChange: (verified: VerifiedPhone | null) => void;
  autoFocus?: boolean;
}

interface FieldMessage {
  error: string;
  success: string;
}

const formatTimer = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

/** 인증번호 유효 시간 카운트다운. expiresAt(ms)이 없으면 멈춘다. */
function useCountdown(expiresAt: number | null): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!expiresAt) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);
  return expiresAt ? Math.max(0, Math.ceil((expiresAt - now) / 1000)) : 0;
}

/**
 * 휴대폰 번호 입력 + 인증요청 + 인증번호 확인 (회원가입 · 아이디 찾기 · 비밀번호 재설정 공통).
 * 인증을 마치면 onVerifiedChange({ phone, token })을, 번호를 다시 입력하면 null을 알린다.
 * token은 백엔드에 phone_verification_token으로 넘긴다.
 */
export default function PhoneVerificationField({
  id,
  error,
  onVerifiedChange,
  autoFocus,
}: PhoneVerificationFieldProps) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  // 인증번호 만료 시각(ms). 아직 요청하지 않았으면 null.
  const [codeExpiresAt, setCodeExpiresAt] = useState<number | null>(null);
  const [debugCode, setDebugCode] = useState("");
  const [verified, setVerified] = useState(false);
  const [message, setMessage] = useState<FieldMessage>({ error: "", success: "" });
  const [busy, setBusy] = useState(false);

  const remaining = useCountdown(verified ? null : codeExpiresAt);
  const codeSent = Boolean(codeExpiresAt);
  const shownError = error || message.error;

  const changePhone = (value: string) => {
    // 숫자만 입력받는다.
    setPhone(value.replace(/\D/g, "").slice(0, 11));
    setMessage({ error: "", success: "" });
  };

  const handleRequest = async () => {
    if (!PHONE_PATTERN.test(phone)) {
      setMessage({ error: "휴대폰 번호를 정확히 입력해 주세요.", success: "" });
      return;
    }
    setBusy(true);
    try {
      const result = await requestPhoneCode(phone);
      setCodeExpiresAt(Date.now() + result.expires_in * 1000);
      setDebugCode(result.debug_code ?? "");
      setCode("");
      setMessage({ error: "", success: "인증번호를 보냈어요." });
    } catch (err) {
      setMessage({ error: toErrorMessage(err), success: "" });
    } finally {
      setBusy(false);
    }
  };

  const handleVerify = async () => {
    setBusy(true);
    try {
      const { verification_token: token } = await verifyPhoneCode(phone, code);
      setVerified(true);
      setDebugCode("");
      setMessage({ error: "", success: "휴대폰 인증이 완료되었어요." });
      onVerifiedChange({ phone, token });
    } catch (err) {
      setMessage({ error: toErrorMessage(err), success: "" });
    } finally {
      setBusy(false);
    }
  };

  // 인증 후 번호를 바꾸려면 처음부터 다시 인증한다.
  const handleReset = () => {
    setVerified(false);
    setCodeExpiresAt(null);
    setCode("");
    setMessage({ error: "", success: "" });
    onVerifiedChange(null);
  };

  return (
    <AuthField
      label="휴대폰 번호"
      htmlFor={id}
      error={shownError}
      success={message.success}
      hint="'-' 없이 숫자만 입력해 주세요."
    >
      <div className="flex gap-2">
        <AuthInput
          id={id}
          type="tel"
          inputMode="numeric"
          autoComplete="tel-national"
          placeholder="01012345678"
          value={phone}
          error={shownError}
          disabled={verified}
          autoFocus={autoFocus}
          onChange={(event) => changePhone(event.target.value)}
        />
        {verified ? (
          <button type="button" onClick={handleReset} className={SIDE_BUTTON_CLASS}>
            번호 변경
          </button>
        ) : (
          <button
            type="button"
            onClick={handleRequest}
            disabled={busy || !phone}
            className={SIDE_BUTTON_CLASS}
          >
            {codeSent ? "재요청" : "인증요청"}
          </button>
        )}
      </div>

      {codeSent && !verified && (
        <div className="mt-2 flex gap-2">
          <div className="relative flex-1">
            <AuthInput
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="인증번호 6자리"
              aria-label="인증번호"
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              className="pr-16"
            />
            <span
              className={`absolute right-3.5 top-1/2 -translate-y-1/2 text-sm tabular-nums ${
                remaining > 0 ? "text-rose-500" : "text-slate-400"
              }`}
            >
              {formatTimer(remaining)}
            </span>
          </div>
          <button
            type="button"
            onClick={handleVerify}
            disabled={busy || code.length !== 6 || remaining === 0}
            className={SIDE_BUTTON_CLASS}
          >
            확인
          </button>
        </div>
      )}
      {codeSent && !verified && remaining === 0 && (
        <p className="mt-1 text-xs text-rose-600">인증 시간이 지났어요. 다시 요청해 주세요.</p>
      )}
      {debugCode && !verified && (
        <p className="mt-1 text-xs text-amber-600">개발 서버 인증번호: {debugCode}</p>
      )}
    </AuthField>
  );
}
