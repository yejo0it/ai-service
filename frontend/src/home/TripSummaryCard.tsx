import { Link, useNavigate } from "react-router-dom";
import { ROUTES, tripDetailPath } from "../routes";
import type { TripDetailState } from "../trips/TripDetailPage";
import { dDayLabel, tripCities, tripColor } from "../trips/tripUtils";
import type { Trip } from "../types/api";
import { formatMonthDay } from "../utils/date";

interface TripSummaryCardProps {
  /** 선택한 여행 (막대 클릭 또는 여행이 하나뿐인 날짜 클릭) */
  trip: Trip | null;
  /** 선택한 날짜. 여행이 없거나 여럿이면 날짜 기준으로 보여준다. */
  date: string | null;
  /** 선택한 날짜에 걸친 여행들 */
  tripsOnDate: Trip[];
  today: string;
  onSelectTrip: (trip: Trip) => void;
  onClose: () => void;
}

/** 캘린더 아래 요약 카드: 선택한 여행의 일정·경로, 또는 선택한 날짜의 여행 목록 */
export default function TripSummaryCard({
  trip,
  date,
  tripsOnDate,
  today,
  onSelectTrip,
  onClose,
}: TripSummaryCardProps) {
  const navigate = useNavigate();
  if (!trip && !date) return null;

  const closeButton = (
    <button
      type="button"
      onClick={onClose}
      aria-label="요약 닫기"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
    >
      <i className="fas fa-times" aria-hidden="true" />
    </button>
  );

  if (trip) {
    const color = tripColor(trip);
    const cities = tripCities(trip);
    return (
      <section aria-label="선택한 여행" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${color.dot}`} aria-hidden="true" />
              <h2 className="truncate text-lg font-bold text-slate-900">{trip.destination_label} 여행</h2>
              <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                {dDayLabel(trip, today)}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {formatMonthDay(trip.start_date)} ~ {formatMonthDay(trip.end_date)} · {trip.nights}박{" "}
              {trip.nights + 1}일
            </p>
          </div>
          {closeButton}
        </div>

        {cities.length > 0 && (
          <ol className="mt-4 flex flex-wrap items-center gap-1.5" aria-label="여행 경로">
            {cities.map((city, index) => (
              <li key={`${city}-${index}`} className="flex items-center gap-1.5">
                {index > 0 && <i className="fas fa-arrow-right text-[10px] text-slate-300" aria-hidden="true" />}
                <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                  {city}
                </span>
              </li>
            ))}
          </ol>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-slate-50 px-3 py-2.5">
            <dt className="text-xs text-slate-400">항공권</dt>
            <dd className="mt-0.5 font-medium text-slate-700">
              {trip.has_flight ? trip.flight_info?.flight_number || "등록됨" : "미등록"}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 px-3 py-2.5">
            <dt className="text-xs text-slate-400">숙소</dt>
            <dd className="mt-0.5 font-medium text-slate-700">
              {trip.hotels.length > 0 ? `${trip.hotels.length}곳` : "미등록"}
            </dd>
          </div>
        </dl>

        {trip.hotels.length > 0 && (
          <ul className="mt-3 space-y-1.5 text-sm">
            {trip.hotels.slice(0, 3).map((hotel) => (
              <li key={hotel.id} className="flex items-center justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2 text-slate-700">
                  <i className="fas fa-bed text-xs text-slate-300" aria-hidden="true" />
                  <span className="truncate">{hotel.name}</span>
                </span>
                <span className="shrink-0 text-xs text-slate-400">
                  {hotel.check_in.slice(5).replace("-", ".")}
                  {hotel.check_out ? ` ~ ${hotel.check_out.slice(5).replace("-", ".")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}

        <button
          type="button"
          onClick={() => navigate(tripDetailPath(trip.id), { state: { trip } satisfies TripDetailState })}
          className="mt-5 w-full rounded-xl border border-slate-200 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
        >
          여행 상세 보기
        </button>
      </section>
    );
  }

  // 날짜만 선택: 그날 여행이 없거나 여럿인 경우
  return (
    <section aria-label="선택한 날짜" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-bold text-slate-900">{date && formatMonthDay(date)}</h2>
        {closeButton}
      </div>
      {tripsOnDate.length === 0 ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-500">이 날은 등록된 여행이 없어요.</p>
          <Link
            to={ROUTES.ONBOARDING}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
          >
            <i className="fas fa-plus text-xs" aria-hidden="true" />새 여행 만들기
          </Link>
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {tripsOnDate.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onSelectTrip(item)}
                className="flex w-full items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-left transition-colors hover:border-slate-300 hover:bg-slate-50"
              >
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${tripColor(item).dot}`} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {item.destination_label}
                </span>
                <span className="shrink-0 text-xs text-slate-400">
                  {formatMonthDay(item.start_date)} ~ {formatMonthDay(item.end_date)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
