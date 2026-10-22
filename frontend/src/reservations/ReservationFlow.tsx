import { useState } from "react";
import { toErrorMessage, validateReservation } from "../api/client";
import type { FlightBooking, HotelBooking, ReservationKind, ReservationResult } from "../types/api";
import FlightReview from "./FlightReview";
import HotelReview from "./HotelReview";
import ReservationUpload from "./ReservationUpload";
import { emptyFlight, emptyHotel } from "./reservationUtils";

type Step =
  | { phase: "upload" }
  | { phase: "review"; original: FlightBooking | HotelBooking; draft: FlightBooking | HotelBooking; result: ReservationResult; manual: boolean };

interface ReservationFlowProps {
  /** 사용자가 확인을 마쳐 서버 검증을 통과한 예약 정보가 나오면 호출된다(2·3단계가 이 값을 여행 생성·추가에 쓴다). */
  onConfirmed: (result: ReservationResult) => void;
}

const KIND_LABEL: Record<ReservationKind, string> = { flight: "항공권", hotel: "숙소" };

/**
 * 예약 확인서 분석 → 확인·수정 → 검증 흐름. 업로드와 확인 화면을 묶은 재사용 컴포넌트다.
 * 여행·항공편·숙소에는 저장하지 않고, 검증된 예약 정보 객체만 onConfirmed로 넘긴다.
 */
export default function ReservationFlow({ onConfirmed }: ReservationFlowProps) {
  const [kind, setKind] = useState<ReservationKind>("flight");
  const [step, setStep] = useState<Step>({ phase: "upload" });
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState("");

  const reset = () => {
    setStep({ phase: "upload" });
    setMessage("");
  };

  const startManual = () =>
    setStep(() => {
      const empty = kind === "flight" ? emptyFlight() : emptyHotel();
      return { phase: "review", original: empty, draft: empty, result: { kind, document: empty, valid: false, errors: [], warnings: [] }, manual: true };
    });

  const confirm = async () => {
    if (step.phase !== "review") return;
    setChecking(true);
    setMessage("");
    try {
      const result = await validateReservation(kind, step.draft);
      setStep({ ...step, draft: result.document, result });
      if (result.valid) onConfirmed(result);
      else setMessage("입력 칸의 오류를 고친 뒤 다시 확인해 주세요.");
    } catch (error) {
      setMessage(toErrorMessage(error));
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-xl bg-slate-100 p-0.5" role="group" aria-label="예약 종류">
        {(["flight", "hotel"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => {
              setKind(item);
              reset();
            }}
            aria-pressed={kind === item}
            className={`rounded-[10px] px-4 py-1.5 text-sm font-semibold transition-colors ${
              kind === item ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {KIND_LABEL[item]}
          </button>
        ))}
      </div>

      {step.phase === "upload" ? (
        <ReservationUpload
          key={kind}
          kind={kind}
          onManual={startManual}
          onAnalyzed={(result) =>
            setStep({ phase: "review", original: result.document, draft: result.document, result, manual: false })
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600">
              {step.manual
                ? "예약 정보를 직접 입력해 주세요."
                : "문서에서 읽은 값이에요. 비어 있거나 틀린 값은 고쳐 주세요."}
            </p>
            <button type="button" onClick={reset} className="text-sm font-medium text-slate-500 hover:text-slate-800">
              다시 업로드
            </button>
          </div>

          {kind === "flight" ? (
            <FlightReview
              original={step.original as FlightBooking}
              value={step.draft as FlightBooking}
              errors={step.result.errors}
              warnings={step.result.warnings}
              onChange={(draft) => setStep({ ...step, draft })}
            />
          ) : (
            <HotelReview
              original={step.original as HotelBooking}
              value={step.draft as HotelBooking}
              errors={step.result.errors}
              warnings={step.result.warnings}
              onChange={(draft) => setStep({ ...step, draft })}
            />
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={confirm}
              disabled={checking}
              className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
            >
              {checking ? "확인 중…" : "예약 정보 확인"}
            </button>
            {message && (
              <p role="alert" className="text-sm text-rose-600">
                {message}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
