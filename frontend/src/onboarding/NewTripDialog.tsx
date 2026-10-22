import { useEffect, useState } from "react";
import { getReservationConfig } from "../api/client";
import ReservationTripWizard from "../reservations/ReservationTripWizard";
import type { Trip } from "../types/api";
import OnboardingWizard from "./OnboardingWizard";

interface NewTripDialogProps {
  onComplete: (trip: Trip, notice?: string) => void;
  onClose: () => void;
}

type Mode = "loading" | "choose" | "direct" | "reservation";

/**
 * 새 여행 만들기: '직접 등록'(기존 3단계 그대로)과 '예약 정보로 만들기'(예약 확인서 업로드)를 고른다.
 * 예약 확인서 기능이 꺼져 있거나 확인하지 못하면 고르지 않고 바로 직접 등록을 연다(지금과 같은 화면).
 */
export default function NewTripDialog({ onComplete, onClose }: NewTripDialogProps) {
  const [mode, setMode] = useState<Mode>("loading");

  useEffect(() => {
    let cancelled = false;
    getReservationConfig()
      .then((config) => !cancelled && setMode(config.enabled ? "choose" : "direct"))
      .catch(() => !cancelled && setMode("direct"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (mode === "direct") return <OnboardingWizard onComplete={onComplete} onClose={onClose} />;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/30">
      <div className="flex min-h-full items-start justify-center px-4 py-8 sm:py-16">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="새 여행 만들기"
          className={`w-full rounded-2xl bg-white p-5 shadow-xl sm:p-7 ${mode === "reservation" ? "max-w-2xl" : "max-w-md"}`}
        >
          <div className="mb-4 flex items-center justify-between">
            <h1 className="text-sm font-semibold text-slate-500">새 여행 만들기</h1>
            <button
              type="button"
              onClick={onClose}
              aria-label="닫기"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <i className="fas fa-times" aria-hidden="true" />
            </button>
          </div>

          {mode === "loading" && <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />}

          {mode === "choose" && (
            <div className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900">어떻게 만들까요?</h2>
              {(
                [
                  ["direct", "fas fa-pen", "직접 등록", "여행지·날짜·항공권·숙소를 차례로 입력해요."],
                  ["reservation", "fas fa-file-upload", "예약 정보로 만들기", "항공권(필수)·숙소 예약 확인서를 올리면 일정을 채워 드려요."],
                ] as const
              ).map(([key, icon, title, description]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setMode(key)}
                  className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 p-4 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50/40"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600" aria-hidden="true">
                    <i className={icon} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-bold text-slate-900">{title}</span>
                    <span className="block text-xs text-slate-500">{description}</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          {mode === "reservation" && (
            <ReservationTripWizard onComplete={(trip) => onComplete(trip)} onBack={() => setMode("direct")} />
          )}
        </div>
      </div>
    </div>
  );
}
