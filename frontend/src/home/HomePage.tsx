import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { updateTripColor } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { nicknameOf } from "../components/layout/AppHeader";
import { ROUTES } from "../routes";
import { nextTrip } from "../trips/tripUtils";
import useTrips from "../trips/useTrips";
import type { Trip, TripColorKey } from "../types/api";
import { parseISODate, todayISODate } from "../utils/date";
import { DDayCard, RouteTimeline } from "./DashboardWidgets";
import TripCalendar from "./TripCalendar";
import TripSummaryCard from "./TripSummaryCard";
import { ExchangeWidget, PackingWidget, WeatherWidget } from "./TravelInfoWidgets";

const firstOfMonth = (date: Date) => new Date(date.getFullYear(), date.getMonth(), 1);

/**
 * `/` 홈 대시보드.
 * 왼쪽(모바일은 아래) D-Day·여행 경로 위젯, 오른쪽 대형 캘린더 + 선택 요약 카드.
 */
export default function HomePage() {
  const { user } = useAuth();
  const tripsState = useTrips();
  const today = todayISODate();

  const [month, setMonth] = useState(() => firstOfMonth(new Date()));
  const [selectedTripId, setSelectedTripId] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const trips = tripsState.status === "ready" ? tripsState.trips : [];
  const upcoming = useMemo(() => nextTrip(trips, today), [trips, today]);
  const selectedTrip = trips.find((trip) => trip.id === selectedTripId) ?? null;
  // 위젯(경로·날씨·환율)은 선택한 여행, 없으면 다가오는 여행 기준
  const focusTrip = selectedTrip ?? upcoming;

  // 처음 들어오면 오늘이 아니라 다가오는 여행이 있는 달을 보여준다(한 번만).
  const openedUpcoming = useRef(false);
  useEffect(() => {
    if (openedUpcoming.current || tripsState.status !== "ready") return;
    openedUpcoming.current = true;
    if (upcoming) setMonth(firstOfMonth(parseISODate(upcoming.start_date)));
  }, [tripsState.status, upcoming]);
  const tripsOnDate = selectedDate
    ? trips.filter((trip) => trip.start_date <= selectedDate && selectedDate <= trip.end_date)
    : [];

  const selectTrip = (trip: Trip) => {
    setSelectedTripId(trip.id);
    setSelectedDate(null);
  };

  // 날짜에 여행이 하나뿐이면 그 여행을 바로 보여주고, 없거나 여럿이면 날짜 요약을 보여준다.
  const selectDate = (date: string) => {
    const onDate = trips.filter((trip) => trip.start_date <= date && date <= trip.end_date);
    setSelectedDate(date);
    setSelectedTripId(onDate.length === 1 ? onDate[0].id : null);
  };

  const changeTripColor = async (trip: Trip, color: TripColorKey | "") => {
    const updated = await updateTripColor(trip.id, color);
    if (tripsState.status === "ready") tripsState.replaceTrip(updated);
  };

  // D-Day 카드에서 "캘린더에서 보기": 여행 시작 달로 이동해 선택한다.
  const showTrip = (trip: Trip) => {
    setMonth(firstOfMonth(parseISODate(trip.start_date)));
    selectTrip(trip);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">안녕하세요, {nicknameOf(user)} 님</h1>
          <p className="mt-1 text-sm text-slate-500">여행 일정을 한눈에 보고, 날짜를 눌러 요약을 확인하세요.</p>
        </div>
        <Link
          to={ROUTES.ONBOARDING}
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />새 여행 만들기
        </Link>
      </div>

      {tripsState.status === "error" ? (
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
      ) : (
        <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
          {/* 캘린더를 먼저 읽도록 모바일에서는 위젯을 아래로 보낸다. */}
          <aside className="order-2 space-y-4 lg:order-1">
            {tripsState.status === "loading" ? (
              <>
                <div className="h-40 animate-pulse rounded-2xl bg-slate-200/70" />
                <div className="h-56 animate-pulse rounded-2xl bg-slate-200/70" />
                <div className="h-32 animate-pulse rounded-2xl bg-slate-200/70" />
              </>
            ) : (
              <>
                <DDayCard trip={upcoming} today={today} onShowTrip={showTrip} />
                {focusTrip && <WeatherWidget trip={focusTrip} today={today} />}
                {focusTrip && <ExchangeWidget trip={focusTrip} />}
                <PackingWidget />
                <RouteTimeline trip={focusTrip} />
              </>
            )}
          </aside>

          <div className="order-1 space-y-4 lg:order-2">
            <div className={tripsState.status === "loading" ? "animate-pulse opacity-60" : ""}>
              <TripCalendar
                trips={trips}
                month={month}
                onMonthChange={setMonth}
                today={today}
                selectedTripId={selectedTripId}
                selectedDate={selectedDate}
                onSelectTrip={selectTrip}
                onSelectDate={selectDate}
              />
            </div>
            <TripSummaryCard
              trip={selectedTrip}
              date={selectedDate}
              tripsOnDate={tripsOnDate}
              today={today}
              onSelectTrip={selectTrip}
              onColorChange={changeTripColor}
              onClose={() => {
                setSelectedTripId(null);
                setSelectedDate(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
