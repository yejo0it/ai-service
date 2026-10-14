import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { checkEmail, errorDataOf, signup, toErrorMessage } from "../api/client";
import { ROUTES } from "../routes";
import AuthLayout, {
  AuthField,
  AuthInput,
  PRIMARY_BUTTON_CLASS,
  SIDE_BUTTON_CLASS,
} from "./AuthLayout";
import NewPasswordFields, { validateNewPassword, type NewPasswordErrors } from "./NewPasswordFields";
import PhoneVerificationField, { type VerifiedPhone } from "./PhoneVerificationField";
import { safeReturnPath, type ReturnPathState } from "./returnPath";
import { saveSession } from "./session";
import { EMAIL_FORMAT_MESSAGE, EMAIL_PATTERN, firstError, nicknameError } from "./validation";

interface SignupErrors extends NewPasswordErrors {
  email?: string;
  name?: string;
  phone?: string;
}

type SignupField = keyof SignupErrors;

interface FieldMessage {
  error: string;
  success: string;
}

export default function SignupPage() {
  const navigate = useNavigate();
  // 로그인이 필요한 화면에서 로그인 → 회원가입으로 왔으면 가입 후 그 화면으로 보낸다.
  const returnPath = safeReturnPath((useLocation().state as ReturnPathState | null)?.from);

  const [email, setEmail] = useState("");
  // 중복 확인을 마친 이메일. 입력이 바뀌면 다시 확인해야 한다.
  const [checkedEmail, setCheckedEmail] = useState("");
  const [emailMessage, setEmailMessage] = useState<FieldMessage>({ error: "", success: "" });
  const [checkingEmail, setCheckingEmail] = useState(false);
  // 이메일 입력칸을 한 번 벗어난 뒤부터 형식 오류를 보여준다(입력하는 동안에는 보여주지 않는다).
  const [emailTouched, setEmailTouched] = useState(false);

  const [name, setName] = useState("");

  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  // 인증을 마친 번호와 가입 API에 넘길 토큰 { phone, token }
  const [verifiedPhone, setVerifiedPhone] = useState<VerifiedPhone | null>(null);

  const [errors, setErrors] = useState<SignupErrors>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const clearError = (field: SignupField) => setErrors((previous) => ({ ...previous, [field]: "" }));

  const changeEmail = (value: string) => {
    setEmail(value);
    setCheckedEmail("");
    setEmailMessage({ error: "", success: "" });
    clearError("email");
  };

  const handleCheckEmail = async () => {
    const value = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(value)) {
      setEmailMessage({ error: EMAIL_FORMAT_MESSAGE, success: "" });
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

  // 실시간으로 보여주는 형식 오류(서버·제출 오류가 있으면 그것을 먼저 보여준다). 이메일은 입력칸을 벗어난 뒤부터.
  // 비밀번호·비밀번호 확인은 NewPasswordFields가 같은 방식으로 처리한다.
  const emailError =
    errors.email ||
    emailMessage.error ||
    (emailTouched && email.trim() && !EMAIL_PATTERN.test(email.trim().toLowerCase()) ? EMAIL_FORMAT_MESSAGE : "");
  const nameError = errors.name || (name.trim() ? nicknameError(name.trim()) : "");

  const validate = (): SignupErrors => {
    const next: SignupErrors = validateNewPassword(password, passwordConfirm);
    const normalized = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) next.email = EMAIL_FORMAT_MESSAGE;
    else if (checkedEmail !== normalized) next.email = "이메일 중복 확인을 해 주세요.";
    if (name.trim()) next.name = nicknameError(name.trim());
    if (!verifiedPhone) next.phone = "휴대폰 인증을 완료해 주세요.";
    return next;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    setSubmitError("");
    if (Object.values(next).some(Boolean) || !verifiedPhone) return;

    setSubmitting(true);
    try {
      const session = await signup({
        email: checkedEmail,
        name: name.trim() || undefined,
        password,
        password_confirm: passwordConfirm,
        phone: verifiedPhone.phone,
        phone_verification_token: verifiedPhone.token,
      });
      saveSession(session);
      navigate(returnPath, { replace: true });
    } catch (error) {
      const data = errorDataOf(error);
      const fieldErrors: SignupErrors = {
        email: firstError(data, "email"),
        name: firstError(data, "name"),
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
          error={emailError}
          success={emailMessage.success}
        >
          <div className="flex gap-2">
            <AuthInput
              id="signup-email"
              type="email"
              autoComplete="email"
              placeholder="example@pinroute.com"
              value={email}
              error={emailError}
              onChange={(event) => changeEmail(event.target.value)}
              onBlur={() => setEmailTouched(true)}
              autoFocus
            />
            <button
              type="button"
              onClick={handleCheckEmail}
              disabled={checkingEmail || !EMAIL_PATTERN.test(email.trim().toLowerCase()) || Boolean(checkedEmail)}
              className={SIDE_BUTTON_CLASS}
            >
              {checkedEmail ? "확인 완료" : "중복 확인"}
            </button>
          </div>
        </AuthField>

        <AuthField
          label="닉네임 (선택)"
          htmlFor="signup-name"
          error={nameError}
          hint="입력하지 않으면 랜덤 닉네임이 생성됩니다."
        >
          <AuthInput
            id="signup-name"
            autoComplete="nickname"
            maxLength={12}
            placeholder="한글·영문·숫자·밑줄 2~12자"
            value={name}
            error={nameError}
            onChange={(event) => {
              setName(event.target.value);
              clearError("name");
            }}
          />
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
        <Link
          to={ROUTES.LOGIN}
          state={{ from: returnPath } satisfies ReturnPathState}
          className="font-semibold text-indigo-600 hover:text-indigo-700"
        >
          로그인
        </Link>
      </p>
    </AuthLayout>
  );
}
