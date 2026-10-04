import { useEffect, useState, type FormEvent } from "react";
import { addItineraryPlace, searchPlaces, toErrorMessage } from "../api/client";
import { TimeField, formatMeridiemTime } from "../components/pickers";
import type { HotelSuggestion, ItineraryResponse, PlaceKind, Trip } from "../types/api";
import { formatMonthDay } from "../utils/date";
import Drawer from "./Drawer";
import { KIND_STYLE } from "./TripItinerary";
import { dayLabel } from "./tripDays";

const KINDS: PlaceKind[] = ["sight", "restaurant", "cafe", "hotel", "airport"];

/** 등록 대기 목록의 장소 하나. sessionToken은 그 장소를 고른 자동완성 세션 (등록 시 상세 조회로 세션을 끝낸다) */
interface PendingPlace {
  key: string;
  kind: PlaceKind;
  place: HotelSuggestion;
  day: string;
  time: string;
  sessionToken: string;
}

interface AddPlaceDrawerProps {
  trip: Trip;
  dates: string[];
  initialDay: string;
  /** 처음 선택된 유형 (기본 관광지) */
  initialKind?: PlaceKind;
  onClose: () => void;
  /** 한 곳이 등록될 때마다 최신 일정 */
  onSaved: (itinerary: ItineraryResponse) => void;
  /** 모두 등록했을 때 (첫 장소의 날짜를 보여준다) */
  onDone: (day: string) => void;
}

/** 여행 기간 중 그날 머무를 것 같은 여행지 (여행지를 순서대로 기간에 고르게 나눈다). 검색 위치 편향에만 쓴다. */
const cityCodeFor = (trip: Trip, dayIndex: number, dayCount: number) => {
  const destinations = trip.destinations.filter((dest) => dest.city_code);
  if (destinations.length === 0) return undefined;
  return destinations[Math.min(destinations.length - 1, Math.floor((dayIndex * destinations.length) / dayCount))]
    .city_code;
};

/**
 * 장소 직접 추가: 유형 · 장소 검색 · 날짜 · 시간(선택)을 입력해 목록에 쌓고, 한 번에 등록한다.
 * 유형을 바꿔도 입력한 검색어·장소·날짜·시간은 그대로 둔다.
 * 그날 안의 자리는 서버가 앞뒤 일정과의 거리(시간을 정하면 시간 순서)로 정한다.
 */
export default function AddPlaceDrawer({
  trip,
  dates,
  initialDay,
  initialKind = "sight",
  onClose,
  onSaved,
  onDone,
}: AddPlaceDrawerProps) {
  const [kind, setKind] = useState<PlaceKind>(initialKind);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<HotelSuggestion | null>(null);
  const [suggestions, setSuggestions] = useState<HotelSuggestion[]>([]);
  const [searchError, setSearchError] = useState("");
  const [day, setDay] = useState(initialDay);
  const [time, setTime] = useState("");
  const [sessionToken, setSessionToken] = useState(() => crypto.randomUUID());
  const [pending, setPending] = useState<PendingPlace[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const cityCode = cityCodeFor(trip, Math.max(0, dates.indexOf(day)), dates.length);

  // 입력어가 바뀌면 300ms 뒤 자동완성 (장소를 고른 뒤에는 멈춘다)
  useEffect(() => {
    const keyword = query.trim();
    if (selected || keyword.length < 2) {
      setSuggestions([]);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      searchPlaces({ input: keyword, sessionToken, cityCode, kind })
        .then((result) => {
          if (cancelled) return;
          setSuggestions(result);
          setSearchError("");
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setSuggestions([]);
          setSearchError(toErrorMessage(err));
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, selected, sessionToken, cityCode, kind]);

  /** 지금 입력 중인 장소 (장소를 골랐을 때만) */
  const current = (): PendingPlace | null =>
    selected ? { key: sessionToken, kind, place: selected, day, time, sessionToken } : null;

  const isDuplicate = (entry: PendingPlace) =>
    pending.some((item) => item.place.place_id === entry.place.place_id && item.day === entry.day);

  // 목록에 쌓고 장소·시간 입력만 비운다(유형·날짜는 다음 장소에도 그대로 쓴다).
  const addToList = () => {
    const entry = current();
    if (!entry) return;
    setError("");
    if (isDuplicate(entry)) {
      setError("같은 날짜에 이미 담은 장소예요.");
      return;
    }
    setPending((list) => [...list, entry]);
    setSelected(null);
    setQuery("");
    setTime("");
    setSessionToken(crypto.randomUUID());
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const entry = current();
    const entries = entry && !isDuplicate(entry) ? [...pending, entry] : pending;
    if (entries.length === 0) return;
    setSaving(true);
    setError("");
    for (const [index, item] of entries.entries()) {
      try {
        onSaved(
          await addItineraryPlace(trip.id, {
            kind: item.kind,
            day: item.day,
            time: item.time,
            place_id: item.place.place_id,
            session_token: item.sessionToken,
          }),
        );
      } catch (err) {
        // 등록하지 못한 장소부터 목록에 남겨 다시 시도할 수 있게 한다.
        setPending(entries.slice(index));
        if (entry) {
          setSelected(null);
          setQuery("");
          setTime("");
          setSessionToken(crypto.randomUUID());
        }
        setError(`${item.place.name}: ${toErrorMessage(err)}`);
        setSaving(false);
        return;
      }
    }
    onDone(entries[0].day);
  };

  const total = pending.length + (selected ? 1 : 0);
  const inputClass =
    "w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100";

  return (
    <Drawer
      title="장소 직접 추가"
      onClose={onClose}
      footer={
        <button
          type="submit"
          form="add-place-form"
          disabled={total === 0 || saving}
          className="w-full rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {saving ? "등록하는 중..." : total > 1 ? `${total}곳 일괄 등록` : "일정에 등록"}
        </button>
      }
    >
      <form id="add-place-form" onSubmit={submit} className="space-y-5">
        <fieldset>
          <legend className="mb-2 text-xs font-semibold text-slate-500">유형</legend>
          <div className="flex flex-wrap gap-1.5">
            {KINDS.map((value) => {
              const active = value === kind;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setKind(value)}
                  aria-pressed={active}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  }`}
                >
                  <i className={`${KIND_STYLE[value].icon} text-xs`} aria-hidden="true" />
                  {KIND_STYLE[value].label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label htmlFor="place-query" className="mb-2 block text-xs font-semibold text-slate-500">
            장소 검색
          </label>
          {selected ? (
            <div className="flex items-start justify-between gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-900">{selected.name}</p>
                <p className="truncate text-xs text-slate-500">{selected.description}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
              >
                다시 검색
              </button>
            </div>
          ) : (
            <>
              <input
                id="place-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`${KIND_STYLE[kind].label} 이름을 입력하세요`}
                autoComplete="off"
                className={inputClass}
              />
              {suggestions.length > 0 && (
                <ul className="mt-1.5 overflow-hidden rounded-xl border border-slate-200" aria-label="검색 결과">
                  {suggestions.map((item) => (
                    <li key={item.place_id} className="border-t border-slate-100 first:border-t-0">
                      <button
                        type="button"
                        onClick={() => setSelected(item)}
                        className="block w-full px-3 py-2.5 text-left hover:bg-slate-50"
                      >
                        <span className="block truncate text-sm font-medium text-slate-800">{item.name}</span>
                        <span className="block truncate text-xs text-slate-400">{item.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {searchError && <p className="mt-1.5 text-xs text-rose-600">{searchError}</p>}
            </>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="place-day" className="mb-2 block text-xs font-semibold text-slate-500">
              날짜
            </label>
            <select
              id="place-day"
              value={day}
              onChange={(event) => setDay(event.target.value)}
              className={`${inputClass} py-3 text-base`}
            >
              {dates.map((date, index) => (
                <option key={date} value={date}>
                  {dayLabel(index)} · {formatMonthDay(date)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <p className="mb-2 block text-xs font-semibold text-slate-500">
              시간 <span className="font-normal text-slate-400">(선택)</span>
            </p>
            <TimeField value={time} onChange={setTime} ariaLabel="시간 (선택)" placeholder="시간 미정" optional />
          </div>
        </div>

        <button
          type="button"
          onClick={addToList}
          disabled={!selected || saving}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-indigo-300 py-2.5 text-sm font-semibold text-indigo-600 transition-colors hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-300"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />
          장소 더 추가하기
        </button>

        {pending.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold text-slate-500">등록할 장소 {pending.length}곳</p>
            <ul className="space-y-1.5" aria-label="등록할 장소">
              {pending.map((item) => (
                <li key={item.key} className="flex items-center gap-2.5 rounded-xl bg-slate-50 px-3 py-2">
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs ${KIND_STYLE[item.kind].tile}`}
                    aria-hidden="true"
                  >
                    <i className={KIND_STYLE[item.kind].icon} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800">{item.place.name}</p>
                    <p className="text-xs text-slate-400">
                      {KIND_STYLE[item.kind].label} · {dayLabel(dates.indexOf(item.day))}
                      {item.time && ` ${formatMeridiemTime(item.time)}`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPending((list) => list.filter((entry) => entry.key !== item.key))}
                    disabled={saving}
                    aria-label={`${item.place.name} 빼기`}
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs text-slate-300 hover:text-rose-500"
                  >
                    <i className="fas fa-times" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-500">
          <i className="fas fa-route mr-1.5 text-slate-400" aria-hidden="true" />
          그날 일정 중 이동 거리가 가장 적게 늘어나는 자리에 넣어요. 시간을 정하면 시간 순서에 맞춰 넣어요.
        </p>
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </form>
    </Drawer>
  );
}
