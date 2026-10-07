import { useEffect, useRef, useState, type FormEvent } from "react";
import { addItineraryPlace, searchPlaces, toErrorMessage } from "../api/client";
import { toISODate } from "../components/calendar";
import { COMPACT_LABEL_CLASS } from "../components/formFields";
import { TimeField, formatMeridiemTime } from "../components/pickers";
import { AirlineFlightFields, AirportInput, EMPTY_AIRPORT } from "../onboarding/flightFields";
import { StayRangeField, formatShortDate, isNightTaken } from "../onboarding/stayRange";
import type {
  AddFlightPayload,
  AddHotelStayPayload,
  AddPlacePayload,
  HotelSuggestion,
  ItineraryResponse,
  PlaceKind,
  Trip,
} from "../types/api";
import type { AirlineSelection, AirportDraft, Stay } from "../types/onboarding";
import { formatMonthDay } from "../utils/date";
import Drawer from "./Drawer";
import { KIND_STYLE } from "./TripItinerary";
import { dayLabel } from "./tripDays";

const KINDS: PlaceKind[] = ["sight", "restaurant", "cafe", "hotel", "airport"];

/**
 * 등록 대기 목록의 일정 하나 (장소 또는 항공편).
 * 장소의 key는 그 장소를 고른 자동완성 세션 (등록 시 상세 조회로 세션을 끝낸다).
 */
interface PendingEntry {
  key: string;
  kind: PlaceKind;
  /** 목록에 보여줄 이름 */
  name: string;
  /** 이름 아래 설명 (항공편은 노선) */
  detail: string;
  /** 날짜·시간 (숙소는 숙박 기간) 표기 */
  when: string;
  /** 등록 후 보여줄 날짜 (숙소는 체크인 날) */
  day: string;
  /** 같은 날 같은 일정을 두 번 담지 않기 위한 값 */
  identity: string;
  payload: AddPlacePayload | AddFlightPayload | AddHotelStayPayload;
}

const EMPTY_AIRLINE: AirlineSelection = { name: "", code: "" };

/** 입력 칸 라벨 (항공편 칸도 날짜·시간과 같은 모양) */
const LABEL_CLASS = COMPACT_LABEL_CLASS;

const airportPayload = (draft: AirportDraft) => {
  const airport = draft.airport!;
  return { code: airport.code, name: airport.name, lat: airport.lat, lng: airport.lng };
};

interface AddPlaceDrawerProps {
  trip: Trip;
  dates: string[];
  initialDay: string;
  /** 처음 선택된 유형 (기본 관광지) */
  initialKind?: PlaceKind;
  onClose: () => void;
  /** 한 곳이 등록될 때마다 최신 일정 */
  onSaved: (itinerary: ItineraryResponse & { trip?: Trip }) => void;
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
 * 공항은 새 여행 만들기의 항공권 입력을 재활용해 단일 노선 한 편(항공사 · 편명 · 출발 · 도착 공항)으로 받는다.
 * 숙소는 새 여행 만들기의 숙소 입력처럼 숙박 기간(체크인~체크아웃, 여행 기간 안)을 받아 여행 숙소로 등록한다.
 * 유형을 바꿔도 입력한 검색어·장소·항공편·날짜·시간은 그대로 둔다.
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
  const [airline, setAirline] = useState<AirlineSelection>(EMPTY_AIRLINE);
  const [flightNumber, setFlightNumber] = useState("");
  const [departure, setDeparture] = useState<AirportDraft>(EMPTY_AIRPORT);
  const [arrival, setArrival] = useState<AirportDraft>(EMPTY_AIRPORT);
  const flightSeq = useRef(0);
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [pending, setPending] = useState<PendingEntry[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const isHotel = kind === "hotel";
  // 검색 위치 편향: 숙소는 체크인 날, 그 밖에는 고른 날의 여행지
  const searchDay = isHotel && checkIn ? checkIn : day;
  const cityCode = cityCodeFor(trip, Math.max(0, dates.indexOf(searchDay)), dates.length);

  const isFlight = kind === "airport";

  // 입력어가 바뀌면 300ms 뒤 자동완성 (장소를 고른 뒤, 항공편 입력 중에는 멈춘다)
  useEffect(() => {
    const keyword = query.trim();
    if (isFlight || selected || keyword.length < 2) {
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
  }, [query, selected, sessionToken, cityCode, kind, isFlight]);

  const flightReady = Boolean(departure.airport && arrival.airport);
  const stayReady = Boolean(checkIn && checkOut);
  // 이미 묵는 밤(등록된 숙소 + 등록 대기 목록의 숙소)은 고를 수 없다. 체크아웃 미정 숙소는 체크인 하룻밤으로 본다.
  const takenStays: Stay[] = [
    ...trip.hotels.map((hotel) => ({
      id: `hotel-${hotel.id}`,
      check_in: hotel.check_in,
      check_out: hotel.check_out ?? toISODate(new Date(new Date(`${hotel.check_in}T00:00:00`).getTime() + 86400000)),
    })),
    ...pending.flatMap((entry) =>
      "check_in" in entry.payload
        ? [{ id: entry.key, check_in: entry.payload.check_in, check_out: entry.payload.check_out }]
        : [],
    ),
  ];
  const hasFreeNight = dates.slice(0, -1).some((date) => !isNightTaken(date, takenStays));
  const ready = isFlight ? flightReady : Boolean(selected) && (!isHotel || stayReady);
  const dayText = (value: string, at = "") => `${dayLabel(dates.indexOf(value))}${at ? ` ${formatMeridiemTime(at)}` : ""}`;
  const stayText = (start: string, end: string) => {
    const nights = Math.round((new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86400000);
    return `${formatShortDate(start)} ~ ${formatShortDate(end)} · ${nights}박`;
  };

  /** 지금 입력 중인 일정 (장소를 골랐거나, 항공편의 출발·도착 공항을 골랐을 때만) */
  const current = (): PendingEntry | null => {
    if (isFlight) {
      if (!departure.airport || !arrival.airport) return null;
      const number = flightNumber ? airline.code + flightNumber : "";
      const name = [airline.name.trim(), number].filter(Boolean).join(" · ") || "항공편";
      return {
        key: `flight-${(flightSeq.current += 1)}`,
        kind,
        when: dayText(day, time),
        day,
        name,
        detail: `${departure.airport.name} → ${arrival.airport.name}`,
        identity: `${number}|${departure.airport.id}|${arrival.airport.id}|${day}`,
        payload: {
          kind: "flight",
          day,
          time,
          airline: airline.name.trim(),
          flight_number: number,
          departure_airport: airportPayload(departure),
          arrival_airport: airportPayload(arrival),
        },
      };
    }
    if (!selected) return null;
    if (isHotel) {
      if (!checkIn || !checkOut) return null;
      return {
        key: sessionToken,
        kind,
        name: selected.name,
        detail: "",
        when: stayText(checkIn, checkOut),
        day: checkIn,
        identity: `${selected.place_id}|${checkIn}`,
        payload: {
          kind: "hotel",
          place_id: selected.place_id,
          session_token: sessionToken,
          city_code: cityCode ?? "",
          check_in: checkIn,
          check_out: checkOut,
        },
      };
    }
    return {
      key: sessionToken,
      kind,
      name: selected.name,
      detail: "",
      when: dayText(day, time),
      day,
      identity: `${selected.place_id}|${day}`,
      payload: { kind, day, time, place_id: selected.place_id, session_token: sessionToken },
    };
  };

  const isDuplicate = (entry: PendingEntry) => pending.some((item) => item.identity === entry.identity);

  /** 담은 일정의 입력만 비운다(유형·날짜·항공사는 다음 일정에도 그대로 쓴다). */
  const clearCurrent = (entry: PendingEntry) => {
    setTime("");
    if ("check_in" in entry.payload) {
      setCheckIn("");
      setCheckOut("");
    }
    if (entry.payload.kind === "flight") {
      setFlightNumber("");
      setDeparture(EMPTY_AIRPORT);
      setArrival(EMPTY_AIRPORT);
    } else {
      setSelected(null);
      setQuery("");
      setSessionToken(crypto.randomUUID());
    }
  };

  const addToList = () => {
    const entry = current();
    if (!entry) return;
    setError("");
    if (isDuplicate(entry)) {
      setError(entry.payload.kind === "flight" ? "같은 날짜에 이미 담은 항공편이에요." : "같은 날짜에 이미 담은 장소예요.");
      return;
    }
    setPending((list) => [...list, entry]);
    clearCurrent(entry);
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
        onSaved(await addItineraryPlace(trip.id, item.payload));
      } catch (err) {
        // 등록하지 못한 일정부터 목록에 남겨 다시 시도할 수 있게 한다.
        setPending(entries.slice(index));
        if (entry) clearCurrent(entry);
        setError(`${item.name}: ${toErrorMessage(err)}`);
        setSaving(false);
        return;
      }
    }
    onDone(entries[0].day);
  };

  const total = pending.length + (ready ? 1 : 0);
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

        {isFlight ? (
          <div className="space-y-3">
            <AirlineFlightFields
              id="flight-airline"
              airlineLabelText="항공사"
              flightLabelText="편명"
              airline={airline.name}
              airlineCode={airline.code}
              flightNumber={flightNumber}
              onAirlineChange={setAirline}
              onFlightNumberChange={setFlightNumber}
              compact
            />
            <div className="grid grid-cols-2 gap-3">
              <AirportInput
                id="flight-departure"
                label="출발 공항"
                ariaLabel="출발 공항"
                value={departure}
                onChange={setDeparture}
                compact
              />
              <AirportInput
                id="flight-arrival"
                label="도착 공항"
                ariaLabel="도착 공항"
                value={arrival}
                onChange={setArrival}
                compact
              />
            </div>
          </div>
        ) : (
          <div>
            <label htmlFor="place-query" className={LABEL_CLASS}>
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
        )}

        {isHotel ? (
          <div>
            <p className={LABEL_CLASS}>숙박 기간</p>
            <StayRangeField
              checkIn={checkIn}
              checkOut={checkOut}
              min={trip.start_date}
              max={trip.end_date}
              otherStays={takenStays}
              ariaLabel="숙박 기간"
              compact
              onChange={(start, end) => {
                setCheckIn(start);
                setCheckOut(end);
              }}
            />
            <p className={`mt-1.5 text-xs ${hasFreeNight ? "text-slate-400" : "text-rose-600"}`}>
              {hasFreeNight
                ? `여행 기간(${formatMonthDay(trip.start_date)} ~ ${formatMonthDay(trip.end_date)}) 안에서, 다른 숙소와 겹치지 않게 고를 수 있어요.`
                : "여행 기간의 모든 밤에 이미 숙소가 있어요. 기존 숙소를 지우거나 기간을 바꾼 뒤 추가해 주세요."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="place-day" className={LABEL_CLASS}>
                날짜
              </label>
              <select
                id="place-day"
                value={day}
                onChange={(event) => setDay(event.target.value)}
                // 기본 select는 줄 높이 때문에 1px 커서 다른 칸(42px)과 맞춘다.
                className={`${inputClass} h-[42px]`}
              >
                {dates.map((date, index) => (
                  <option key={date} value={date}>
                    {dayLabel(index)} · {formatMonthDay(date)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className={LABEL_CLASS}>
                시간 <span className="font-normal text-slate-400">(선택)</span>
              </p>
              <TimeField
                value={time}
                onChange={setTime}
                ariaLabel="시간 (선택)"
                placeholder="시간 미정"
                optional
                compact
              />
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={addToList}
          disabled={!ready || saving}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-indigo-300 py-2.5 text-sm font-semibold text-indigo-600 transition-colors hover:bg-indigo-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-300"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />
          {isFlight ? "항공편 더 추가하기" : isHotel ? "숙소 더 추가하기" : "장소 더 추가하기"}
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
                    <p className="truncate text-sm font-medium text-slate-800">{item.name}</p>
                    <p className="truncate text-xs text-slate-400">
                      {item.detail || KIND_STYLE[item.kind].label} · {item.when}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPending((list) => list.filter((entry) => entry.key !== item.key))}
                    disabled={saving}
                    aria-label={`${item.name} 빼기`}
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
          {isHotel
            ? "체크인·숙박·체크아웃 카드가 경로에 함께 들어가고, 요약의 숙소 정보에도 등록돼요."
            : "그날 일정 중 이동 거리가 가장 적게 늘어나는 자리에 넣어요. 시간을 정하면 시간 순서에 맞춰 넣어요."}
        </p>
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </form>
    </Drawer>
  );
}
