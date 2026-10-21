import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteTrip, toErrorMessage } from "../api/client";
import { tripDetailPath } from "../routes";
import type { Trip } from "../types/api";
import { formatMonthDay, todayISODate } from "../utils/date";
import type { TripDetailState } from "./TripDetailPage";
import { dDayLabel, tripColor, tripStatus, type TripStatus } from "./tripUtils";
import useTrips from "./useTrips";
import { PAGE_CONTAINER_CLASS } from "../components/layout/pageContainer";

const SECTIONS: { status: TripStatus; title: string }[] = [
  { status: "ongoing", title: "여행 중" },
  { status: "upcoming", title: "다가오는 여행" },
  { status: "past", title: "지난 여행" },
];

interface TripListItemProps {
  trip: Trip;
  today: string;
  /** 삭제가 끝나면 목록에서 뺀다 */
  onDeleted: (tripId: number) => void;
}

/** 여행 카드: 카드 전체를 누르면 상세로 이동, 왼쪽 아래 휴지통은 한 번 더 확인한 뒤 삭제한다. */
function TripListItem({ trip, today, onDeleted }: TripListItemProps) {
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const remove = async () => {
    setDeleting(true);
    setError("");
    try {
      await deleteTrip(trip.id);
      onDeleted(trip.id);
    } catch (err) {
      setError(toErrorMessage(err));
      setDeleting(false);
    }
  };

  return (
    <li className="flex">
      <div className="relative flex min-w-0 flex-1 flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-colors hover:border-slate-300">
        {/* 버튼을 카드 전체로 넓혀(after) 어디를 눌러도 상세로 간다. 삭제 버튼은 그 위(z-10)에 둔다. */}
        <button
          type="button"
          onClick={() => navigate(tripDetailPath(trip.id), { state: { trip } satisfies TripDetailState })}
          className="min-w-0 text-left after:absolute after:inset-0 after:rounded-2xl"
        >
          <span className="flex items-center justify-between gap-3">
            <span className={`h-1.5 w-10 shrink-0 rounded-full ${tripColor(trip).dot}`} aria-hidden="true" />
            <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
              {dDayLabel(trip, today)}
            </span>
          </span>
          <span className="mt-4 block truncate text-lg font-semibold text-slate-900">{trip.destination_label}</span>
          <span className="mt-1 block text-sm text-slate-500">
            {formatMonthDay(trip.start_date)} ~ {formatMonthDay(trip.end_date)} · {trip.nights}박 {trip.nights + 1}일
          </span>
        </button>

        <div className="mt-3 flex min-h-9 items-center justify-between gap-2">
          {confirming ? (
            <div className="relative z-10 flex items-center gap-1.5" role="group" aria-label="삭제 확인">
              <span className="text-xs text-slate-500">삭제할까요?</span>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={deleting}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={deleting}
                className="rounded-lg bg-rose-500 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
              >
                {deleting ? "삭제 중" : "삭제"}
              </button>
            </div>
          ) : trip.is_owner ? (
            // 여행 삭제는 만든 회원만 한다 (초대받은 일행은 상세의 일행 초대하기에서 나갈 수 있다)
            <button
              type="button"
              onClick={() => setConfirming(true)}
              aria-label={`${trip.destination_label} 여행 삭제`}
              title="삭제"
              className="relative z-10 -ml-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-rose-50 hover:text-rose-500"
            >
              <i className="far fa-trash-alt" aria-hidden="true" />
            </button>
          ) : (
            <span />
          )}
          <span className="ml-auto flex items-center gap-1 text-sm text-slate-500" aria-hidden="true">
            상세 보기
            <i className="fas fa-arrow-right text-xs" />
          </span>
        </div>
        {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
      </div>
    </li>
  );
}

/** `/trips` 내 여행 목록: 여행 중 · 다가오는 여행 · 지난 여행 */
export default function MyTripsPage() {
  const tripsState = useTrips();
  const today = todayISODate();

  return (
    <div className={`${PAGE_CONTAINER_CLASS} py-6 sm:py-8`}>
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">내 여행</h1>
          <p className="mt-1 text-sm text-slate-500">등록한 여행을 모아 봤어요.</p>
        </div>
      </div>

      {tripsState.status === "loading" && (
        <div className="grid gap-3 md:grid-cols-2 md:gap-4">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="h-36 animate-pulse rounded-2xl bg-slate-200/70" />
          ))}
        </div>
      )}

      {tripsState.status === "error" && (
        <div role="alert" className="rounded-2xl border border-rose-100 bg-rose-50 p-6 text-center">
          <p className="text-sm text-rose-700">{tripsState.message}</p>
          <button
            type="button"
            onClick={tripsState.reload}
            className="mt-3 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
          >
            다시 불러오기
          </button>
        </div>
      )}

      {tripsState.status === "ready" && tripsState.trips.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <p className="font-semibold text-slate-800">등록된 여행이 없습니다</p>
          <p className="mt-1 text-sm text-slate-500">첫 여행을 만들어 보세요.</p>
        </div>
      )}

      {tripsState.status === "ready" &&
        SECTIONS.map(({ status, title }) => {
          const trips = tripsState.trips.filter((trip) => tripStatus(trip, today) === status);
          if (trips.length === 0) return null;
          // 지난 여행은 최근 것부터 보여준다.
          const ordered = status === "past" ? [...trips].reverse() : trips;
          return (
            <section key={status} className="mb-8">
              <h2 className="mb-3 text-sm font-semibold text-slate-500">
                {title} <span className="text-slate-400">{trips.length}</span>
              </h2>
              <ul className="grid gap-3 md:grid-cols-2 md:gap-4">
                {ordered.map((trip) => (
                  <TripListItem key={trip.id} trip={trip} today={today} onDeleted={tripsState.removeTrip} />
                ))}
              </ul>
            </section>
          );
        })}
    </div>
  );
}
