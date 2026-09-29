import { AuthField, PasswordInput } from "./AuthLayout";
import { PASSWORD_PATTERN, PASSWORD_RULE, PASSWORD_RULE_MESSAGE } from "./validation";

/** 새 비밀번호 규칙 검사 결과. 제출 전 검증에서 쓴다. */
export function validateNewPassword(password, passwordConfirm) {
  const errors = {};
  if (!PASSWORD_PATTERN.test(password)) errors.password = PASSWORD_RULE_MESSAGE;
  if (!passwordConfirm || passwordConfirm !== password) {
    errors.passwordConfirm = "비밀번호가 일치하지 않아요.";
  }
  return errors;
}

/**
 * 비밀번호 + 비밀번호 확인 (회원가입 · 비밀번호 재설정 공통).
 * 규칙·일치 여부는 입력을 시작한 뒤부터 실시간으로 보여주고, errors는 제출·서버 에러다.
 */
export default function NewPasswordFields({
  idPrefix,
  password,
  passwordConfirm,
  errors = {},
  onPasswordChange,
  onPasswordConfirmChange,
  label = "비밀번호",
  autoFocus,
}) {
  const passwordError =
    errors.password || (password && !PASSWORD_PATTERN.test(password) ? PASSWORD_RULE_MESSAGE : "");
  const confirmError =
    errors.passwordConfirm ||
    (passwordConfirm && passwordConfirm !== password ? "비밀번호가 일치하지 않아요." : "");

  return (
    <>
      <AuthField
        label={label}
        htmlFor={`${idPrefix}-password`}
        error={passwordError}
        hint={PASSWORD_RULE}
      >
        <PasswordInput
          id={`${idPrefix}-password`}
          autoComplete="new-password"
          placeholder={label}
          value={password}
          error={passwordError}
          autoFocus={autoFocus}
          onChange={(event) => onPasswordChange(event.target.value)}
        />
      </AuthField>

      <AuthField
        label={`${label} 확인`}
        htmlFor={`${idPrefix}-password-confirm`}
        error={confirmError}
        success={passwordConfirm && !confirmError ? "비밀번호가 일치해요." : ""}
      >
        <PasswordInput
          id={`${idPrefix}-password-confirm`}
          autoComplete="new-password"
          placeholder={`${label} 다시 입력`}
          value={passwordConfirm}
          error={confirmError}
          onChange={(event) => onPasswordConfirmChange(event.target.value)}
        />
      </AuthField>
    </>
  );
}
