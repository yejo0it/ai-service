import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { addPackingItem, deletePackingItem, getPackingItems, toErrorMessage, updatePackingItem } from "../api/client";
import type { PackingCategory, PackingItem, Trip } from "../types/api";
import { dDayLabel, tripStatus } from "../trips/tripUtils";
import { todayISODate } from "../utils/date";

const PACKING_CATEGORIES: { key: PackingCategory; label: string; icon: string; example: string }[] = [
  { key: "todo", label: "해야 할 일", icon: "fas fa-clipboard-check", example: "전망대 입장권 예약하기" },
  { key: "essentials", label: "필수 준비물", icon: "fas fa-passport", example: "국제운전면허증" },
  { key: "toiletries", label: "세면도구/화장품", icon: "fas fa-pump-soap", example: "클렌징폼" },
  { key: "clothing", label: "의류", icon: "fas fa-tshirt", example: "패딩" },
  { key: "electronics", label: "전자제품", icon: "fas fa-plug", example: "카메라" },
  { key: "medicine", label: "상비약", icon: "fas fa-medkit", example: "멀미약" },
  { key: "etc", label: "기타", icon: "fas fa-box-open", example: "수영복" },
];

type Filter = "all" | "left" | "done";

/** 사이드바 D-Day 뱃지. 지난 여행이면 null. */
const ddayBadge = (trip: Trip) => {
  const today = todayISODate();
  return tripStatus(trip, today) === "past" ? null : dDayLabel(trip, today);
};

/** 여행 체크리스트. 여행 상세의 `/trips/:id/checklist` 탭에 그린다. */
export default function PackingNote({ trip }: { trip: Trip }) {
  const [items, setItems] = useState<PackingItem[] | null>(null);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Partial<Record<PackingCategory, string>>>({});
  const [adding, setAdding] = useState<PackingCategory | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [focusCat, setFocusCat] = useState<PackingCategory | null>(null);

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

  const setDone = (target: PackingItem, done: boolean) => {
    setError("");
    setItems((cur) => cur?.map((i) => (i.id === target.id ? { ...i, done } : i)) ?? null);
    return updatePackingItem(target.id, { done }).catch((err: unknown) => {
      setItems((cur) => cur?.map((i) => (i.id === target.id ? { ...i, done: !done } : i)) ?? null);
      setError(toErrorMessage(err));
    });
  };

  const remove = (target: PackingItem) => {
    setError("");
    deletePackingItem(target.id)
      .then(() => setItems((cur) => cur?.filter((i) => i.id !== target.id) ?? null))
      .catch((err: unknown) => setError(toErrorMessage(err)));
  };

  const add = async (category: PackingCategory) => {
    const text = (drafts[category] ?? "").trim();
    if (!text || adding) return;
    setAdding(category);
    setError("");
    try {
      const created = await addPackingItem(trip.id, { category, text });
      setItems((cur) => [...(cur ?? []), created]);
      setDrafts((d) => ({ ...d, [category]: "" }));
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setAdding(null);
    }
  };

  const onDraftKey = (category: PackingCategory) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      add(category);
    }
  };

  // "체크 모두 해제": 체크된 항목만 PATCH
  const resetAll = () => items?.filter((i) => i.done).forEach((i) => setDone(i, false));

  const stats = useMemo(() => {
    const list = items ?? [];
    const done = list.filter((i) => i.done).length;
    return { total: list.length, done, percent: list.length ? Math.round((done / list.length) * 100) : 0 };
  }, [items]);

  if (error && !items) return <p className="text-sm text-rose-600">{error}</p>;
  if (!items) return <div className="h-64 animate-pulse rounded-2xl bg-slate-200/70" />;

  const groups = PACKING_CATEGORIES.map((c) => {
    const all = items.filter((i) => i.category === c.key);
    const done = all.filter((i) => i.done).length;
    return { ...c, all, done, complete: all.length > 0 && done === all.length };
  });
  const keep = (i: PackingItem) => filter === "all" || (filter === "left" ? !i.done : i.done);
  const visible = groups
    .filter((g) => !focusCat || g.key === focusCat)
    .map((g) => ({ ...g, items: g.all.filter(keep) }))
    .filter((g) => filter === "all" || g.items.length > 0);
  const dday = ddayBadge(trip);

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[300px_minmax(0,1fr)]">
      {/* 왼쪽 요약 사이드바 */}
      <aside className="flex flex-col gap-5 lg:sticky lg:top-24">
        <div className="flex flex-col gap-[18px] rounded-[18px] border border-slate-200 bg-white p-5">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-[44px] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
                {stats.percent}<span className="text-[22px]">%</span>
              </span>
              {dday && <span className="rounded-lg bg-indigo-50 px-2 py-1 text-[13px] font-bold text-indigo-600">{dday}</span>}
            </div>
            <div
              className="mb-2 mt-3.5 h-2 overflow-hidden rounded bg-slate-100"
              role="progressbar" aria-label="체크리스트 진행률" aria-valuenow={stats.percent} aria-valuemin={0} aria-valuemax={100}
            >
              <div className="h-full rounded bg-indigo-600 transition-all duration-300" style={{ width: `${stats.percent}%` }} />
            </div>
            <p className="text-[13px] text-slate-500">
              {stats.total}개 중 {stats.done}개 완료 · 남은 {stats.total - stats.done}개
            </p>
          </div>

          <hr className="border-slate-100" />

          <nav aria-label="분류" className="flex flex-col gap-0.5">
            <button
              type="button"
              onClick={() => setFocusCat(null)}
              className={`flex items-center gap-2.5 rounded-[10px] px-2.5 py-[9px] text-left text-sm font-semibold ${!focusCat ? "bg-indigo-50 text-indigo-800" : "text-slate-700 hover:bg-slate-50"}`}
            >
              <i className="fas fa-layer-group w-4 text-center text-[13px]" aria-hidden="true" />
              <span className="flex-1">전체</span>
              <span className="text-xs tabular-nums">{stats.done}/{stats.total}</span>
            </button>
            {groups.map((g) => {
              const active = focusCat === g.key;
              const pct = g.all.length ? (g.done / g.all.length) * 100 : 0;
              return (
                <button
                  key={g.key}
                  type="button"
                  onClick={() => setFocusCat(active ? null : g.key)}
                  aria-pressed={active}
                  className={`flex flex-col gap-1.5 rounded-[10px] px-2.5 py-[9px] text-left text-sm font-medium ${active ? "bg-indigo-50 text-indigo-800" : "text-slate-700 hover:bg-slate-50"}`}
                >
                  <span className="flex w-full items-center gap-2.5">
                    <i className={`${g.icon} w-4 text-center text-[13px] ${g.complete ? "text-emerald-500" : "text-indigo-500"}`} aria-hidden="true" />
                    <span className="flex-1">{g.label}</span>
                    {g.complete && <i className="fas fa-check-circle text-[13px] text-emerald-500" aria-label="완료" />}
                    <span className="text-xs tabular-nums text-slate-400">{g.done}/{g.all.length}</span>
                  </span>
                  <span className="ml-[26px] h-[3px] w-[calc(100%-26px)] overflow-hidden rounded-sm bg-slate-200">
                    <span className={`block h-full transition-all duration-300 ${g.complete ? "bg-emerald-500" : "bg-indigo-500"}`} style={{ width: `${pct}%` }} />
                  </span>
                </button>
              );
            })}
          </nav>
        </div>
      </aside>

      {/* 오른쪽 체크리스트 */}
      <main className="flex min-w-0 flex-col gap-5">
        <div className="flex h-10 items-center justify-between gap-3">
          <div className="flex gap-0.5 rounded-xl bg-[#eef0f4] p-[3px]" role="tablist" aria-label="보기">
            {([["all", "전체", stats.total], ["left", "남은 것", stats.total - stats.done], ["done", "완료한 것", stats.done]] as const).map(([key, label, count]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={filter === key}
                onClick={() => setFilter(key)}
                className={`rounded-[9px] px-3.5 py-2 text-[13px] font-semibold ${filter === key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
              >
                {label} <span className="font-medium tabular-nums text-slate-400">{count}</span>
              </button>
            ))}
          </div>
          <button type="button" onClick={resetAll} disabled={stats.done === 0} className="flex items-center gap-1.5 text-[13px] font-medium text-slate-500 hover:text-slate-700 disabled:opacity-40">
            <i className="fas fa-undo text-xs" aria-hidden="true" />
            체크 모두 해제
          </button>
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}

        {visible.length === 0 ? (
          <div className="rounded-[18px] border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
            <div className="mx-auto mb-3.5 flex h-[52px] w-[52px] items-center justify-center rounded-full bg-emerald-50 text-[22px] text-emerald-500">
              <i className="fas fa-check" aria-hidden="true" />
            </div>
            <p className="text-[17px] font-bold">{filter === "left" ? "모두 완료했어요" : "아직 완료한 항목이 없어요"}</p>
            <p className="mt-1.5 text-sm text-slate-500">
              {filter === "left" ? `${stats.total}개 항목을 모두 완료했어요. 즐거운 여행 되세요.` : "항목을 체크하면 여기에 모여요."}
            </p>
          </div>
        ) : (
          visible.map((g) => {
            const draft = drafts[g.key] ?? "";
            return (
              <section key={g.key} aria-label={g.label} className="overflow-hidden rounded-[18px] border border-slate-200 bg-white">
                <header className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
                  <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] bg-indigo-50 text-sm text-indigo-600">
                    <i className={g.icon} aria-hidden="true" />
                  </span>
                  <h2 className="flex-1 text-base font-bold text-slate-900">{g.label}</h2>
                  <span className="text-[13px] tabular-nums text-slate-500">{g.done}/{g.all.length}</span>
                </header>
                {g.items.length > 0 && (
                  <ul className="grid gap-x-2 px-2 py-1.5 sm:grid-cols-2">
                    {g.items.map((item) => (
                      <li key={item.id} className="flex items-center gap-1 rounded-[10px] pr-1 hover:bg-slate-50">
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3 py-[11px]">
                          <input type="checkbox" checked={item.done} onChange={(e) => setDone(item, e.target.checked)} className="peer sr-only" />
                          <span
                            aria-hidden="true"
                            className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-[1.5px] text-[11px] text-white transition-all peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-200 ${item.done ? "border-indigo-600 bg-indigo-600" : "border-slate-300 bg-white"}`}
                          >
                            {item.done && <i className="fas fa-check" />}
                          </span>
                          <span className={`min-w-0 flex-1 truncate text-[15px] ${item.done ? "text-slate-400 line-through" : "text-slate-800"}`}>{item.text}</span>
                          {!item.is_default && <span className="rounded-[5px] bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-500">직접 추가</span>}
                        </label>
                        <button
                          type="button"
                          onClick={() => remove(item)}
                          aria-label={`${item.text} 삭제`}
                          className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg text-xs text-slate-300 transition-colors hover:bg-slate-100 hover:text-slate-500"
                        >
                          <i className="fas fa-times" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="flex items-center gap-2.5 px-5 pb-3.5 pt-1">
                  <i className="fas fa-plus w-5 text-center text-xs text-indigo-300" aria-hidden="true" />
                  <label htmlFor={`packing-new-${g.key}`} className="sr-only">{g.label}에 준비물 추가</label>
                  <input
                    id={`packing-new-${g.key}`}
                    value={draft}
                    onChange={(e) => setDrafts((d) => ({ ...d, [g.key]: e.target.value }))}
                    onKeyDown={onDraftKey(g.key)}
                    maxLength={100}
                    placeholder={`${g.label}에 추가 (예: ${g.example})`}
                    className="flex-1 border-b border-transparent bg-transparent py-2 text-sm placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none"
                  />
                  {draft.trim() && (
                    <button
                      type="button"
                      onClick={() => add(g.key)}
                      disabled={adding === g.key}
                      className="rounded-[9px] bg-indigo-600 px-3 py-[7px] text-[13px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      추가
                    </button>
                  )}
                </div>
              </section>
            );
          })
        )}
      </main>
    </div>
  );
}
