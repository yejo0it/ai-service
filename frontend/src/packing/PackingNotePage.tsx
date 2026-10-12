import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { addPackingItem, deletePackingItem, getPackingItems, toErrorMessage, updatePackingItem } from "../api/client";
import { ROUTES, tripDetailPath, type HomeLocationState } from "../routes";
import type { PackingCategory, PackingItem, Trip } from "../types/api";
import { nextTrip, tripShortTitle } from "../trips/tripUtils";
import useTrips from "../trips/useTrips";
import { formatMonthDay, todayISODate } from "../utils/date";

/** 기본으로 보여줄 여행: 여행 중 → 다가오는 여행 → 가장 최근 여행 */
const defaultTrip = (trips: Trip[]) => nextTrip(trips, todayISODate()) ?? trips[trips.length - 1] ?? null;

/** 준비물 분류. 화면에 이 순서대로 나온다 (backend PackingItem.Category와 같다). */
const PACKING_CATEGORIES: { key: PackingCategory; label: string }[] = [
  { key: "essentials", label: "필수 준비물" },
  { key: "toiletries", label: "세면도구/화장품" },
  { key: "clothing", label: "의류" },
  { key: "electronics", label: "전자제품" },
  { key: "medicine", label: "상비약" },
  { key: "etc", label: "기타" },
];

/** 준비물 체크리스트: 기본 준비물 + 직접 추가한 준비물. 체크·추가·삭제는 바로 저장한다. */
function PackingChecklist({ trip }: { trip: Trip }) {
  const [items, setItems] = useState<PackingItem[] | null>(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [category, setCategory] = useState<PackingCategory>("etc");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError("");
    getPackingItems(trip.id)
      .then((data) => !cancelled && setItems(data))
      .catch((err: unknown) => !cancelled && setError(toErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [trip.id]);

  const toggle = (target: PackingItem, done: boolean) => {
    setError("");
    setItems((current) => current?.map((item) => (item.id === target.id ? { ...item, done } : item)) ?? null);
    updatePackingItem(target.id, { done }).catch((err: unknown) => {
      setItems((current) => current?.map((item) => (item.id === target.id ? { ...item, done: !done } : item)) ?? null);
      setError(toErrorMessage(err));
    });
  };

  const remove = (target: PackingItem) => {
    setError("");
    deletePackingItem(target.id)
      .then(() => setItems((current) => current?.filter((item) => item.id !== target.id) ?? null))
      .catch((err: unknown) => setError(toErrorMessage(err)));
  };

  const add = async (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || adding) return;
    setAdding(true);
    setError("");
    try {
      const created = await addPackingItem(trip.id, { category, text });
      setItems((current) => [...(current ?? []), created]);
      setDraft("");
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setAdding(false);
    }
  };

  if (error && !items) return <p className="text-sm text-rose-600">{error}</p>;
  if (!items) return <div className="h-48 animate-pulse rounded-2xl bg-slate-100" />;

  const doneCount = items.filter((item) => item.done).length;
  const percent = items.length === 0 ? 0 : Math.round((doneCount / items.length) * 100);

  return (
    <div>
      <div className="flex items-center gap-3">
        <div
          className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-label="짐싸기 진행률"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${percent}%` }} />
        </div>
        <span className="text-sm font-semibold tabular-nums text-slate-700">{percent}%</span>
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        {items.length}개 중 {doneCount}개 챙김
      </p>

      <form onSubmit={add} className="mt-5 flex flex-wrap gap-2">
        <label htmlFor="packing-category" className="sr-only">
          분류
        </label>
        <select
          id="packing-category"
          value={category}
          onChange={(event) => setCategory(event.target.value as PackingCategory)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        >
          {PACKING_CATEGORIES.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
        <label htmlFor="packing-new" className="sr-only">
          준비물 추가
        </label>
        <input
          id="packing-new"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={100}
          placeholder="챙길 준비물을 입력하세요 (예: 수영복)"
          className="min-w-[12rem] flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
        <button
          type="submit"
          disabled={!draft.trim() || adding}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />
          추가
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}

      {items.length === 0 ? (
        <p className="mt-5 rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
          준비물을 추가해 보세요.
        </p>
      ) : (
        <div className="mt-6 space-y-6">
          {PACKING_CATEGORIES.map((option) => {
            const group = items.filter((item) => item.category === option.key);
            if (group.length === 0) return null;
            return (
              <section key={option.key} aria-label={option.label}>
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
                  {option.label}
                  <span className="text-xs font-medium tabular-nums text-slate-400">
                    {group.filter((item) => item.done).length}/{group.length}
                  </span>
                </h3>
                <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {group.map((item) => (
                    <li key={item.id} className="flex items-center gap-2 rounded-xl bg-slate-50 pr-1.5">
                      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3.5 py-2.5">
                        <input
                          type="checkbox"
                          checked={item.done}
                          onChange={(event) => toggle(item, event.target.checked)}
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                        />
                        <span className={`min-w-0 flex-1 truncate text-sm ${item.done ? "text-slate-400 line-through" : "text-slate-800"}`}>
                          {item.text}
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => remove(item)}
                        aria-label={`${item.text} 삭제`}
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600"
                      >
                        <i className="fas fa-times text-xs" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** `/packing` 짐싸기 노트. 여행을 고르면 그 여행의 준비물 체크리스트를 보여준다(`?trip=` 로 기억). */
export default function PackingNotePage() {
  const trips = useTrips();
  const [params, setParams] = useSearchParams();

  if (trips.status === "loading") {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="h-64 animate-pulse rounded-2xl bg-slate-200/70" />
      </div>
    );
  }
  if (trips.status === "error") {
    return <p className="mx-auto max-w-6xl px-4 py-8 text-sm text-rose-600 sm:px-6">{trips.message}</p>;
  }

  const selected =
    trips.trips.find((trip) => String(trip.id) === params.get("trip")) ?? defaultTrip(trips.trips);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">짐싸기 노트</h1>

      {!selected ? (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-8 text-center">
          <p className="text-sm text-slate-600">아직 여행이 없어요.</p>
          <Link
            to={ROUTES.HOME}
            state={{ newTrip: true } satisfies HomeLocationState}
            className="mt-3 inline-block text-sm font-semibold text-indigo-600"
          >
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

          <section aria-label="준비물 체크리스트" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-base font-bold text-slate-900">준비물 체크리스트</h2>
            <PackingChecklist key={selected.id} trip={selected} />
          </section>
        </>
      )}
    </div>
  );
}
