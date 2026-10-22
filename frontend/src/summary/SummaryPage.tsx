import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  deleteTripPhoto,
  getTripPhotoBlob,
  getTripSummary,
  replaceTripPhoto,
  saveTripMemo,
  toErrorMessage,
  uploadTripPhoto,
} from "../api/client";
import type { Trip, TripPhoto, TripSummary } from "../types/api";

const CARD_CLASS = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";
const MEMO_MAX = 300;
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

/** 업로드 전에 걸러 바로 알려 준다(서버도 같은 규칙으로 다시 확인한다). */
const fileError = (file: File) =>
  !ACCEPTED_TYPES.includes(file.type)
    ? "JPG, PNG, WEBP, GIF 사진만 올릴 수 있어요."
    : file.size > MAX_UPLOAD_BYTES
      ? "사진은 5MB 이하로 올려 주세요."
      : "";

/** 공개 주소가 없는 사진을 로그인 토큰으로 받아 보여 준다. 사진이 바뀌면(url의 v 값) 다시 받는다. */
function AuthImage({ url, alt }: { url: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setSrc(null);
    setFailed(false);
    getTripPhotoBlob(url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (failed) {
    return (
      <span className="flex h-full w-full items-center justify-center bg-slate-100 px-2 text-center text-xs text-slate-400">
        사진을 불러오지 못했어요
      </span>
    );
  }
  if (!src) return <span className="block h-full w-full animate-pulse bg-slate-100" aria-hidden="true" />;
  return <img src={src} alt={alt} className="h-full w-full object-cover" />;
}

interface PhotoSlotProps {
  photo: TripPhoto | null;
  index: number;
  busy: boolean;
  disabled: boolean;
  onPick: (file: File, photo: TripPhoto | null) => void;
  onDelete: (photo: TripPhoto) => void;
}

/** 사진 한 칸: 사진이 있으면 미리보기와 교체·삭제, 없으면 사진 추가 */
function PhotoSlot({ photo, index, busy, disabled, onPick, onDelete }: PhotoSlotProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [confirming, setConfirming] = useState(false);

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // 같은 파일을 다시 골라도 반응하도록
    if (file) onPick(file, photo);
  };

  const input = (
    <input
      ref={inputRef}
      type="file"
      accept={ACCEPTED_TYPES.join(",")}
      onChange={pick}
      className="hidden"
      aria-label={photo ? `사진 ${index + 1} 교체` : `사진 ${index + 1} 추가`}
    />
  );

  if (!photo) {
    return (
      <div>
        {input}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || busy}
          className="flex aspect-square w-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-slate-300 text-slate-400 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <i className={busy ? "fas fa-spinner fa-spin" : "fas fa-plus"} aria-hidden="true" />
          <span className="text-xs font-medium">{busy ? "올리는 중…" : "사진 추가"}</span>
        </button>
      </div>
    );
  }

  return (
    <div>
      {input}
      <div className="relative aspect-square overflow-hidden rounded-xl bg-slate-100">
        <AuthImage url={photo.url} alt={`여행 사진 ${index + 1}`} />
        {busy && (
          <span className="absolute inset-0 flex items-center justify-center bg-white/70 text-sm text-slate-500">
            <i className="fas fa-spinner fa-spin" aria-hidden="true" />
          </span>
        )}
        {confirming ? (
          <div
            className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-slate-900/70 px-2 py-1.5"
            role="group"
            aria-label="삭제 확인"
          >
            <span className="text-xs text-white">삭제할까요?</span>
            <span className="flex gap-1">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded-md bg-white/20 px-2 py-1 text-xs text-white hover:bg-white/30"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  onDelete(photo);
                }}
                className="rounded-md bg-rose-500 px-2 py-1 text-xs font-semibold text-white hover:bg-rose-600"
              >
                삭제
              </button>
            </span>
          </div>
        ) : (
          <div className="absolute right-1.5 top-1.5 flex gap-1">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={disabled || busy}
              aria-label={`사진 ${index + 1} 교체`}
              title="교체"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/90 text-slate-600 shadow-sm hover:bg-white disabled:opacity-50"
            >
              <i className="fas fa-sync-alt text-xs" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              disabled={disabled || busy}
              aria-label={`사진 ${index + 1} 삭제`}
              title="삭제"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/90 text-slate-600 shadow-sm hover:bg-white hover:text-rose-500 disabled:opacity-50"
            >
              <i className="far fa-trash-alt text-xs" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** 여행 상세 `여행 요약` 탭: 여행 사진(최대 3장)과 한 줄 메모. 여행 시작일부터 쓰고 고친다. */
export default function SummaryPage({ trip }: { trip: Trip }) {
  const [summary, setSummary] = useState<TripSummary | null>(null);
  const [loadError, setLoadError] = useState("");
  const [memo, setMemo] = useState("");
  const [savedMemo, setSavedMemo] = useState("");
  const [savingMemo, setSavingMemo] = useState(false);
  const [memoNotice, setMemoNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busySlot, setBusySlot] = useState<number | null>(null);
  const [photoError, setPhotoError] = useState("");

  const load = useCallback(() => {
    let cancelled = false;
    setLoadError("");
    getTripSummary(trip.id)
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setMemo(data.memo);
        setSavedMemo(data.memo);
      })
      .catch((err: unknown) => !cancelled && setLoadError(toErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [trip.id]);
  useEffect(() => load(), [load]);

  // 저장 성공 안내는 잠시 뒤 사라진다.
  useEffect(() => {
    if (!memoNotice?.ok) return undefined;
    const timer = window.setTimeout(() => setMemoNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [memoNotice]);

  if (!summary) {
    return loadError ? (
      <div role="alert" className="rounded-2xl border border-rose-100 bg-rose-50 p-6 text-center">
        <p className="text-sm text-rose-700">{loadError}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
        >
          다시 불러오기
        </button>
      </div>
    ) : (
      <div className="space-y-4">
        <div className="h-56 animate-pulse rounded-2xl bg-slate-200/70" />
        <div className="h-40 animate-pulse rounded-2xl bg-slate-200/70" />
      </div>
    );
  }

  const writable = summary.writable;
  const changed = memo.trim() !== savedMemo;

  const saveMemo = async () => {
    if (!changed || savingMemo) return;
    setSavingMemo(true);
    setMemoNotice(null);
    try {
      const data = await saveTripMemo(trip.id, memo);
      setSummary((current) => (current ? { ...current, memo: data.memo } : current));
      setMemo(data.memo);
      setSavedMemo(data.memo);
      setMemoNotice({ ok: true, text: data.memo ? "메모를 저장했어요." : "메모를 지웠어요." });
    } catch (err) {
      setMemoNotice({ ok: false, text: toErrorMessage(err) });
    } finally {
      setSavingMemo(false);
    }
  };

  // 빈 칸의 사진은 새로 올리고, 있는 사진은 같은 자리에 교체한다.
  const pickPhoto = async (file: File, photo: TripPhoto | null, slot: number) => {
    const problem = fileError(file);
    if (problem) {
      setPhotoError(problem);
      return;
    }
    setPhotoError("");
    setBusySlot(slot);
    try {
      const saved = photo ? await replaceTripPhoto(trip.id, photo.id, file) : await uploadTripPhoto(trip.id, file);
      setSummary((current) =>
        current
          ? {
              ...current,
              photos: photo
                ? current.photos.map((item) => (item.id === photo.id ? saved : item))
                : [...current.photos, saved],
            }
          : current,
      );
    } catch (err) {
      setPhotoError(toErrorMessage(err));
    } finally {
      setBusySlot(null);
    }
  };

  const removePhoto = async (photo: TripPhoto, slot: number) => {
    setPhotoError("");
    setBusySlot(slot);
    try {
      await deleteTripPhoto(trip.id, photo.id);
      load(); // 남은 사진의 순서가 앞으로 당겨지므로 다시 불러온다.
    } catch (err) {
      setPhotoError(toErrorMessage(err));
    } finally {
      setBusySlot(null);
    }
  };

  const slots = Array.from({ length: summary.max_photos }, (_, index) => summary.photos[index] ?? null);

  return (
    <div className="space-y-4">
      <section aria-label="여행 사진" className={CARD_CLASS}>
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-base font-bold text-slate-900">여행 사진</h2>
          <span className="text-xs text-slate-400">
            {summary.photos.length}/{summary.max_photos}장 · 5MB 이하 JPG·PNG·WEBP·GIF
          </span>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {slots.map((photo, index) => (
            <PhotoSlot
              key={photo?.id ?? `empty-${index}`}
              photo={photo}
              index={index}
              busy={busySlot === index}
              disabled={!writable || busySlot !== null}
              onPick={(file, target) => pickPhoto(file, target, index)}
              onDelete={(target) => removePhoto(target, index)}
            />
          ))}
        </div>
        {summary.photos.length === 0 && (
          <p className="mt-3 text-sm text-slate-500">아직 올린 사진이 없어요. 여행의 한 장면을 남겨 보세요.</p>
        )}
        {photoError && (
          <p role="alert" className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">
            {photoError}
          </p>
        )}
      </section>

      <section aria-label="한 줄 메모" className={CARD_CLASS}>
        <div className="flex items-baseline justify-between gap-3">
          <label htmlFor="trip-memo" className="text-base font-bold text-slate-900">
            한 줄 메모
          </label>
          <span className="text-xs tabular-nums text-slate-400">
            {memo.length}/{MEMO_MAX}
          </span>
        </div>
        {savedMemo === "" && (
          <p className="mt-1 text-sm text-slate-500">아직 남긴 메모가 없어요. 이번 여행을 한 줄로 기록해 보세요.</p>
        )}
        <textarea
          id="trip-memo"
          value={memo}
          onChange={(event) => {
            setMemo(event.target.value.slice(0, MEMO_MAX));
            setMemoNotice(null);
          }}
          maxLength={MEMO_MAX}
          rows={3}
          disabled={!writable}
          placeholder="예) 첫날 먹은 라멘이 이번 여행 최고였다"
          className="mt-3 w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p
            role={memoNotice && !memoNotice.ok ? "alert" : "status"}
            className={`min-w-0 text-sm ${memoNotice?.ok ? "text-emerald-600" : "text-rose-600"}`}
          >
            {memoNotice?.text}
          </p>
          <button
            type="button"
            onClick={saveMemo}
            disabled={!writable || !changed || savingMemo}
            className="shrink-0 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            {savingMemo ? "저장 중…" : "저장"}
          </button>
        </div>
      </section>
    </div>
  );
}
