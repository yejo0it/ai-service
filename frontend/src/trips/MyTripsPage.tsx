import { Link, useNavigate } from "react-router-dom";
import { ROUTES, tripDetailPath } from "../routes";
import type { Trip } from "../types/api";
import { formatMonthDay, todayISODate } from "../utils/date";
import type { TripDetailState } from "./TripDetailPage";
import { dDayLabel, tripColor, tripStatus, type TripStatus } from "./tripUtils";
import useTrips from "./useTrips";

const SECTIONS: { status: TripStatus; title: string }[] = [
  { status: "ongoing", title: "여행 중" },
  { status: "upcoming", title: "다가오는 여행" },
  { status: "past", title: "지난 여행" },
];

function TripListItem({ trip, today }: { trip: Trip; today: string }) {
  const navigate = useNavigate();
  return (
    <li>
      <button
        type="button"
        onClick={() => navigate(tripDetailPath(trip.id), { state: { trip } satisfies TripDetailState })}
        className="flex w-full items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-colors hover:border-slate-300"
      >
        <span className={`h-10 w-1.5 shrink-0 rounded-full ${tripColor(trip).dot}`} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold text-slate-900">{trip.destination_label}</span>
          <span className="mt-0.5 block text-sm text-slate-500">
            {formatMonthDay(trip.start_date)} ~ {formatMonthDay(trip.end_date)} · {trip.nights}박
          </span>
        </span>
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
          {dDayLabel(trip, today)}
        </span>
      </button>
    </li>
  );
}

/** `/trips` 내 여행 목록: 여행 중 · 다가오는 여행 · 지난 여행 */
export default function MyTripsPage() {
  const tripsState = useTrips();
  const today = todayISODate();

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">내 여행</h1>
          <p className="mt-1 text-sm text-slate-500">등록한 여행을 모아 봤어요.</p>
        </div>
        <Link
          to={ROUTES.ONBOARDING}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />새 여행
        </Link>
      </div>

      {tripsState.status === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((key) => (
            <div key={key} className="h-20 animate-pulse rounded-2xl bg-slate-200/70" />
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
              <ul className="space-y-3">
                {ordered.map((trip) => (
                  <TripListItem key={trip.id} trip={trip} today={today} />
                ))}
              </ul>
            </section>
          );
        })}
    </div>
  );
}
