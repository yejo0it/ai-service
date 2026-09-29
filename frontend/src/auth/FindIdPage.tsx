import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { findId, toErrorMessage } from "../api/client";
import { ROUTES, type RoutePath } from "../routes";
import AuthLayout, { PRIMARY_BUTTON_CLASS } from "./AuthLayout";
import type { LoginLocationState } from "./LoginPage";
import PhoneVerificationField, { type VerifiedPhone } from "./PhoneVerificationField";

/**
 * `/find-id` — 가입할 때 인증한 휴대폰으로 다시 인증하면 가입된 이메일(아이디)을 보여준다.
 * [로그인하기]를 누르면 첫 번째 이메일을 채운 로그인 화면으로 이동한다.
 */
export default function FindIdPage() {
  const navigate = useNavigate();
  const [verifiedPhone, setVerifiedPhone] = useState<VerifiedPhone | null>(null);
  // 조회 전에는 null, 조회 후에는 찾은 이메일 목록(없으면 빈 배열)
  const [emails, setEmails] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!verifiedPhone) {
      setError("휴대폰 인증을 완료해 주세요.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await findId({
        phone: verifiedPhone.phone,
        phone_verification_token: verifiedPhone.token,
      });
      setEmails(result.emails);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (emails) {
    return (
      <AuthLayout title="아이디 찾기" description="휴대폰 인증으로 가입된 아이디를 확인했어요.">
        {emails.length > 0 ? (
          <ul className="space-y-2 rounded-2xl bg-slate-50 p-4">
            {emails.map((email) => (
              <li key={email} className="flex items-center gap-2.5 text-base text-slate-900">
                <i className="far fa-envelope text-slate-400" aria-hidden="true" />
                <span className="break-all font-semibold">{email}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
            이 번호로 이메일 가입한 계정이 없어요. 카카오·네이버로 가입했다면 간편 로그인을
            이용해 주세요.
          </p>
        )}

        <div className="mt-6 space-y-2.5">
          <button
            type="button"
            onClick={() =>
              navigate(ROUTES.LOGIN, {
                replace: true,
                state: { email: emails[0] ?? "" } satisfies LoginLocationState,
              })
            }
            className={PRIMARY_BUTTON_CLASS}
          >
            로그인하기
          </button>
          {emails.length > 0 && (
            <Link
              to={ROUTES.RESET_PASSWORD}
              className="block text-center text-sm font-medium text-slate-500 hover:text-indigo-600"
            >
              비밀번호가 기억나지 않나요? 비밀번호 재설정
            </Link>
          )}
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="아이디 찾기" description="가입할 때 인증한 휴대폰 번호로 찾을 수 있어요.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <PhoneVerificationField
          id="find-id-phone"
          autoFocus
          onVerifiedChange={(verified) => {
            setVerifiedPhone(verified);
            setError("");
          }}
        />

        {error && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !verifiedPhone}
          className={PRIMARY_BUTTON_CLASS}
        >
          {submitting ? "찾는 중..." : "아이디 찾기"}
        </button>
      </form>

      <AccountLinks />
    </AuthLayout>
  );
}

interface AccountLinksProps {
  /** 지금 보고 있는 계정 찾기 화면. 나머지 한 화면으로 가는 링크를 보여준다. */
  current?: RoutePath;
}

/** 계정 찾기 화면 하단의 로그인 · 비밀번호 재설정 이동 링크 */
export function AccountLinks({ current = ROUTES.FIND_ID }: AccountLinksProps) {
  const links = [
    { to: ROUTES.LOGIN, label: "로그인" },
    current === ROUTES.FIND_ID
      ? { to: ROUTES.RESET_PASSWORD, label: "비밀번호 재설정" }
      : { to: ROUTES.FIND_ID, label: "아이디 찾기" },
  ];
  return (
    <p className="mt-6 flex justify-center gap-3 text-sm text-slate-500">
      {links.map((link, index) => (
        <span key={link.to} className="flex items-center gap-3">
          {index > 0 && <span className="h-3 w-px bg-slate-200" aria-hidden="true" />}
          <Link to={link.to} className="font-medium hover:text-indigo-600">
            {link.label}
          </Link>
        </span>
      ))}
    </p>
  );
}
