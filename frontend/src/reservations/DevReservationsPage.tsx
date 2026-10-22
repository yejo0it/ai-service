import { useState } from "react";
import { PAGE_CONTAINER_CLASS } from "../components/layout/pageContainer";
import type { ReservationResult } from "../types/api";
import ReservationFlow from "./ReservationFlow";

/**
 * `/dev/reservations` 개발용 화면(개발 모드에서만 등록된다). 예약 확인서 분석 1단계를 확인한다:
 * 업로드 → 추출 결과 확인·수정 → 서버 검증 → 최종 '검증된 예약 정보 객체' 확인. 여행에는 저장하지 않는다.
 */
export default function DevReservationsPage() {
  const [confirmed, setConfirmed] = useState<ReservationResult | null>(null);

  return (
    <div className={`${PAGE_CONTAINER_CLASS} py-6 sm:py-8`}>
      <div className="mb-6">
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700">개발용</span>
        <h1 className="mt-2 text-2xl font-bold text-slate-900 sm:text-3xl">예약 확인서 분석</h1>
        <p className="mt-1 text-sm text-slate-500">
          항공권·숙소 예약 확인서에서 정보를 읽어 확인하고 고칩니다. 여행에는 저장하지 않아요.
        </p>
      </div>

      <div className="mx-auto max-w-3xl space-y-6">
        <ReservationFlow onConfirmed={setConfirmed} />

        {confirmed && (
          <section aria-label="검증된 예약 정보" className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-4">
            <h2 className="text-sm font-bold text-emerald-800">검증된 예약 정보 (다음 단계에 전달할 객체)</h2>
            <pre className="mt-2 max-h-96 overflow-auto rounded-xl bg-white p-3 text-xs text-slate-700">
              {JSON.stringify({ kind: confirmed.kind, document: confirmed.document }, null, 2)}
            </pre>
          </section>
        )}
      </div>
    </div>
  );
}
