import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getPackingNote, toErrorMessage, updateChecklistItem } from "../api/client";
import { ROUTES, tripDetailPath } from "../routes";
import type { PackingLinkedItem, Trip } from "../types/api";
import { dayLabel, tripDates } from "../trips/tripDays";
import { nextTrip, tripShortTitle } from "../trips/tripUtils";
import useTrips from "../trips/useTrips";
import { formatMonthDay, todayISODate } from "../utils/date";

/** 기본으로 보여줄 여행: 여행 중 → 다가오는 여행 → 가장 최근 여행 */
const defaultTrip = (trips: Trip[]) => nextTrip(trips, todayISODate()) ?? trips[trips.length - 1] ?? null;

/** 일정 연동 항목: 여행 상세 카드 체크리스트 중 짐싸기 노트 표시가 켜진 항목을 날짜별로. 체크 상태는 카드와 같다. */
function LinkedItems({ trip }: { trip: Trip }) {
  const [items, setItems] = useState<PackingLinkedItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError("");
    getPackingNote(trip.id)
      .then((data) => !cancelled && setItems(data.linked))
      .catch((err: unknown) => !cancelled && setError(toErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [trip.id]);

  const dates = useMemo(() => tripDates(trip), [trip]);

  const toggle = (check: PackingLinkedItem, done: boolean) => {
    setError("");
    setItems((current) => current?.map((item) => (item.id === check.id ? { ...item, done } : item)) ?? null);
    updateChecklistItem(check.id, { done }).catch((err: unknown) => {
      setItems((current) => current?.map((item) => (item.id === check.id ? { ...item, done: !done } : item)) ?? null);
      setError(toErrorMessage(err));
    });
  };

  if (error && !items) return <p className="text-sm text-rose-600">{error}</p>;
  if (!items) return <div className="h-24 animate-pulse rounded-2xl bg-slate-100" />;
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center">
        <p className="text-sm font-medium text-slate-600">아직 일정에서 연동된 항목이 없어요</p>
        <p className="mt-1 text-xs text-slate-400">
          여행 상세 카드의 체크리스트에 예약·티켓·준비물을 적으면 여기에 모여요.
        </p>
      </div>
    );
  }

  const byDay = dates
    .map((date, index) => ({ date, index, items: items.filter((item) => item.day === date) }))
    .filter((group) => group.items.length > 0);
  const doneCount = items.filter((item) => item.done).length;

  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-500">
        {items.length}개 중 {doneCount}개 완료
      </p>
      {byDay.map((group) => (
        <div key={group.date}>
          <h3 className="mb-2 text-xs font-semibold text-slate-400">
            {dayLabel(group.index)} · {formatMonthDay(group.date)}
          </h3>
          <ul className="space-y-1.5">
            {group.items.map((item) => (
              <li key={item.id}>
                <label className="flex cursor-pointer items-center gap-3 rounded-xl bg-slate-50 px-3.5 py-2.5">
                  <input
                    type="checkbox"
                    checked={item.done}
                    onChange={(event) => toggle(item, event.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                  />
                  <span className={`min-w-0 flex-1 text-sm ${item.done ? "text-slate-400 line-through" : "text-slate-800"}`}>
                    {item.text}
                  </span>
                  <span className="max-w-[40%] shrink-0 truncate rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-500 shadow-sm">
                    {item.item_title}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {error && <p className="text-sm text-rose-600">{error}</p>}
    </div>
  );
}

/** `/packing` 짐싸기 노트. 여행을 고르면 그 여행의 '일정 연동 항목'을 보여준다(`?trip=` 로 기억). */
export default function PackingNotePage() {
  const trips = useTrips();
  const [params, setParams] = useSearchParams();

  if (trips.status === "loading") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <div className="h-64 animate-pulse rounded-2xl bg-slate-200/70" />
      </div>
    );
  }
  if (trips.status === "error") {
    return <p className="mx-auto max-w-3xl px-4 py-8 text-sm text-rose-600 sm:px-6">{trips.message}</p>;
  }

  const selected =
    trips.trips.find((trip) => String(trip.id) === params.get("trip")) ?? defaultTrip(trips.trips);

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">짐싸기 노트</h1>

      {!selected ? (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-8 text-center">
          <p className="text-sm text-slate-600">아직 여행이 없어요.</p>
          <Link to={ROUTES.ONBOARDING} className="mt-3 inline-block text-sm font-semibold text-indigo-600">
            새 여행 만들기
          </Link>
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <label htmlFor="packing-trip" className="sr-only">
              여행 선택
            </label>
            <select
              id="packing-trip"
              value={selected.id}
              onChange={(event) => setParams({ trip: event.target.value }, { replace: true })}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            >
              {trips.trips.map((trip) => (
                <option key={trip.id} value={trip.id}>
                  {tripShortTitle(trip)} · {formatMonthDay(trip.start_date)}
                </option>
              ))}
            </select>
            <Link to={tripDetailPath(selected.id)} className="text-sm font-medium text-indigo-600 hover:underline">
              여행 상세 보기
            </Link>
          </div>

          <section aria-label="일정 연동 항목" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-1 text-base font-bold text-slate-900">일정 연동 항목</h2>
            <p className="mb-4 text-xs text-slate-400">
              여행 상세 카드의 예약·티켓·준비물 체크리스트가 자동으로 모여요. 체크하면 카드에도 함께 반영돼요.
            </p>
            <LinkedItems key={selected.id} trip={selected} />
          </section>
        </>
      )}
    </div>
  );
}
