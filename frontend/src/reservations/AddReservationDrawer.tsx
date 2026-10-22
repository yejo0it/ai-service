import { useMemo, useState } from "react";
import { applyTripReservation, previewTripReservation, toErrorMessage } from "../api/client";
import Drawer from "../trips/Drawer";
import { segmentCard, stayCards } from "../trips/tripDays";
import type {
  FlightBooking,
  Hotel,
  HotelBooking,
  HotelPlacePick,
  ItineraryCardInput,
  ItineraryItem,
  ReservationKind,
  ReservationPreview,
  ReservationResult,
  Trip,
} from "../types/api";
import { formatMonthDay } from "../utils/date";
import ReservationFlow from "./ReservationFlow";
import { HotelPlaceSearch } from "./ReservationTripWizard";

interface AddReservationDrawerProps {
  trip: Trip;
  kind: ReservationKind;
  /** 저장된 예약 항공편을 고칠 때: 지금 구간을 확인 화면에 불러오고 전체 교체로 저장한다. */
  editFlight?: boolean;
  onClose: () => void;
  onSaved: (trip: Trip, items: ItineraryItem[]) => void;
}

const SECTION_TITLE = "mb-2 text-xs font-semibold text-slate-500";

/** 저장된 비행 구간 -> 확인 화면에서 고칠 수 있는 예약 정보 */
function bookingFromTrip(trip: Trip): FlightBooking {
  return {
    itineraries: [
      {
        status: null,
        segments: (trip.flight_segments ?? []).map((segment) => ({
          airline_name: segment.airline_name || null,
          flight_number: segment.flight_number,
          departure_airport_code: segment.departure_airport_code,
          departure_airport_name: segment.departure_airport_name || null,
          arrival_airport_code: segment.arrival_airport_code,
          arrival_airport_name: segment.arrival_airport_name || null,
          departure_date: segment.departure_date,
          departure_time: segment.departure_time,
          arrival_date: segment.arrival_date,
          arrival_time: segment.arrival_time,
          direction: segment.direction,
          notes: [],
        })),
      },
    ],
  };
}

/**
 * 기존 여행에 예약 확인서 추가: 업로드·확인(1단계 화면) → 변경 미리보기 → 저장.
 * 미리보기에서 경로에 넣을 카드와 시간이 겹치는 기존 일정 중 지울 것을 사용자가 직접 고르고,
 * '예약 정보만 저장'과 '저장하고 경로에 반영' 중 하나를 누른다. 기존 일정은 고른 것 말고는 바뀌지 않는다.
 */
export default function AddReservationDrawer({ trip, kind, editFlight = false, onClose, onSaved }: AddReservationDrawerProps) {
  const [document, setDocument] = useState<FlightBooking | HotelBooking | null>(null);
  const [preview, setPreview] = useState<ReservationPreview | null>(null);
  const [mode, setMode] = useState<"add" | "replace">(editFlight ? "replace" : "add");
  const [decisions, setDecisions] = useState<("skip" | "replace")[]>([]);
  const [places, setPlaces] = useState<(HotelPlacePick | null)[]>([]);
  const [searching, setSearching] = useState<number | null>(null);
  const [extend, setExtend] = useState(false);
  const [skippedCards, setSkippedCards] = useState<Set<number>>(new Set());
  const [removeIds, setRemoveIds] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const initial = useMemo<ReservationResult | null>(
    () => (editFlight ? { kind: "flight", document: bookingFromTrip(trip), valid: true, errors: [], warnings: [] } : null),
    [editFlight, trip],
  );

  const payload = (doc: FlightBooking | HotelBooking, nextMode = mode, nextDecisions = decisions) =>
    kind === "flight"
      ? { flight: doc as FlightBooking, flight_mode: nextMode }
      : { hotels: doc as HotelBooking, hotel_decisions: nextDecisions, hotel_places: places };

  const loadPreview = async (doc: FlightBooking | HotelBooking, nextMode = mode, nextDecisions = decisions) => {
    setBusy(true);
    setError("");
    try {
      setPreview(await previewTripReservation(trip.id, payload(doc, nextMode, nextDecisions)));
      setSkippedCards(new Set());
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  // 경로에 넣을 새 카드: 새 구간과 저장할 숙소(추가·교체)
  const newCards = useMemo<ItineraryCardInput[]>(() => {
    if (!preview) return [];
    const { start, end } = preview.dates;
    const flightCards = (preview.flight?.new ?? []).map((segment, order) =>
      segmentCard({
        order,
        direction: segment.direction,
        airline_name: segment.airline_name ?? "",
        flight_number: segment.flight_number ?? "",
        departure_airport_code: segment.departure_airport_code ?? "",
        departure_airport_name: segment.departure_airport_name ?? "",
        arrival_airport_code: segment.arrival_airport_code ?? "",
        arrival_airport_name: segment.arrival_airport_name ?? "",
        departure_date: segment.departure_date ?? start,
        departure_time: segment.departure_time ?? "",
        arrival_date: segment.arrival_date,
        arrival_time: segment.arrival_time,
        status: segment.status ?? "",
      }),
    );
    const hotelCards = preview.hotels
      .filter((entry) => entry.status === "new" || entry.status === "replace")
      .flatMap((entry) => {
        const place = places[entry.index];
        const stay = entry.stay;
        const nights = stay.check_in_date && stay.check_out_date
          ? Math.round((Date.parse(stay.check_out_date) - Date.parse(stay.check_in_date)) / 86_400_000)
          : null;
        const hotel: Hotel = {
          id: 0,
          name: stay.name ?? "",
          address: place?.address || stay.address || "",
          place_id: place?.place_id ?? "",
          latitude: place?.latitude ?? null,
          longitude: place?.longitude ?? null,
          phone: place?.phone ?? "",
          city_code: "",
          check_in: stay.check_in_date ?? start,
          check_out: stay.check_out_date,
          check_in_time: stay.check_in_time,
          check_out_time: stay.check_out_time,
          nights,
        };
        return stayCards(hotel, start, end);
      });
    return [...flightCards, ...hotelCards];
  }, [preview, places]);

  const save = async (reflect: boolean) => {
    if (!document || !preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await applyTripReservation(trip.id, {
        ...payload(document),
        extend_dates: extend,
        reflect,
        cards: reflect ? newCards.filter((_, index) => !skippedCards.has(index)) : [],
        remove_item_ids: reflect ? [...removeIds] : [],
      });
      onSaved(result.trip, result.items);
    } catch (err) {
      setError(toErrorMessage(err));
      setBusy(false);
    }
  };

  const toggle = (set: Set<number>, value: number) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  };

  const title = editFlight ? "예약 항공편 수정" : kind === "flight" ? "항공권 예약 추가" : "숙소 예약 추가";
  const nothingNew =
    preview && (preview.flight?.new.length ?? 0) === 0 && !preview.hotels.some((h) => h.status === "new" || h.status === "replace");
  const needsConsent = Boolean(preview?.dates.extend && !extend);
  const hasSegments = (trip.flight_segments?.length ?? 0) > 0;

  return (
    <Drawer title={title} onClose={onClose}>
      {!preview ? (
        <div className="space-y-3">
          {kind === "flight" && !hasSegments && trip.flight_info && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">
              지금 등록된 항공 정보는 예약 확인서의 항공편으로 바뀌어요(저장 전에 미리보기로 확인할 수 있어요).
            </p>
          )}
          <ReservationFlow
            fixedKind={kind}
            initial={initial}
            confirmLabel="변경 내용 미리보기"
            onConfirmed={(result) => {
              setDocument(result.document);
              loadPreview(result.document);
            }}
          />
          {busy && <p className="text-sm text-slate-500">변경 내용을 계산하고 있어요…</p>}
          {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>}
        </div>
      ) : (
        <div className="space-y-5 text-sm">
          {preview.flight && (
            <section aria-label="항공편">
              <h3 className={SECTION_TITLE}>항공편</h3>
              {preview.flight.legacy_replaced && (
                <p className="mb-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">직접 등록한 항공 정보를 예약 확인서의 항공편으로 바꿔요.</p>
              )}
              {hasSegments && !editFlight && (
                <div className="mb-2 inline-flex rounded-xl bg-slate-100 p-0.5" role="group" aria-label="저장 방식">
                  {(
                    [
                      ["add", "기존 항공편에 추가"],
                      ["replace", "전체 교체"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={mode === value}
                      onClick={() => {
                        setMode(value);
                        if (document) loadPreview(document, value);
                      }}
                      className={`rounded-[10px] px-3 py-1.5 text-xs font-semibold ${mode === value ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              <ul className="space-y-1">
                {preview.flight.new.map((segment, index) => (
                  <li key={`new-${index}`} className="rounded-lg bg-indigo-50 px-3 py-2 text-indigo-800">
                    + {segment.flight_number} {segment.departure_airport_code} → {segment.arrival_airport_code} ·{" "}
                    {segment.departure_date && formatMonthDay(segment.departure_date)} {segment.departure_time}
                  </li>
                ))}
                {preview.flight.duplicates.map((segment, index) => (
                  <li key={`dup-${index}`} className="rounded-lg bg-slate-50 px-3 py-2 text-slate-500">
                    {segment.flight_number} {segment.departure_date && formatMonthDay(segment.departure_date)} · 이미 등록된 항공편이라 건너뛰어요
                  </li>
                ))}
              </ul>
            </section>
          )}

          {preview.hotels.length > 0 && (
            <section aria-label="숙소">
              <h3 className={SECTION_TITLE}>숙소</h3>
              <ul className="space-y-2">
                {preview.hotels.map((entry) => (
                  <li key={entry.index} className="rounded-xl border border-slate-200 p-3">
                    <p className="font-semibold text-slate-800">{entry.stay.name}</p>
                    <p className="text-xs text-slate-500">
                      {entry.stay.check_in_date && formatMonthDay(entry.stay.check_in_date)} ~{" "}
                      {entry.stay.check_out_date && formatMonthDay(entry.stay.check_out_date)}
                    </p>
                    {entry.status === "duplicate" && <p className="mt-1 text-xs text-slate-500">이미 등록된 숙소라 건너뛰어요.</p>}
                    {(entry.status === "skip" || entry.status === "replace") && (
                      <div className="mt-2 space-y-1">
                        <p className="text-xs text-amber-700">
                          {entry.overlaps.map((hotel) => hotel.name).join(", ")}과(와) 숙박 기간이 겹쳐요.
                        </p>
                        {(["skip", "replace"] as const).map((value) => (
                          <label key={value} className="flex items-center gap-2 text-xs text-slate-700">
                            <input
                              type="radio"
                              name={`hotel-${entry.index}`}
                              checked={entry.status === value}
                              onChange={() => {
                                const next = [...decisions];
                                next[entry.index] = value;
                                setDecisions(next);
                                if (document) loadPreview(document, mode, next);
                              }}
                            />
                            {value === "skip" ? "이 숙소는 건너뛰기" : "기존 숙소를 이 숙소로 바꾸기(기존 숙소의 경로 카드도 빠져요)"}
                          </label>
                        ))}
                      </div>
                    )}
                    {(entry.status === "new" || entry.status === "replace") &&
                      (places[entry.index] ? (
                        <p className="mt-1 text-xs text-emerald-700">위치 연결됨 · {places[entry.index]?.address}</p>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setSearching(searching === entry.index ? null : entry.index)}
                          className="mt-1 text-xs font-medium text-indigo-600 hover:underline"
                        >
                          지도 위치 찾기(선택)
                        </button>
                      ))}
                    {searching === entry.index && !places[entry.index] && (
                      <HotelPlaceSearch
                        name={entry.stay.name ?? ""}
                        city=""
                        onPick={(place) => {
                          const next = [...places];
                          next[entry.index] = place;
                          setPlaces(next);
                          setSearching(null);
                        }}
                      />
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {preview.dates.extend && (
            <section aria-label="여행 기간" className="rounded-xl bg-amber-50 px-3 py-2 text-amber-800">
              <p className="text-xs">
                예약이 여행 기간 밖이에요. 여행 기간이 {formatMonthDay(preview.dates.current_start)} ~ {formatMonthDay(preview.dates.current_end)}에서{" "}
                <strong>
                  {formatMonthDay(preview.dates.start)} ~ {formatMonthDay(preview.dates.end)}
                </strong>
                로 늘어나요.
              </p>
              <label className="mt-1 flex items-center gap-2 text-xs font-semibold">
                <input type="checkbox" checked={extend} onChange={(event) => setExtend(event.target.checked)} />
                여행 기간을 늘리는 데 동의해요
              </label>
            </section>
          )}

          <section aria-label="여행 경로 반영">
            <h3 className={SECTION_TITLE}>여행 경로 반영 (고른 것만 반영돼요)</h3>
            {!preview.itinerary_initialized ? (
              <p className="text-xs text-slate-500">아직 여행 경로를 열지 않은 여행이라, 처음 열 때 예약 정보로 경로가 만들어져요.</p>
            ) : (
              <div className="space-y-3">
                {newCards.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs text-slate-500">경로에 추가할 카드</p>
                    {newCards.map((card, index) => (
                      <label key={index} className="flex items-center gap-2 py-0.5 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          checked={!skippedCards.has(index)}
                          onChange={() => setSkippedCards(toggle(skippedCards, index))}
                        />
                        {formatMonthDay(card.day)} {card.time} {card.title} ({card.time_label})
                      </label>
                    ))}
                  </div>
                )}
                {preview.replaced_cards.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs text-slate-500">함께 빠지는 카드(교체한 항공·숙소의 카드)</p>
                    <ul className="space-y-0.5 text-xs text-slate-500 line-through">
                      {preview.replaced_cards.map((card) => (
                        <li key={card.id}>
                          {formatMonthDay(card.day)} {card.time} {card.title}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {preview.conflicts.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs text-amber-700">시간이 겹치는 기존 일정(그대로 두거나, 지울 것만 고르세요)</p>
                    {preview.conflicts.map((item) => (
                      <label key={item.id} className="flex items-center gap-2 py-0.5 text-xs text-slate-700">
                        <input type="checkbox" checked={removeIds.has(item.id)} onChange={() => setRemoveIds(toggle(removeIds, item.id))} />
                        <span>
                          이 일정 지우기: {formatMonthDay(item.day)} {item.time} {item.title}
                          <span className="ml-1 text-slate-400">({item.reason})</span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
                {newCards.length === 0 && preview.conflicts.length === 0 && preview.replaced_cards.length === 0 && (
                  <p className="text-xs text-slate-500">경로에 바뀌는 내용이 없어요.</p>
                )}
              </div>
            )}
          </section>

          {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>}
          {nothingNew && <p className="text-xs text-slate-500">새로 저장할 예약이 없어요.</p>}

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => {
                setPreview(null);
                setError("");
              }}
              disabled={busy}
              className="rounded-xl border border-slate-200 px-4 py-2.5 font-medium text-slate-600 hover:bg-slate-50"
            >
              예약 정보 다시 확인
            </button>
            <button
              type="button"
              onClick={() => save(false)}
              disabled={busy || needsConsent || Boolean(nothingNew && preview.replaced_cards.length === 0)}
              className="rounded-xl border border-indigo-200 px-4 py-2.5 font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
            >
              예약 정보만 저장
            </button>
            <button
              type="button"
              onClick={() => save(true)}
              disabled={busy || needsConsent || !preview.itinerary_initialized}
              className="flex-1 rounded-xl bg-indigo-600 px-4 py-2.5 font-semibold text-white hover:bg-indigo-700 disabled:bg-indigo-300"
            >
              {busy ? "저장 중…" : "저장하고 경로에 반영"}
            </button>
          </div>
        </div>
      )}
    </Drawer>
  );
}
