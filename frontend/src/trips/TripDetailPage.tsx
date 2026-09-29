import { Navigate, useLocation } from "react-router-dom";
import { ROUTES } from "../routes";
import type { Trip } from "../types/api";

/** 여행 상세로 이동할 때 넘기는 라우터 state */
export interface TripDetailState {
  trip: Trip;
}

/**
 * `/trips/:tripId` — 온보딩 완료 후 도착 화면이자 여행 요약.
 * (동선 최적화 화면이 붙기 전 임시 요약. 라우터 state 없이 들어오면 홈으로 보낸다.)
 */
export default function TripDetailPage() {
  const state = useLocation().state as TripDetailState | null;
  const trip = state?.trip;

  if (!trip) return <Navigate to={ROUTES.HOME} replace />;

  return (
    <div className="flex justify-center px-4 py-8 sm:py-12">
      <div className="w-full max-w-md rounded-2xl bg-white p-7 shadow-sm ring-1 ring-slate-100">
        <h1 className="text-xl font-bold text-slate-900">
          {trip.destination_label} 여행이 만들어졌어요
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {trip.start_date} ~ {trip.end_date} · {trip.nights}박
        </p>
        <ul className="mt-5 space-y-2 text-sm text-slate-700">
          <li>항공권 {trip.has_flight ? "등록됨" : "미등록"}</li>
          <li>
            숙소 {trip.hotels?.length ? `${trip.hotels.length}곳 등록됨` : "미등록"}
          </li>
        </ul>
      </div>
    </div>
  );
}
