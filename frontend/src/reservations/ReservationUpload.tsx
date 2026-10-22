import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { analyzeReservation, toErrorMessage } from "../api/client";
import type { ReservationKind, ReservationResult } from "../types/api";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "application/pdf,image/jpeg,image/png,image/webp";
const ALLOWED = ["application/pdf", "image/jpeg", "image/png", "image/webp"];

const KIND_TEXT: Record<ReservationKind, { title: string; icon: string; hint: string }> = {
  flight: { title: "항공권 예약 확인서", icon: "fas fa-plane", hint: "왕복·경유·다구간 항공권도 구간별로 읽어 와요." },
  hotel: { title: "숙소 예약 확인서", icon: "fas fa-bed", hint: "숙소 이름·주소와 체크인·체크아웃 날짜를 읽어 와요." },
};

/** 업로드 전에 걸러 바로 알려 준다(서버도 파일 내용으로 다시 확인한다). */
const fileProblem = (file: File) =>
  !ALLOWED.includes(file.type)
    ? "PDF, JPG, PNG, WEBP 파일만 올릴 수 있어요."
    : file.size > MAX_BYTES
      ? "파일은 10MB 이하로 올려 주세요."
      : "";

type Phase =
  | { status: "idle" }
  | { status: "analyzing"; file: File }
  | { status: "failed"; file: File | null; message: string };

interface ReservationUploadProps {
  kind: ReservationKind;
  /** 분석이 끝나면 호출된다(검증된 예약 정보와 오류·경고) */
  onAnalyzed: (result: ReservationResult) => void;
  /** 분석을 건너뛰고 직접 입력하기로 했을 때 */
  onManual: () => void;
  disabled?: boolean;
}

/**
 * 예약 확인서 업로드 칸(항공권 / 숙소). 파일 선택 → 분석 중(취소 가능) → 실패 시 재시도·직접 입력.
 * 여행 생성 화면과 분리된 독립 컴포넌트라 새 여행 만들기('예약 정보로 만들기')와 기존 여행에 추가 화면이 그대로 쓸 수 있다.
 */
export default function ReservationUpload({ kind, onAnalyzed, onManual, disabled = false }: ReservationUploadProps) {
  const [phase, setPhase] = useState<Phase>({ status: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const copy = KIND_TEXT[kind];

  // 화면을 떠나면 진행 중인 분석 요청을 취소한다.
  useEffect(() => () => abortRef.current?.abort(), []);

  const analyze = async (file: File) => {
    const problem = fileProblem(file);
    if (problem) {
      setPhase({ status: "failed", file, message: problem });
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase({ status: "analyzing", file });
    try {
      const result = await analyzeReservation(kind, file, controller.signal);
      if (controller.signal.aborted) return;
      setPhase({ status: "idle" });
      onAnalyzed(result);
    } catch (error) {
      if (controller.signal.aborted) return; // 사용자가 취소한 경우
      setPhase({ status: "failed", file, message: toErrorMessage(error) });
    }
  };

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // 같은 파일을 다시 골라도 반응하도록
    if (file) analyze(file);
  };

  const cancel = () => {
    abortRef.current?.abort();
    setPhase({ status: "idle" });
  };

  const busy = phase.status === "analyzing";
  return (
    <section aria-label={copy.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600" aria-hidden="true">
          <i className={copy.icon} />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-slate-900">{copy.title}</h3>
          <p className="text-xs text-slate-500">{copy.hint}</p>
        </div>
      </div>

      <input ref={inputRef} type="file" accept={ACCEPT} onChange={pick} className="hidden" aria-label={`${copy.title} 파일 선택`} />

      {phase.status === "analyzing" ? (
        <div className="mt-4 flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-3" role="status" aria-live="polite">
          <i className="fas fa-spinner fa-spin text-indigo-500" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-800">{phase.file.name}</p>
            <p className="text-xs text-slate-500">예약 정보를 읽고 있어요. 최대 1분쯤 걸려요.</p>
          </div>
          <button type="button" onClick={cancel} className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-white">
            취소
          </button>
        </div>
      ) : (
        <>
          {phase.status === "failed" && (
            <div role="alert" className="mt-4 rounded-xl bg-rose-50 px-3 py-3">
              {phase.file && <p className="truncate text-xs font-medium text-slate-600">{phase.file.name}</p>}
              <p className="mt-0.5 text-sm text-rose-700">{phase.message}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {phase.file && !fileProblem(phase.file) && (
                  <button
                    type="button"
                    onClick={() => phase.file && analyze(phase.file)}
                    disabled={disabled}
                    className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 shadow-sm hover:bg-rose-100"
                  >
                    다시 시도
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  disabled={disabled}
                  className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
                >
                  다른 파일 선택
                </button>
              </div>
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={disabled || busy}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
            >
              <i className="fas fa-file-upload text-xs" aria-hidden="true" />
              파일 선택
            </button>
            <button
              type="button"
              onClick={onManual}
              disabled={disabled}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              직접 입력
            </button>
            <span className="text-xs text-slate-400">PDF(5쪽 이하) · JPG · PNG · WEBP, 10MB 이하</span>
          </div>
        </>
      )}
    </section>
  );
}
