import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  deleteItineraryItem,
  getItinerary,
  getTrip,
  initItinerary,
  reorderItinerary,
  toErrorMessage,
} from "../api/client";
import { ROUTES } from "../routes";
import type { Airport, ItineraryItem, ItineraryResponse, PlaceKind, Trip } from "../types/api";
import { formatMeridiemTime } from "../components/pickers";
import { formatMonthDay, todayISODate } from "../utils/date";
import AddPlaceDrawer from "./AddPlaceDrawer";
import AiPlannerDrawer, { type Message as AiMessage } from "./AiPlannerDrawer";
import TripItinerary from "./TripItinerary";
import TripMap from "./TripMap";
import { cityPoints, dayLabel, initialCards, numberStops, tripDates } from "./tripDays";
import { dDayLabel, tripColor } from "./tripUtils";

/** 여행 상세로 이동할 때 넘기는 라우터 state (있으면 서버 응답 전에 바로 그린다) */
export interface TripDetailState {
  trip: Trip;
  /** 새 여행 만들기를 막 마쳤는지 (완료 안내 표시) */
  created?: boolean;
}

const CARD_CLASS = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

/** "2026-10-12T09:00:00+09:00" -> "10월 12일 (월) 09:00" */
const formatDateTime = (value?: string | null) =>
  value ? `${formatMonthDay(value.slice(0, 10))} ${value.slice(11, 16)}` : "";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-slate-100 pt-4 first:border-t-0 first:pt-0">
      <h3 className="mb-2 text-xs font-semibold text-slate-400">{title}</h3>
      {children}
    </section>
  );
}

const Empty = ({ children }: { children: ReactNode }) => (
  <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-400">{children}</p>
);

interface FlightLegProps {
  label: string;
  airline?: string;
  flightNumber?: string;
  from?: Airport | null;
  to?: Airport | null;
  when: string;
  whenLabel: string;
}

function FlightLeg({ label, airline, flightNumber, from, to, when, whenLabel }: FlightLegProps) {
  return (
    <div className="rounded-xl bg-slate-50 px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-indigo-600">{label}</span>
        <span className="truncate text-xs text-slate-500">
          {[airline, flightNumber].filter(Boolean).join(" · ") || "항공편 정보 없음"}
        </span>
      </div>
      <p className="mt-1.5 flex items-center gap-2 text-sm font-medium text-slate-800">
        <span className="truncate">{from?.name ?? "출발 공항 미지정"}</span>
        <i className="fas fa-arrow-right shrink-0 text-[10px] text-slate-300" aria-hidden="true" />
        <span className="truncate">{to?.name ?? "도착 공항 미지정"}</span>
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {whenLabel} {when || "미정"}
      </p>
    </div>
  );
}

/** 경로에서 추가한 숙소: 같은 숙소(장소 ID, 없으면 이름)를 묶고 그 숙소가 들어간 날짜들을 모은다. */
interface RouteHotel {
  key: string;
  name: string;
  address: string;
  days: string[];
}

function routeHotels(trip: Trip, items: ItineraryItem[]): RouteHotel[] {
  // 여행을 만들 때 등록한 숙소와 같은 곳은 이미 보여주므로 뺀다.
  const registered = new Set(trip.hotels.flatMap((hotel) => [hotel.place_id, hotel.name].filter(Boolean)));
  const groups = new Map<string, RouteHotel>();
  items
    .filter((item) => item.kind === "hotel" && item.source !== "auto")
    .filter((item) => !registered.has(item.place_id) && !registered.has(item.title))
    .forEach((item) => {
      const key = item.place_id || item.title;
      const group = groups.get(key) ?? { key, name: item.title, address: item.address, days: [] };
      if (!group.days.includes(item.day)) group.days.push(item.day);
      groups.set(key, group);
    });
  return [...groups.values()]
    .map((group) => ({ ...group, days: [...group.days].sort() }))
    .sort((a, b) => a.days[0].localeCompare(b.days[0]));
}

/** "11월 11일 (수)" 또는 "11월 11일 (수) ~ 11월 12일 (목)" */
const dayRange = (days: string[]) =>
  days.length > 1
    ? `${formatMonthDay(days[0])} ~ ${formatMonthDay(days[days.length - 1])}`
    : formatMonthDay(days[0]);

/** 요약 카드의 숙소 한 곳: 숙소명 / 묵는 기간 / 주소를 한 줄씩 (긴 숙소명도 자르지 않고 줄바꿈) */
function HotelSummary({ name, period, address }: { name: string; period: string; address: string }) {
  return (
    <li className="flex flex-col gap-1 rounded-xl bg-slate-50 px-3.5 py-3">
      <p className="break-words text-sm font-semibold text-slate-800">{name}</p>
      <p className="flex items-center gap-1.5 text-xs text-slate-500">
        <i className="far fa-calendar text-[11px] text-slate-400" aria-hidden="true" />
        {period}
      </p>
      {address && (
        <p className="flex gap-1.5 break-words text-xs text-slate-400">
          <i className="fas fa-map-marker-alt mt-0.5 text-[11px] text-slate-300" aria-hidden="true" />
          <span className="min-w-0">{address}</span>
        </p>
      )}
    </li>
  );
}

/** 비어 있을 때: 안내 + 바로 추가 버튼 */
function EmptyWithAction({ children, action, onClick }: { children: ReactNode; action: string; onClick?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5">
      <p className="text-sm text-slate-400">{children}</p>
      {onClick && (
        <button
          type="button"
          onClick={onClick}
          className="shrink-0 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
        >
          <i className="fas fa-plus mr-1 text-[10px]" aria-hidden="true" />
          {action}
        </button>
      )}
    </div>
  );
}

interface TripBasicsProps {
  trip: Trip;
  /** 저장된 일정 (불러오기 전이면 null) */
  items: ItineraryItem[] | null;
  /** 요약 카드에서 숙소·공항 직접 추가 열기 */
  onAdd?: (kind: PlaceKind) => void;
}

/**
 * 기본 정보: 항공(출국·귀국 일시) · 여행지 · 숙소.
 * 여행을 만들 때 등록한 항공·숙소에 더해, 여행 경로에서 추가한 공항·숙소도 함께 보여준다.
 * 항공·숙소는 선택 입력이라 비어 있으면 안내와 바로 추가 버튼을 보여준다.
 */
function TripBasics({ trip, items, onAdd }: TripBasicsProps) {
  const flight = trip.flight_info;
  // 경로에서 가는 편·오는 편 카드를 지우면 그 편의 정보가 비워진다. 남은 편만 보여준다.
  const hasOutbound = Boolean(
    flight &&
      (flight.departure_airport || flight.arrival_airport || flight.airline || flight.flight_number || flight.departure_at),
  );
  const hasReturn = Boolean(
    flight &&
      (flight.return_departure_airport ||
        flight.return_arrival_airport ||
        flight.return_airline ||
        flight.return_flight_number ||
        flight.return_arrival_at),
  );
  const routeItems = items ?? [];
  const byDayOrder = (a: ItineraryItem, b: ItineraryItem) => a.day.localeCompare(b.day) || a.order - b.order;
  // 경로에서 추가한 항공편(출발 공항 -> 도착 공항)과 공항
  const routeFlights = routeItems.filter((item) => item.kind === "flight" && item.source !== "auto").sort(byDayOrder);
  const airports = routeItems.filter((item) => item.kind === "airport" && item.source !== "auto").sort(byDayOrder);
  const hotels = routeHotels(trip, routeItems);
  const addAirport = onAdd && (() => onAdd("airport"));
  const addHotel = onAdd && (() => onAdd("hotel"));

  return (
    <div className={`${CARD_CLASS} space-y-4`}>
      <Section title="항공">
        {hasOutbound || hasReturn || routeFlights.length > 0 || airports.length > 0 ? (
          <div className="space-y-2">
            {flight && hasOutbound && (
              <FlightLeg
                label="가는 편"
                airline={flight.airline}
                flightNumber={flight.flight_number}
                from={flight.departure_airport}
                to={flight.arrival_airport}
                when={formatDateTime(flight.departure_at)}
                whenLabel="출국"
              />
            )}
            {flight && hasReturn && (
              <FlightLeg
                label="오는 편"
                airline={flight.return_airline}
                flightNumber={flight.return_flight_number}
                from={flight.return_departure_airport}
                to={flight.return_arrival_airport}
                when={formatDateTime(flight.return_arrival_at)}
                whenLabel="귀국"
              />
            )}
            {routeFlights.map((item) => (
              <FlightLeg
                key={item.id}
                label="항공편"
                airline={item.title}
                from={item.stops[0] && { code: "", name: item.stops[0].label }}
                to={item.stops[1] && { code: "", name: item.stops[1].label }}
                when={`${formatMonthDay(item.day)}${item.time ? ` ${formatMeridiemTime(item.time)}` : ""}`}
                whenLabel="출발"
              />
            ))}
            {airports.length > 0 && (
              <ul className="space-y-2" aria-label="경로에서 추가한 공항">
                {airports.map((item) => (
                  <li key={item.id} className="rounded-xl bg-slate-50 px-3.5 py-3">
                    <p className="truncate text-sm font-medium text-slate-800">{item.title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatMonthDay(item.day)}
                      {item.time ? ` ${formatMeridiemTime(item.time)}` : ""}
                    </p>
                    {item.address && <p className="mt-0.5 break-words text-xs text-slate-400">{item.address}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <EmptyWithAction action="공항 추가" onClick={addAirport}>
            등록된 항공권이 없어요. 날짜만 등록한 여행이에요.
          </EmptyWithAction>
        )}
      </Section>

      <Section title="여행지">
        {trip.destinations.length > 0 ? (
          <ol className="flex flex-wrap items-center gap-1.5">
            {trip.destinations.map((dest, index) => (
              <li key={`${dest.city}-${index}`} className="flex items-center gap-1.5">
                {index > 0 && <i className="fas fa-arrow-right text-[10px] text-slate-300" aria-hidden="true" />}
                <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                  {dest.city}
                  {dest.city_code && <span className="ml-1 text-indigo-400">{dest.city_code}</span>}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <Empty>등록된 여행지가 없어요.</Empty>
        )}
      </Section>

      <Section title="숙소">
        {trip.hotels.length > 0 || hotels.length > 0 ? (
          <ul className="space-y-2">
            {[...trip.hotels]
              .sort((a, b) => a.check_in.localeCompare(b.check_in))
              .map((hotel) => (
                <HotelSummary
                  key={hotel.id}
                  name={hotel.name}
                  period={`${formatMonthDay(hotel.check_in)}${hotel.check_out ? ` ~ ${formatMonthDay(hotel.check_out)}` : ""}${
                    hotel.nights ? ` · ${hotel.nights}박` : ""
                  }`}
                  address={hotel.address}
                />
              ))}
            {hotels.map((hotel) => (
              <HotelSummary key={hotel.key} name={hotel.name} period={dayRange(hotel.days)} address={hotel.address} />
            ))}
          </ul>
        ) : (
          <EmptyWithAction action="숙소 추가" onClick={addHotel}>
            등록된 숙소가 없어요.
          </EmptyWithAction>
        )}
      </Section>
    </div>
  );
}

/** 숙소 정보까지 지우는 카드 (등록 숙소의 체크인·체크아웃 카드) */
const removesHotel = (item: ItineraryItem) =>
  item.source === "auto" && item.kind === "hotel" && (item.time_label === "체크인" || item.time_label === "체크아웃");

/** 숙소 체크인·체크아웃 카드를 지우기 전 확인: 숙소 정보와 그 숙소의 카드가 모두 지워진다. */
function HotelDeleteDialog({ item, onCancel, onConfirm }: { item: ItineraryItem; onCancel: () => void; onConfirm: () => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onCancel();
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 px-4" onClick={onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="hotel-delete-title"
        aria-describedby="hotel-delete-description"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl"
      >
        <h2 id="hotel-delete-title" className="text-base font-bold text-slate-900">
          숙소 정보를 삭제할까요?
        </h2>
        <p id="hotel-delete-description" className="mt-2 text-sm leading-relaxed text-slate-600">
          '{item.title}'의 {item.time_label} 카드를 지우면 이 숙소 정보가 아예 삭제돼요. 
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700"
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  );
}

/** 일자 탭: 첫째 날, 둘째 날 ... */
function DayTabs({ dates, selected, onSelect }: { dates: string[]; selected: number; onSelect: (index: number) => void }) {
  return (
    <div role="tablist" aria-label="일자" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
      {dates.map((date, index) => {
        const active = index === selected;
        return (
          <button
            key={date}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(index)}
            className={`shrink-0 rounded-xl border px-3.5 py-2 text-left transition-colors ${
              active
                ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
            }`}
          >
            <span className="block text-sm font-semibold">{dayLabel(index)}</span>
            <span className={`block text-[11px] ${active ? "text-indigo-500" : "text-slate-400"}`}>
              {formatMonthDay(date)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

type Panel = "ai" | "add" | null;

const BUTTON_BASE =
  "flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold transition-colors";
const OUTLINE_BUTTON = `${BUTTON_BASE} border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50`;

/** 여행 경로 카드 머리의 일정 메뉴: AI와 함께 만들기 · 직접 추가 */
function RouteMenu({ onOpen }: { onOpen: (panel: Exclude<Panel, null>) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:flex">
      <button
        type="button"
        onClick={() => onOpen("ai")}
        className={`${BUTTON_BASE} bg-indigo-600 text-white hover:bg-indigo-700`}
      >
        <i className="fas fa-magic text-xs" aria-hidden="true" />
        AI와 함께 만들기
      </button>
      <button type="button" onClick={() => onOpen("add")} className={OUTLINE_BUTTON}>
        <i className="fas fa-plus text-xs" aria-hidden="true" />
        직접 추가
      </button>
    </div>
  );
}

/** 여행 제목 오른쪽 끝의 일행 초대하기 (준비 중) */
function InviteButton() {
  const [notice, setNotice] = useState("");
  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => setNotice("'일행 초대하기'는 준비 중이에요.")}
        className={`${OUTLINE_BUTTON} whitespace-nowrap`}
      >
        <i className="fas fa-user-plus text-xs" aria-hidden="true" />
        일행 초대하기
      </button>
      {notice && (
        <p role="status" className="text-xs text-slate-500">
          {notice}
        </p>
      )}
    </div>
  );
}

/**
 * `/trips/:tripId` 여행 상세.
 * - 제목 오른쪽 끝에 일행 초대하기, 여행 경로 카드 머리에 AI와 함께 만들기 · 직접 추가
 * - 넓은 화면: [지도 | 항공·여행지·숙소] 아래에 여행 경로 / 좁은 화면: 정보 → 지도 → 경로
 * - 일정은 서버에 저장된다. 처음 열 때 항공편·숙소 카드를 한 번 만들어 저장한다.
 * - 지도 핀 번호는 일정 카드 순서를 따르고, 카드를 끌어 순서를 바꾸면 번호도 바뀐다.
 */
export default function TripDetailPage() {
  const { tripId } = useParams();
  const state = useLocation().state as TripDetailState | null;
  const [trip, setTrip] = useState<Trip | null>(state?.trip ?? null);
  const [items, setItems] = useState<ItineraryItem[] | null>(null);
  const [error, setError] = useState("");
  const [routeError, setRouteError] = useState("");
  const [dayIndex, setDayIndex] = useState(0);
  const [panel, setPanel] = useState<Panel>(null);
  const [hotelDelete, setHotelDelete] = useState<ItineraryItem | null>(null);
  // AI 대화는 창을 닫았다 열어도 이어진다(이 여행 화면에 있는 동안).
  const [aiMessages, setAiMessages] = useState<AiMessage[]>([]);
  useEffect(() => setAiMessages([]), [tripId]);
  const [addKind, setAddKind] = useState<PlaceKind>("sight");

  useEffect(() => {
    const id = Number(tripId);
    if (!Number.isInteger(id)) {
      setError("여행을 찾을 수 없어요.");
      return undefined;
    }
    let cancelled = false;
    Promise.all([getTrip(id), getItinerary(id)])
      .then(async ([data, itinerary]) => {
        if (cancelled) return;
        setTrip(data);
        const loaded = itinerary.initialized ? itinerary : await initItinerary(id, initialCards(data));
        if (!cancelled) setItems(loaded.items);
      })
      .catch((err: unknown) => !cancelled && setError(toErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [tripId]);

  const dates = useMemo(() => (trip ? tripDates(trip) : []), [trip]);
  const day = dates[dayIndex] ?? dates[0];
  const dayItems = useMemo(() => (items ?? []).filter((item) => item.day === day), [items, day]);
  const { points, numbers } = useMemo(() => numberStops(dayItems), [dayItems]);
  // 그날 좌표가 있는 위치가 없으면 여행 도시를 대신 보여준다.
  const fallbackPoints = useMemo(() => (trip && points.length === 0 ? cityPoints(trip) : []), [trip, points]);
  const mapPoints = points.length > 0 ? points : fallbackPoints;

  const replaceDay = (dayValue: string, next: ItineraryItem[]) =>
    setItems((current) => [...(current ?? []).filter((item) => item.day !== dayValue), ...next]);

  // 순서는 바로 반영하고 저장한다. 저장에 실패하면 되돌린다.
  const onReorder = (next: ItineraryItem[]) => {
    if (!trip || !day) return;
    const previous = dayItems;
    replaceDay(day, next);
    setRouteError("");
    reorderItinerary(
      trip.id,
      day,
      next.map((item) => item.id),
    )
      .then((itinerary) => setItems(itinerary.items))
      .catch((err: unknown) => {
        replaceDay(day, previous);
        setRouteError(toErrorMessage(err));
      });
  };

  const removeCard = (id: number) => {
    setRouteError("");
    deleteItineraryItem(id)
      .then((result) => {
        const removed = new Set(result?.removed_ids ?? [id]);
        setItems((current) => (current ?? []).filter((item) => !removed.has(item.id)));
        // 항공·숙소 카드를 지우면 요약 카드도 바뀐 등록 정보로 맞춘다.
        if (result) setTrip(result.trip);
      })
      .catch((err: unknown) => setRouteError(toErrorMessage(err)));
  };

  // 숙소 체크인·체크아웃 카드는 숙소 정보까지 지우므로 먼저 확인한다.
  const onRemove = (id: number) => {
    const item = items?.find((card) => card.id === id);
    if (item && removesHotel(item)) setHotelDelete(item);
    else removeCard(id);
  };
  const cancelHotelDelete = useCallback(() => setHotelDelete(null), []);

  const closePanel = useCallback(() => setPanel(null), []);

  const onPlacesSaved = (itinerary: ItineraryResponse & { trip?: Trip }) => {
    setItems(itinerary.items);
    // 숙소를 숙박 기간과 함께 등록하면 요약 카드(숙소)도 바뀐다.
    if (itinerary.trip) setTrip(itinerary.trip);
  };

  const onPlacesDone = (addedDay: string) => {
    setDayIndex(Math.max(0, dates.indexOf(addedDay)));
    setPanel(null);
  };

  if (!trip) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {error ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
            <p className="text-sm text-slate-600">{error}</p>
            <Link to={ROUTES.MY_TRIPS} className="mt-3 inline-block text-sm font-semibold text-indigo-600">
              내 여행으로 돌아가기
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="h-10 w-64 animate-pulse rounded-xl bg-slate-200/70" />
            <div className="h-96 animate-pulse rounded-2xl bg-slate-200/70" />
          </div>
        )}
      </div>
    );
  }

  const today = todayISODate();
  // 방금 만든 여행: 첫째 날의 출발 공항 → 도착 공항 → 첫 숙소를 맨 위에 한 줄로 보여준다.
  // 공항은 공항명, 숙소는 숙소명으로 보여준다.
  const firstDayStops = (items ?? [])
    .filter((item) => item.day === dates[0])
    .flatMap((item) => (item.kind === "flight" ? item.stops.map((stop) => stop.label) : [item.title]));

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <Link
        to={ROUTES.MY_TRIPS}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-800"
      >
        <i className="fas fa-arrow-left text-xs" aria-hidden="true" />내 여행
      </Link>

      {state?.created && (
        <div role="status" className="mt-4 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3">
          <p className="text-sm font-semibold text-emerald-800">여행이 만들어졌어요. 첫째 날부터 경로를 채워 보세요.</p>
          {firstDayStops.length > 0 && (
            <ol className="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-emerald-900" aria-label="첫째 날 이동">
              {firstDayStops.map((label, index) => (
                <li key={`${label}-${index}`} className="flex items-center gap-1.5">
                  {index > 0 && <i className="fas fa-arrow-right text-[10px] text-emerald-400" aria-hidden="true" />}
                  <span className="rounded-full bg-white px-2.5 py-1 font-medium shadow-sm">{label}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      <header className="mb-6 mt-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`h-3 w-3 rounded-full ${tripColor(trip).dot}`} aria-hidden="true" />
            <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">{trip.destination_label} 여행</h1>
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
              {dDayLabel(trip, today)}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {formatMonthDay(trip.start_date)} ~ {formatMonthDay(trip.end_date)} · {trip.nights}박 {trip.nights + 1}일
          </p>
        </div>
        <InviteButton />
      </header>

      {/* 좁은 화면: 정보 → 지도 → 경로 / 넓은 화면: [지도 | 정보] 아래 경로 */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <section aria-label="여행 지도" className={`${CARD_CLASS} order-2 flex flex-col lg:order-1`}>
          <div className="mb-3 flex items-baseline justify-between gap-2">
            <h2 className="text-base font-bold text-slate-900">{day ? `${dayLabel(dayIndex)} 이동` : "이동 경로"}</h2>
            {points.length === 0 && fallbackPoints.length > 0 && (
              <span className="text-xs text-slate-400">이 날 위치가 없어 여행 도시를 표시해요</span>
            )}
          </div>
          <TripMap points={mapPoints} className="h-72 sm:h-96 lg:h-auto lg:min-h-[24rem] lg:flex-1" />
        </section>

        <div className="order-1 lg:order-2">
          <TripBasics
            trip={trip}
            items={items}
            onAdd={
              items === null
                ? undefined
                : (kind) => {
                    setAddKind(kind);
                    setPanel("add");
                  }
            }
          />
        </div>

        <section aria-label="여행 경로" className={`${CARD_CLASS} order-3 space-y-5 lg:col-span-2`}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-base font-bold text-slate-900">여행 경로</h2>
            <RouteMenu
              onOpen={(next) => {
                setAddKind("sight");
                setPanel(next);
              }}
            />
          </div>
          <DayTabs dates={dates} selected={dayIndex} onSelect={setDayIndex} />
          {routeError && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{routeError}</p>}
          <div className="lg:max-w-3xl">
            {items === null ? (
              error ? (
                <p className="text-sm text-rose-600">{error}</p>
              ) : (
                <div className="h-32 animate-pulse rounded-2xl bg-slate-100" />
              )
            ) : (
              <TripItinerary
                items={dayItems}
                numbers={numbers}
                onReorder={onReorder}
                onRemove={onRemove}
              />
            )}
          </div>
        </section>
      </div>

      {hotelDelete && (
        <HotelDeleteDialog
          item={hotelDelete}
          onCancel={cancelHotelDelete}
          onConfirm={() => {
            removeCard(hotelDelete.id);
            setHotelDelete(null);
          }}
        />
      )}
      {panel === "add" && day && (
        <AddPlaceDrawer
          trip={trip}
          dates={dates}
          initialDay={day}
          initialKind={addKind}
          onClose={closePanel}
          onSaved={onPlacesSaved}
          onDone={onPlacesDone}
        />
      )}
      {panel === "ai" && (
        <AiPlannerDrawer
          trip={trip}
          dates={dates}
          messages={aiMessages}
          setMessages={setAiMessages}
          onClose={closePanel}
          onApplied={(itinerary, updatedTrip) => {
            setItems(itinerary.items);
            setTrip(updatedTrip);
          }}
        />
      )}
    </div>
  );
}

