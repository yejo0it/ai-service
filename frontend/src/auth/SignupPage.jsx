import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { checkEmail, signup, toErrorMessage } from "../api/client";
import { ROUTES } from "../routes";
import AuthLayout, {
  AuthField,
  AuthInput,
  PRIMARY_BUTTON_CLASS,
  SIDE_BUTTON_CLASS,
} from "./AuthLayout";
import NewPasswordFields, { validateNewPassword } from "./NewPasswordFields";
import PhoneVerificationField from "./PhoneVerificationField";
import { saveSession } from "./session";
import { EMAIL_PATTERN, firstError } from "./validation";

export default function SignupPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  // 중복 확인을 마친 이메일. 입력이 바뀌면 다시 확인해야 한다.
  const [checkedEmail, setCheckedEmail] = useState("");
  const [emailMessage, setEmailMessage] = useState({ error: "", success: "" });
  const [checkingEmail, setCheckingEmail] = useState(false);

  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  // 인증을 마친 번호와 가입 API에 넘길 토큰 { phone, token }
  const [verifiedPhone, setVerifiedPhone] = useState(null);

  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const clearError = (field) => setErrors((previous) => ({ ...previous, [field]: "" }));

  const changeEmail = (value) => {
    setEmail(value);
    setCheckedEmail("");
    setEmailMessage({ error: "", success: "" });
    clearError("email");
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

  const validate = () => {
    const next = validateNewPassword(password, passwordConfirm);
    const normalized = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) next.email = "이메일 형식이 올바르지 않아요.";
    else if (checkedEmail !== normalized) next.email = "이메일 중복 확인을 해 주세요.";
    if (!verifiedPhone) next.phone = "휴대폰 인증을 완료해 주세요.";
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
        phone: verifiedPhone.phone,
        phone_verification_token: verifiedPhone.token,
      });
      saveSession(session);
      navigate(ROUTES.HOME, { replace: true });
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

        <NewPasswordFields
          idPrefix="signup"
          password={password}
          passwordConfirm={passwordConfirm}
          errors={errors}
          onPasswordChange={(value) => {
            setPassword(value);
            clearError("password");
          }}
          onPasswordConfirmChange={(value) => {
            setPasswordConfirm(value);
            clearError("passwordConfirm");
          }}
        />

        <PhoneVerificationField
          id="signup-phone"
          error={errors.phone}
          onVerifiedChange={(verified) => {
            setVerifiedPhone(verified);
            clearError("phone");
          }}
        />

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
        <Link to={ROUTES.LOGIN} className="font-semibold text-indigo-600 hover:text-indigo-700">
          로그인
        </Link>
      </p>
    </AuthLayout>
  );
}
