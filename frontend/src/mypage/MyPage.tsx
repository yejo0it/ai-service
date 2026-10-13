import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import {
  cancelEmailChange,
  changePhone,
  checkEmailChangePassword,
  checkNickname,
  confirmEmailChange,
  deleteAvatar,
  errorDataOf,
  mediaUrl,
  requestEmailChange,
  resendEmailChange,
  toErrorMessage,
  updateNickname,
  uploadAvatar,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthInput, PasswordInput, SIDE_BUTTON_CLASS } from "../auth/AuthLayout";
import PhoneVerificationField from "../auth/PhoneVerificationField";
import { getSession, saveSession } from "../auth/session";
import { EMAIL_PATTERN, firstError } from "../auth/validation";
import Avatar from "../components/layout/Avatar";
import { nicknameOf } from "../components/layout/AppHeader";
import type { AuthUser } from "../types/api";

/** 백엔드 accounts.serializers.NICKNAME_PATTERN과 같은 규칙 */
const NICKNAME_PATTERN = /^[가-힣A-Za-z0-9_]{2,12}$/;
const NICKNAME_RULE_MESSAGE = "닉네임은 한글, 영문, 숫자, 밑줄(_)로 2~12자 입력해 주세요.";
const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
const AVATAR_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

const PRIMARY_BUTTON_CLASS =
  "rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50";
const SECONDARY_BUTTON_CLASS =
  "rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50";
const CHANGE_BUTTON_CLASS =
  "shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50";

/** 바뀐 회원 정보를 세션에 저장해 상단 바 등 화면 전체에 반영한다. */
function applyUser(user: AuthUser) {
  const session = getSession();
  if (session) saveSession({ ...session, user });
}

/** "01012345678" → "010-1234-5678" */
const formatPhone = (phone: string) =>
  phone.length === 11 ? `${phone.slice(0, 3)}-${phone.slice(3, 7)}-${phone.slice(7)}` : phone.replace(/^(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3");

interface InfoRowProps {
  label: string;
  children: ReactNode;
  /** 오른쪽 [변경] 버튼 자리 */
  action?: ReactNode;
  /** 변경 폼 (열려 있을 때만) */
  editor?: ReactNode;
}

function InfoRow({ label, children, action, editor }: InfoRowProps) {
  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <div className="flex items-center gap-3">
        <dt className="w-24 shrink-0 text-sm font-medium text-slate-500">{label}</dt>
        <dd className="flex min-w-0 flex-1 items-center gap-2 text-sm text-slate-900">{children}</dd>
        {action}
      </div>
      {editor && <div className="mt-3 sm:pl-24">{editor}</div>}
    </div>
  );
}

const FormActions = ({ onCancel, submitLabel, disabled }: { onCancel: () => void; submitLabel: string; disabled: boolean }) => (
  <div className="flex justify-end gap-2">
    <button type="button" onClick={onCancel} className={SECONDARY_BUTTON_CLASS}>
      취소
    </button>
    <button type="submit" disabled={disabled} className={PRIMARY_BUTTON_CLASS}>
      {submitLabel}
    </button>
  </div>
);

/* ------------------------------------------------------------------ *
 * 프로필 사진
 * ------------------------------------------------------------------ */

function AvatarEditor({ user }: { user: AuthUser }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const clearPreview = () => {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = event.target.files?.[0];
    if (!picked) return;
    setError("");
    if (!AVATAR_TYPES.includes(picked.type)) {
      setError("JPG, PNG, WEBP, GIF 사진만 올릴 수 있어요.");
      event.target.value = "";
      return;
    }
    if (picked.size > AVATAR_MAX_BYTES) {
      setError("사진은 5MB 이하로 올려 주세요.");
      event.target.value = "";
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    setFile(picked);
    setPreview(URL.createObjectURL(picked));
  };

  const remove = async () => {
    if (!window.confirm("프로필 사진을 삭제할까요? 기본 프로필로 바뀌어요.")) return;
    setSaving(true);
    setError("");
    try {
      applyUser(await deleteAvatar());
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    if (!file) return;
    setSaving(true);
    setError("");
    try {
      applyUser(await uploadAvatar(file));
      clearPreview();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="group relative rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2"
        aria-label="프로필 사진 선택"
      >
        <Avatar name={nicknameOf(user)} src={preview ?? mediaUrl(user.avatar)} size={80} />
        <span className="absolute bottom-0 right-0 flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-slate-700 text-white transition-colors group-hover:bg-indigo-600">
          <i className="fas fa-camera text-[11px]" aria-hidden="true" />
        </span>
      </button>
      <input ref={inputRef} type="file" accept={AVATAR_TYPES.join(",")} onChange={pick} className="sr-only" tabIndex={-1} />

      <div className="flex flex-col gap-2">
        {preview ? (
          <div className="flex gap-2">
            <button type="button" onClick={clearPreview} disabled={saving} className={SECONDARY_BUTTON_CLASS}>
              취소
            </button>
            <button type="button" onClick={save} disabled={saving} className={PRIMARY_BUTTON_CLASS}>
              {saving ? "저장 중…" : "사진 저장"}
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            <button type="button" onClick={() => inputRef.current?.click()} className={CHANGE_BUTTON_CLASS}>
              사진 변경
            </button>
            {user.avatar && (
              <button
                type="button"
                onClick={remove}
                disabled={saving}
                className={`${CHANGE_BUTTON_CLASS} text-rose-600 hover:border-rose-200 hover:bg-rose-50 disabled:opacity-50`}
              >
                사진 삭제
              </button>
            )}
          </div>
        )}
        {preview ? (
          <p className="text-xs text-slate-500">미리보기예요. 저장하면 반영돼요.</p>
        ) : (
          <p className="text-xs text-slate-400">JPG·PNG·WEBP·GIF, 5MB 이하</p>
        )}
        {error && <p className="text-xs text-rose-600">{error}</p>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * 닉네임
 * ------------------------------------------------------------------ */

function NicknameForm({ user, onDone }: { user: AuthUser; onDone: () => void }) {
  const [name, setName] = useState(user.name);
  // 중복 확인을 통과한 닉네임. 입력이 바뀌면 다시 확인한다.
  const [checkedName, setCheckedName] = useState("");
  const [message, setMessage] = useState({ error: "", success: "" });
  const [busy, setBusy] = useState(false);

  const value = name.trim();
  const formatError = value && !NICKNAME_PATTERN.test(value) ? NICKNAME_RULE_MESSAGE : "";

  const change = (next: string) => {
    setName(next);
    setCheckedName("");
    setMessage({ error: "", success: "" });
  };

  const check = async () => {
    if (!NICKNAME_PATTERN.test(value)) {
      setMessage({ error: NICKNAME_RULE_MESSAGE, success: "" });
      return;
    }
    setBusy(true);
    try {
      const { available } = await checkNickname(value);
      setCheckedName(available ? value : "");
      setMessage(available ? { error: "", success: "사용할 수 있는 닉네임이에요." } : { error: "이미 사용 중인 닉네임이에요.", success: "" });
    } catch (err) {
      setMessage({ error: firstError(errorDataOf(err), "name") ?? toErrorMessage(err), success: "" });
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (checkedName !== value) return;
    setBusy(true);
    try {
      applyUser(await updateNickname(value));
      onDone();
    } catch (err) {
      setMessage({ error: firstError(errorDataOf(err), "name") ?? toErrorMessage(err), success: "" });
      setBusy(false);
    }
  };

  const error = message.error || formatError;

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <div className="flex gap-2">
          <AuthInput
            aria-label="새 닉네임"
            value={name}
            maxLength={12}
            placeholder="한글·영문·숫자·밑줄 2~12자"
            error={error}
            autoFocus
            onChange={(event) => change(event.target.value)}
          />
          <button type="button" onClick={check} disabled={busy || !value} className={SIDE_BUTTON_CLASS}>
            중복 확인
          </button>
        </div>
        {error ? (
          <p className="mt-1 text-xs text-rose-600">{error}</p>
        ) : message.success ? (
          <p className="mt-1 text-xs text-emerald-600">{message.success}</p>
        ) : (
          <p className="mt-1 text-xs text-slate-400">중복 확인 후 저장할 수 있어요.</p>
        )}
      </div>
      <FormActions onCancel={onDone} submitLabel="저장" disabled={busy || checkedName !== value} />
    </form>
  );
}

/* ------------------------------------------------------------------ *
 * 이메일
 * ------------------------------------------------------------------ */

type EmailStep = { step: "password" } | { step: "email"; ticket: string } | { step: "sent"; email: string; debugLink?: string };

/**
 * 이메일 변경 모달.
 * 1) 현재 비밀번호 확인 → 2) 새 이메일 입력 후 [이메일 변경] → 3) 새 이메일로 인증 메일 발송 안내.
 * 3단계에서 [인증메일 재전송]으로 다시 보내거나 [이메일 변경 취소]로 보낸 링크를 무효로 할 수 있다.
 * 메일의 '변경 이메일 인증하기'를 누르면 마이페이지(?email_token=)로 돌아와 변경을 마친다.
 */
function EmailChangeDialog({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<EmailStep>({ step: "password" });
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const fieldError = (err: unknown, field: string) => firstError(errorDataOf(err), field) ?? toErrorMessage(err);

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (!password) {
      setError("현재 비밀번호를 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { password_ticket: ticket } = await checkEmailChangePassword(password);
      setPassword("");
      setState({ step: "email", ticket });
    } catch (err) {
      setError(fieldError(err, "password"));
    } finally {
      setBusy(false);
    }
  };

  const submitEmail = async (event: FormEvent) => {
    event.preventDefault();
    if (state.step !== "email") return;
    const value = email.trim();
    if (!EMAIL_PATTERN.test(value)) {
      setError("이메일 형식이 올바르지 않아요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await requestEmailChange(value, state.ticket);
      setState({ step: "sent", email: result.email, debugLink: result.debug_link });
    } catch (err) {
      setError(fieldError(err, "email"));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await resendEmailChange();
      setState({ step: "sent", email: result.email, debugLink: result.debug_link });
      setNotice("인증 메일을 다시 보냈어요.");
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    setError("");
    try {
      await cancelEmailChange();
      onClose();
    } catch (err) {
      setError(toErrorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 px-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="email-change-title"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="email-change-title" className="text-base font-bold text-slate-900">
            이메일 변경
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="-mr-1 -mt-1 flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <i className="fas fa-times" aria-hidden="true" />
          </button>
        </div>

        {state.step === "password" && (
          <form onSubmit={submitPassword} className="mt-3 space-y-4" noValidate>
            <p className="text-sm leading-relaxed text-slate-600">본인 확인을 위해 현재 비밀번호를 입력해 주세요.</p>
            <div>
              <PasswordInput
                aria-label="현재 비밀번호"
                autoComplete="current-password"
                placeholder="현재 비밀번호"
                value={password}
                error={error}
                autoFocus
                onChange={(event) => setPassword(event.target.value)}
              />
              {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
            </div>
            <FormActions onCancel={onClose} submitLabel="확인" disabled={busy} />
          </form>
        )}

        {state.step === "email" && (
          <form onSubmit={submitEmail} className="mt-3 space-y-4" noValidate>
            <p className="text-sm leading-relaxed text-slate-600">
              변경할 이메일을 입력해 주세요. 그 주소로 인증 메일을 보내요.
            </p>
            <div>
              <AuthInput
                type="email"
                aria-label="변경할 이메일"
                autoComplete="email"
                placeholder="변경할 이메일"
                value={email}
                error={error}
                autoFocus
                onChange={(event) => setEmail(event.target.value)}
              />
              {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
            </div>
            <FormActions onCancel={onClose} submitLabel="이메일 변경" disabled={busy} />
          </form>
        )}

        {state.step === "sent" && (
          <div className="mt-3 space-y-4">
            <div role="status" className="rounded-xl bg-indigo-50 px-4 py-3 text-sm leading-relaxed text-indigo-900">
              <p>
                <b className="break-all">{state.email}</b>(으)로 인증 메일을 보냈어요.
              </p>
              <p className="mt-1 text-indigo-800">
                변경 이메일 인증 링크로 기존 계정에 로그인하면, 이메일 변경이 완료됩니다. 이후 새로운 이메일 주소로
                로그인할 수 있습니다.
              </p>
            </div>
            {state.debugLink && (
              <p className="break-all text-xs text-amber-600">
                개발 서버 인증 링크:{" "}
                <a href={state.debugLink} className="underline">
                  {state.debugLink}
                </a>
              </p>
            )}
            {notice && !error && <p className="text-xs text-emerald-600">{notice}</p>}
            {error && <p className="text-xs text-rose-600">{error}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={cancel} disabled={busy} className={SECONDARY_BUTTON_CLASS}>
                이메일 변경 취소
              </button>
              <button type="button" onClick={resend} disabled={busy} className={PRIMARY_BUTTON_CLASS}>
                인증메일 재전송
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** 결과 토스트를 보여 주는 시간(ms). 실패는 읽을 시간을 조금 더 준다. */
const TOAST_MS = { ok: 3000, error: 5000 };

/** 메일 링크(/mypage?email_token=)로 들어오면 이메일 변경을 마치고 결과를 토스트로 알린다. */
function useEmailChangeConfirm() {
  const [params, setParams] = useSearchParams();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  // 개발 모드(StrictMode)에서 effect가 두 번 돌아도 한 번만 요청한다(링크는 1회용).
  const handled = useRef("");
  const token = params.get("email_token");

  useEffect(() => {
    if (!token || handled.current === token) return;
    handled.current = token;
    // 새로고침해도 다시 요청하지 않도록 주소에서 토큰을 지운다.
    setParams({}, { replace: true });
    confirmEmailChange(token)
      .then((user) => {
        applyUser(user);
        setResult({ ok: true, message: "이메일 인증이 완료되었습니다." });
      })
      .catch((err: unknown) => setResult({ ok: false, message: toErrorMessage(err) }));
  }, [token, setParams]);

  // 토스트는 잠시 뒤 저절로 사라진다.
  useEffect(() => {
    if (!result) return undefined;
    const timer = setTimeout(() => setResult(null), result.ok ? TOAST_MS.ok : TOAST_MS.error);
    return () => clearTimeout(timer);
  }, [result]);

  return { result, confirming: Boolean(token) && !result };
}

/* ------------------------------------------------------------------ *
 * 휴대폰 번호
 * ------------------------------------------------------------------ */

/** 인증번호 확인을 마치면 바로 번호를 저장한다. */
function PhoneForm({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (phone: string, token: string) => {
    setSaving(true);
    setError("");
    try {
      applyUser(await changePhone(phone, token));
      onDone();
    } catch (err) {
      setError(toErrorMessage(err));
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <PhoneVerificationField
        id="mypage-phone"
        error={error}
        autoFocus
        onVerifiedChange={(verified) => verified && save(verified.phone, verified.token)}
      />
      {saving && <p className="text-xs text-slate-500">번호를 저장하는 중…</p>}
      <div className="flex justify-end">
        <button type="button" onClick={onDone} className={SECONDARY_BUTTON_CLASS}>
          취소
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * 화면
 * ------------------------------------------------------------------ */

type Editing = "name" | "email" | "phone" | null;

/** `/mypage` 마이페이지. 첫 단락: 기본정보(프로필 사진 · 닉네임 · 이메일 · 휴대폰 번호) 조회·변경 */
export default function MyPage() {
  const { user } = useAuth();
  const [editing, setEditing] = useState<Editing>(null);
  const emailConfirm = useEmailChangeConfirm();

  if (!user) return null;
  const close = () => setEditing(null);
  const changeButton = (target: Exclude<Editing, null>, label = "변경") =>
    editing === target ? null : (
      <button type="button" onClick={() => setEditing(target)} className={CHANGE_BUTTON_CLASS}>
        {label}
      </button>
    );
  const phone = user.phone ?? "";

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">마이페이지</h1>

      {emailConfirm.confirming && <p className="mt-4 text-sm text-slate-500">이메일 변경을 확인하는 중…</p>}
      {emailConfirm.result && (
        <div
          role={emailConfirm.result.ok ? "status" : "alert"}
          className={`fixed left-1/2 top-4 z-[60] w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-md px-6 py-3.5 text-[15px] text-white shadow-lg ${
            emailConfirm.result.ok ? "bg-indigo-500" : "bg-rose-500"
          }`}
        >
          {emailConfirm.result.message}
        </div>
      )}

      <section aria-labelledby="basic-info" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <h2 id="basic-info" className="mb-5 text-base font-bold text-slate-900">
          기본정보
        </h2>

        <dl className="divide-y divide-slate-100">
          <InfoRow label="프로필 사진">
            <AvatarEditor user={user} />
          </InfoRow>

          <InfoRow
            label="닉네임"
            action={changeButton("name")}
            editor={editing === "name" && <NicknameForm user={user} onDone={close} />}
          >
            <span className="truncate">{user.name}</span>
          </InfoRow>

          <InfoRow
            label="이메일"
            action={user.has_password ? changeButton("email") : null}
          >
            <span className="truncate">{user.email || <span className="text-slate-400">등록된 이메일이 없어요</span>}</span>
            {!user.has_password && (
              <span className="shrink-0 text-xs text-slate-400">소셜 로그인 계정은 이메일을 바꿀 수 없어요</span>
            )}
          </InfoRow>

          <InfoRow
            label="휴대폰 번호"
            action={changeButton("phone", phone ? "변경" : "등록")}
            editor={editing === "phone" && <PhoneForm onDone={close} />}
          >
            {phone ? (
              <>
                <span className="tabular-nums">{formatPhone(phone)}</span>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                  <i className="fas fa-check text-[9px]" aria-hidden="true" />
                  인증 완료
                </span>
              </>
            ) : (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">미인증</span>
            )}
          </InfoRow>
        </dl>
      </section>

      {editing === "email" && <EmailChangeDialog onClose={close} />}
    </div>
  );
}
