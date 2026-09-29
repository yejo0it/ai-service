import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  confirmPasswordReset,
  toErrorMessage,
  verifyPasswordReset,
} from "../api/client";
import { ROUTES } from "../routes";
import AuthLayout, { AuthField, AuthInput, PRIMARY_BUTTON_CLASS } from "./AuthLayout";
import { AccountLinks } from "./FindIdPage";
import NewPasswordFields, { validateNewPassword } from "./NewPasswordFields";
import PhoneVerificationField from "./PhoneVerificationField";
import { EMAIL_PATTERN, firstError } from "./validation";

/**
 * `/reset-password` — 1단계: 이메일 + 가입할 때 인증한 휴대폰으로 본인 확인.
 * 확인되면 재설정 토큰(15분, 1회용)을 들고 `/reset-password/new`로 이동한다.
 */
export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [verifiedPhone, setVerifiedPhone] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const normalized = email.trim().toLowerCase();
    const next = {};
    if (!EMAIL_PATTERN.test(normalized)) next.email = "이메일 형식이 올바르지 않아요.";
    if (!verifiedPhone) next.phone = "휴대폰 인증을 완료해 주세요.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSubmitting(true);
    try {
      const { reset_token: resetToken } = await verifyPasswordReset({
        email: normalized,
        phone: verifiedPhone.phone,
        phone_verification_token: verifiedPhone.token,
      });
      // 토큰은 주소에 남지 않도록 라우터 state로만 넘긴다.
      navigate(ROUTES.RESET_PASSWORD_NEW, { state: { resetToken, email: normalized } });
    } catch (error) {
      setErrors({ form: toErrorMessage(error) });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="비밀번호 재설정"
      description="가입한 이메일과 휴대폰 인증으로 본인을 확인해요."
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField label="이메일" htmlFor="reset-email" error={errors.email}>
          <AuthInput
            id="reset-email"
            type="email"
            autoComplete="email"
            placeholder="example@pinroute.com"
            value={email}
            error={errors.email}
            onChange={(event) => {
              setEmail(event.target.value);
              setErrors((previous) => ({ ...previous, email: "", form: "" }));
            }}
            autoFocus
          />
        </AuthField>

        <PhoneVerificationField
          id="reset-phone"
          error={errors.phone}
          onVerifiedChange={(verified) => {
            setVerifiedPhone(verified);
            setErrors((previous) => ({ ...previous, phone: "", form: "" }));
          }}
        />

        {errors.form && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {errors.form}
          </p>
        )}

        <button type="submit" disabled={submitting} className={PRIMARY_BUTTON_CLASS}>
          {submitting ? "확인하는 중..." : "다음"}
        </button>
      </form>

      <AccountLinks current={ROUTES.RESET_PASSWORD} />
    </AuthLayout>
  );
}

/**
 * `/reset-password/new` — 2단계: 새 비밀번호 입력.
 * 1단계를 거치지 않고(새로고침 등) 들어오면 토큰이 없으므로 1단계로 돌려보낸다.
 * 변경을 마치면 로그인 화면으로 이동해 안내 문구와 이메일을 채워둔다.
 */
export function ResetPasswordNewPage() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  if (!state?.resetToken) return <Navigate to={ROUTES.RESET_PASSWORD} replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    const next = validateNewPassword(password, passwordConfirm);
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSubmitting(true);
    try {
      await confirmPasswordReset({
        reset_token: state.resetToken,
        password,
        password_confirm: passwordConfirm,
      });
      navigate(ROUTES.LOGIN, {
        replace: true,
        state: {
          email: state.email,
          notice: "비밀번호를 변경했어요. 새 비밀번호로 로그인해 주세요.",
        },
      });
    } catch (error) {
      const data = error?.response?.data;
      const fieldErrors = {
        password: firstError(data, "password"),
        passwordConfirm: firstError(data, "password_confirm"),
      };
      setErrors(
        Object.values(fieldErrors).some(Boolean) ? fieldErrors : { form: toErrorMessage(error) },
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title="새 비밀번호 설정" description={`${state.email} 계정의 비밀번호를 바꿔요.`}>
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <NewPasswordFields
          idPrefix="reset"
          label="새 비밀번호"
          autoFocus
          password={password}
          passwordConfirm={passwordConfirm}
          errors={errors}
          onPasswordChange={(value) => {
            setPassword(value);
            setErrors((previous) => ({ ...previous, password: "", form: "" }));
          }}
          onPasswordConfirmChange={(value) => {
            setPasswordConfirm(value);
            setErrors((previous) => ({ ...previous, passwordConfirm: "", form: "" }));
          }}
        />

        {errors.form && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {errors.form}
          </p>
        )}

        <button type="submit" disabled={submitting} className={PRIMARY_BUTTON_CLASS}>
          {submitting ? "변경하는 중..." : "비밀번호 변경"}
        </button>
      </form>
    </AuthLayout>
  );
}
