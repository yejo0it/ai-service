import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  checkEmail,
  requestPhoneCode,
  signup,
  toErrorMessage,
  verifyPhoneCode,
} from "../api/client";
import AuthLayout, {
  AuthField,
  AuthInput,
  PasswordInput,
  PRIMARY_BUTTON_CLASS,
  SIDE_BUTTON_CLASS,
} from "./AuthLayout";
import { saveSession } from "./session";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// 백엔드(accounts.serializers.PASSWORD_PATTERN)와 같은 규칙
const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s])\S{8,20}$/;
const PHONE_PATTERN = /^01[016789]\d{7,8}$/;
const PASSWORD_RULE = "영문, 숫자, 특수문자를 모두 포함해 8~20자";

const formatTimer = (seconds) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

/** 인증번호 유효 시간 카운트다운. expiresAt(ms)이 없으면 멈춘다. */
function useCountdown(expiresAt) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!expiresAt) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);
  return expiresAt ? Math.max(0, Math.ceil((expiresAt - now) / 1000)) : 0;
}

/** DRF 필드 에러 { field: [msg] } 에서 첫 메시지만 꺼낸다. */
const firstError = (data, field) => {
  const value = data?.[field];
  return Array.isArray(value) ? value[0] : value;
};

export default function SignupPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  // 중복 확인을 마친 이메일. 입력이 바뀌면 다시 확인해야 한다.
  const [checkedEmail, setCheckedEmail] = useState("");
  const [emailMessage, setEmailMessage] = useState({ error: "", success: "" });
  const [checkingEmail, setCheckingEmail] = useState(false);

  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");

  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [codeExpiresAt, setCodeExpiresAt] = useState(null);
  const [debugCode, setDebugCode] = useState("");
  // 인증을 마친 번호와 가입 API에 넘길 토큰
  const [verified, setVerified] = useState({ phone: "", token: "" });
  const [phoneMessage, setPhoneMessage] = useState({ error: "", success: "" });
  const [phoneBusy, setPhoneBusy] = useState(false);

  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const remaining = useCountdown(verified.phone ? null : codeExpiresAt);
  const codeSent = Boolean(codeExpiresAt);
  const isPhoneVerified = Boolean(verified.token) && verified.phone === phone;

  /* 실시간 검증 — 입력을 시작한 뒤에만 보여준다. */
  const passwordError =
    password && !PASSWORD_PATTERN.test(password) ? `비밀번호는 ${PASSWORD_RULE}로 입력해 주세요.` : "";
  const confirmError =
    passwordConfirm && passwordConfirm !== password ? "비밀번호가 일치하지 않아요." : "";

  const changeEmail = (value) => {
    setEmail(value);
    setCheckedEmail("");
    setEmailMessage({ error: "", success: "" });
    setErrors((previous) => ({ ...previous, email: "" }));
  };

  const handleCheckEmail = async () => {
    const value = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(value)) {
      setEmailMessage({ error: "이메일 형식이 올바르지 않아요.", success: "" });
      return;
    }
    setCheckingEmail(true);
    try {
      const { available } = await checkEmail(value);
      setCheckedEmail(available ? value : "");
      setEmailMessage(
        available
          ? { error: "", success: "사용할 수 있는 이메일이에요." }
          : { error: "이미 가입된 이메일이에요.", success: "" },
      );
    } catch (error) {
      setEmailMessage({ error: toErrorMessage(error), success: "" });
    } finally {
      setCheckingEmail(false);
    }
  };

  const changePhone = (value) => {
    // 숫자만 입력받는다.
    setPhone(value.replace(/\D/g, "").slice(0, 11));
    setPhoneMessage({ error: "", success: "" });
    setErrors((previous) => ({ ...previous, phone: "" }));
  };

  const handleRequestCode = async () => {
    if (!PHONE_PATTERN.test(phone)) {
      setPhoneMessage({ error: "휴대폰 번호를 정확히 입력해 주세요.", success: "" });
      return;
    }
    setPhoneBusy(true);
    try {
      const result = await requestPhoneCode(phone);
      setCodeExpiresAt(Date.now() + result.expires_in * 1000);
      setDebugCode(result.debug_code ?? "");
      setVerified({ phone: "", token: "" });
      setCode("");
      setPhoneMessage({ error: "", success: "인증번호를 보냈어요." });
    } catch (error) {
      setPhoneMessage({ error: toErrorMessage(error), success: "" });
    } finally {
      setPhoneBusy(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!/^\d{6}$/.test(code)) {
      setPhoneMessage({ error: "인증번호 6자리를 입력해 주세요.", success: "" });
      return;
    }
    setPhoneBusy(true);
    try {
      const { verification_token: token } = await verifyPhoneCode(phone, code);
      setVerified({ phone, token });
      setDebugCode("");
      setPhoneMessage({ error: "", success: "휴대폰 인증이 완료되었어요." });
    } catch (error) {
      setPhoneMessage({ error: toErrorMessage(error), success: "" });
    } finally {
      setPhoneBusy(false);
    }
  };

  const validate = () => {
    const next = {};
    const normalized = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) next.email = "이메일 형식이 올바르지 않아요.";
    else if (checkedEmail !== normalized) next.email = "이메일 중복 확인을 해 주세요.";
    if (!PASSWORD_PATTERN.test(password)) next.password = `비밀번호는 ${PASSWORD_RULE}로 입력해 주세요.`;
    if (!passwordConfirm || passwordConfirm !== password) {
      next.passwordConfirm = "비밀번호가 일치하지 않아요.";
    }
    if (!isPhoneVerified) next.phone = "휴대폰 인증을 완료해 주세요.";
    return next;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    setSubmitError("");
    if (Object.values(next).some(Boolean)) return;

    setSubmitting(true);
    try {
      const session = await signup({
        email: checkedEmail,
        password,
        password_confirm: passwordConfirm,
        phone,
        phone_verification_token: verified.token,
      });
      saveSession(session);
      navigate("/onboarding", { replace: true });
    } catch (error) {
      const data = error?.response?.data;
      const fieldErrors = {
        email: firstError(data, "email"),
        password: firstError(data, "password"),
        passwordConfirm: firstError(data, "password_confirm"),
        phone: firstError(data, "phone"),
      };
      if (Object.values(fieldErrors).some(Boolean)) setErrors(fieldErrors);
      else setSubmitError(toErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title="회원가입" description="이메일로 PinRoute를 시작해 보세요.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField
          label="이메일"
          htmlFor="signup-email"
          error={errors.email || emailMessage.error}
          success={emailMessage.success}
        >
          <div className="flex gap-2">
            <AuthInput
              id="signup-email"
              type="email"
              autoComplete="email"
              placeholder="example@pinroute.com"
              value={email}
              error={errors.email || emailMessage.error}
              onChange={(event) => changeEmail(event.target.value)}
              autoFocus
            />
            <button
              type="button"
              onClick={handleCheckEmail}
              disabled={checkingEmail || !email.trim() || Boolean(checkedEmail)}
              className={SIDE_BUTTON_CLASS}
            >
              {checkedEmail ? "확인 완료" : "중복 확인"}
            </button>
          </div>
        </AuthField>

        <AuthField
          label="비밀번호"
          htmlFor="signup-password"
          error={errors.password || passwordError}
          hint={PASSWORD_RULE}
        >
          <PasswordInput
            id="signup-password"
            autoComplete="new-password"
            placeholder="비밀번호"
            value={password}
            error={errors.password || passwordError}
            onChange={(event) => {
              setPassword(event.target.value);
              setErrors((previous) => ({ ...previous, password: "" }));
            }}
          />
        </AuthField>

        <AuthField
          label="비밀번호 확인"
          htmlFor="signup-password-confirm"
          error={errors.passwordConfirm || confirmError}
          success={passwordConfirm && !confirmError ? "비밀번호가 일치해요." : ""}
        >
          <PasswordInput
            id="signup-password-confirm"
            autoComplete="new-password"
            placeholder="비밀번호 다시 입력"
            value={passwordConfirm}
            error={errors.passwordConfirm || confirmError}
            onChange={(event) => {
              setPasswordConfirm(event.target.value);
              setErrors((previous) => ({ ...previous, passwordConfirm: "" }));
            }}
          />
        </AuthField>

        <AuthField
          label="휴대폰 번호"
          htmlFor="signup-phone"
          error={errors.phone || phoneMessage.error}
          success={phoneMessage.success}
          hint="'-' 없이 숫자만 입력해 주세요."
        >
          <div className="flex gap-2">
            <AuthInput
              id="signup-phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              placeholder="01012345678"
              value={phone}
              error={errors.phone || phoneMessage.error}
              disabled={isPhoneVerified}
              onChange={(event) => changePhone(event.target.value)}
            />
            <button
              type="button"
              onClick={handleRequestCode}
              disabled={phoneBusy || !phone || isPhoneVerified}
              className={SIDE_BUTTON_CLASS}
            >
              {isPhoneVerified ? "인증 완료" : codeSent ? "재요청" : "인증요청"}
            </button>
          </div>

          {codeSent && !isPhoneVerified && (
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
                onClick={handleVerifyCode}
                disabled={phoneBusy || code.length !== 6 || remaining === 0}
                className={SIDE_BUTTON_CLASS}
              >
                확인
              </button>
            </div>
          )}
          {codeSent && !isPhoneVerified && remaining === 0 && (
            <p className="mt-1 text-xs text-rose-600">인증 시간이 지났어요. 다시 요청해 주세요.</p>
          )}
          {debugCode && !isPhoneVerified && (
            <p className="mt-1 text-xs text-amber-600">개발 서버 인증번호: {debugCode}</p>
          )}
        </AuthField>

        {submitError && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {submitError}
          </p>
        )}

        <button type="submit" disabled={submitting} className={PRIMARY_BUTTON_CLASS}>
          {submitting ? "가입하는 중..." : "가입하기"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-500">
        이미 계정이 있으신가요?{" "}
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          로그인
        </Link>
      </p>
    </AuthLayout>
  );
}
