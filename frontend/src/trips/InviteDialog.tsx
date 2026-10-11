import { useEffect, useRef, useState } from "react";
import { createTripInvitation, getTripMembers, removeTripMember, toErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { tripInviteUrl } from "../routes";
import type { Trip, TripMembers } from "../types/api";
import { formatMonthDay } from "../utils/date";
import { isKakaoShareConfigured, shareToKakao } from "./kakaoShare";

interface InviteDialogProps {
  trip: Trip;
  onClose: () => void;
  /** 일행이 스스로 나간 뒤 (상세 화면을 떠난다) */
  onLeft: () => void;
}

const SECONDARY_BUTTON =
  "rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50";

/**
 * 일행 초대하기 모달.
 * - 카카오톡으로 초대하기(여행 제목·일정·초대 링크) · 초대 링크 복사
 * - 함께하는 일행 수(만든 사람 제외, 최대 10명)와 목록. 만든 사람은 내보내기, 일행은 나가기
 * - 링크는 여행마다 하나, 7일 동안 쓸 수 있다. 만든 사람이 열 때 쓸 수 있는 링크가 없으면 새로 만든다.
 */
export default function InviteDialog({ trip, onClose, onLeft }: InviteDialogProps) {
  const { user } = useAuth();
  const [data, setData] = useState<TripMembers | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // 만든 사람이 열면 쓸 수 있는 링크를 받아 둔다(없거나 만료됐으면 새로 만든다).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const members = await getTripMembers(trip.id);
        const invitation =
          members.is_owner && !members.invitation ? await createTripInvitation(trip.id) : members.invitation;
        if (!cancelled) setData({ ...members, invitation });
      } catch (err) {
        if (!cancelled) setError(toErrorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [trip.id]);

  const link = data?.invitation ? tripInviteUrl(data.invitation.token) : "";
  const full = data ? data.members.length >= data.max_members : false;
  const kakaoReady = isKakaoShareConfigured();

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error && !("isAxiosError" in err) ? err.message : toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const copyLink = () =>
    run(async () => {
      try {
        await navigator.clipboard.writeText(link);
        setNotice("초대 링크를 복사했어요.");
      } catch {
        throw new Error("복사하지 못했어요. 잠시 후 다시 시도해 주세요.");
      }
    });

  const shareKakao = () =>
    run(() =>
      shareToKakao({
        text: `[PinRoute] ${trip.destination_label} 여행에 함께해요!\n${formatMonthDay(trip.start_date)} ~ ${formatMonthDay(
          trip.end_date,
        )} · ${trip.nights}박 ${trip.nights + 1}일\n링크를 열고 로그인하면 함께 일정을 짤 수 있어요.`,
        url: link,
        buttonTitle: "여행 함께하기",
      }),
    );

  const removeMember = (userId: number) =>
    run(async () => {
      await removeTripMember(trip.id, userId);
      setConfirmingId(null);
      if (userId === user?.id) {
        onLeft();
        return;
      }
      setData((current) =>
        current ? { ...current, members: current.members.filter((member) => member.id !== userId) } : current,
      );
    });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 px-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="invite-title"
        onClick={(event) => event.stopPropagation()}
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id="invite-title" className="text-base font-bold text-slate-900">
            일행 초대하기
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="-mr-1 -mt-1 flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <i className="fas fa-times" aria-hidden="true" />
          </button>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          초대받은 일행도 PinRoute 회원가입/로그인 후 함께 여행을 수정할 수 있어요.
        </p>

        {!data && !error && <p className="mt-5 text-sm text-slate-400">불러오는 중...</p>}

        {data && (
          <>
            {/* 초대 */}
            <div className="mt-5 space-y-2">
              {full ? (
                <p className="rounded-xl bg-amber-50 px-3 py-2.5 text-sm text-amber-700">
                  일행이 가득 찼어요. (최대 {data.max_members}명)
                </p>
              ) : !link ? (
                <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-600">
                  지금 쓸 수 있는 초대 링크가 없어요. 여행을 만든 일행에게 초대 링크를 요청해 주세요.
                </p>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={shareKakao}
                    disabled={busy || !kakaoReady}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#FEE500] py-3 text-sm font-semibold text-[#191919] transition-colors hover:bg-[#F5DC00] disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    <i className="fas fa-comment" aria-hidden="true" />
                    카카오톡으로 초대하기
                  </button>
                  {!kakaoReady && (
                    <p className="text-center text-xs text-slate-400">
                      카카오톡 공유를 준비 중이에요. 링크 복사를 이용해 주세요.
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={copyLink}
                    disabled={busy}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
                  >
                    <i className="fas fa-link text-xs" aria-hidden="true" />
                    초대 링크 복사
                  </button>
                </>
              )}
              {notice && (
                <p role="status" className="text-xs text-emerald-600">
                  {notice}
                </p>
              )}
            </div>

            {/* 일행 목록 */}
            <div className="mt-6">
              <h3 className="flex items-baseline justify-between text-sm font-semibold text-slate-900">
                함께하는 일행
                <span className="text-xs font-medium tabular-nums text-slate-500">
                  {data.members.length} / {data.max_members}명
                </span>
              </h3>
              <ul className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-200">
                {data.owner && (
                  <li className="flex items-center gap-2 px-3 py-2.5 text-sm">
                    <span className="truncate text-slate-800">{data.owner.name}</span>
                    <span className="shrink-0 rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-600">
                      만든 사람
                    </span>
                    {data.owner.id === user?.id && <span className="shrink-0 text-xs text-slate-400">나</span>}
                  </li>
                )}
                {data.members.map((member) => {
                  const isMe = member.id === user?.id;
                  const canRemove = data.is_owner || isMe;
                  return (
                    <li key={member.id} className="flex items-center gap-2 px-3 py-2.5 text-sm">
                      <span className="min-w-0 flex-1 truncate text-slate-800">
                        {member.name}
                        {isMe && <span className="ml-1.5 text-xs text-slate-400">나</span>}
                      </span>
                      {canRemove &&
                        (confirmingId === member.id ? (
                          <span className="flex shrink-0 items-center gap-1.5">
                            <button type="button" onClick={() => setConfirmingId(null)} disabled={busy} className={SECONDARY_BUTTON}>
                              취소
                            </button>
                            <button
                              type="button"
                              onClick={() => removeMember(member.id)}
                              disabled={busy}
                              className="rounded-lg bg-rose-500 px-2.5 py-1 text-xs font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
                            >
                              {isMe ? "나가기" : "내보내기"}
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setConfirmingId(member.id)}
                            disabled={busy}
                            aria-label={isMe ? "이 여행에서 나가기" : `${member.name} 내보내기`}
                            className={SECONDARY_BUTTON}
                          >
                            {isMe ? "나가기" : "내보내기"}
                          </button>
                        ))}
                    </li>
                  );
                })}
                {data.members.length === 0 && (
                  <li className="px-3 py-2.5 text-xs text-slate-400">아직 함께하는 일행이 없어요.</li>
                )}
              </ul>
              {confirmingId !== null && (
                <p className="mt-1.5 text-xs text-slate-500">
                  {confirmingId === user?.id
                    ? "나가면 이 여행을 볼 수 없어요. 다시 함께하려면 초대 링크가 필요해요."
                    : "내보낸 일행은 이 여행을 볼 수 없어요."}
                </p>
              )}
            </div>
          </>
        )}

        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
      </div>
    </div>
  );
}
