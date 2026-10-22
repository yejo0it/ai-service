import { useEffect, useMemo, useRef, useState } from "react";
import { createTripFromReservations, getHotelDetails, searchHotels, toErrorMessage } from "../api/client";
import { SuggestInput, TextInput } from "../components/formFields";
import { searchCities, type CityOption } from "../onboarding/cities";
import type {
  Destination,
  FlightBooking,
  HotelBooking,
  HotelPlacePick,
  HotelSuggestion,
  ReservationResult,
  Trip,
} from "../types/api";
import { formatMonthDay } from "../utils/date";
import ReservationFlow from "./ReservationFlow";
import { guessHotelCity, segmentsOf, suggestDates, suggestDestinations } from "./tripPlan";

type Step = "flight" | "hotel" | "review";
const STEPS: { key: Step; label: string }[] = [
  { key: "flight", label: "항공권" },
  { key: "hotel", label: "숙소(선택)" },
  { key: "review", label: "최종 확인" },
];

interface ReservationTripWizardProps {
  onComplete: (trip: Trip) => void;
  /** 직접 등록으로 돌아가기 */
  onBack: () => void;
}

/** 숙소 위치 찾기: 기존 숙소 검색(Google Places 자동완성)을 사용자가 누를 때만 쓴다. 고르면 같은 세션으로 상세를 받는다. */
function HotelPlaceSearch({ name, city, onPick }: { name: string; city: string; onPick: (place: HotelPlacePick) => void }) {
  const [query, setQuery] = useState(name);
  const [items, setItems] = useState<HotelSuggestion[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const sessionToken = useRef(crypto.randomUUID());

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      setItems(await searchHotels({ input: query.trim(), sessionToken: sessionToken.current, city }));
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const pick = async (item: HotelSuggestion) => {
    setLoading(true);
    try {
      const detail = await getHotelDetails(item.place_id, sessionToken.current);
      onPick({ ...detail, address: detail.address || item.description });
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl bg-slate-50 p-3">
      <div className="flex gap-2">
        <TextInput
          compact
          aria-label="숙소 검색어"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              search();
            }
          }}
        />
        <button
          type="button"
          onClick={search}
          disabled={loading}
          className="shrink-0 rounded-xl bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-100 disabled:opacity-50"
        >
          검색
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
      {items.length > 0 && (
        <ul className="mt-2 space-y-1">
          {items.map((item) => (
            <li key={item.place_id}>
              <button
                type="button"
                onClick={() => pick(item)}
                className="w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-white"
              >
                <span className="block truncate font-medium text-slate-800">{item.name}</span>
                <span className="block truncate text-xs text-slate-500">{item.description}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * 예약 정보로 여행 만들기: 항공권(필수) → 숙소(선택) → 최종 확인 → 여행 만들기.
 * 1단계의 업로드·확인 화면(ReservationFlow)을 그대로 쓰고, 마지막에 여행 기간·여행지·숙소 위치를 확인한 뒤 한 번에 저장한다.
 * 관광 일정은 만들지 않고, 항공·숙소 카드는 여행 상세를 처음 열 때 예약 정보 그대로 만들어진다.
 */
export default function ReservationTripWizard({ onComplete, onBack }: ReservationTripWizardProps) {
  const [step, setStep] = useState<Step>("flight");
  const [flight, setFlight] = useState<ReservationResult | null>(null);
  const [hotels, setHotels] = useState<ReservationResult | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [unknownAirports, setUnknownAirports] = useState<string[]>([]);
  const [cityQuery, setCityQuery] = useState("");
  const [places, setPlaces] = useState<(HotelPlacePick | null)[]>([]);
  const [hotelCities, setHotelCities] = useState<string[]>([]);
  const [searching, setSearching] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // 같은 요청을 두 번 보내도 여행이 하나만 만들어지도록 화면을 여는 동안 같은 번호를 쓴다.
  const requestId = useRef(crypto.randomUUID());

  const flightDoc = flight?.document as FlightBooking | undefined;
  const hotelDoc = (hotels?.document as HotelBooking | undefined) ?? null;
  const stays = hotelDoc?.stays ?? [];
  const segments = useMemo(() => (flightDoc ? segmentsOf(flightDoc) : []), [flightDoc]);

  // 최종 확인에 들어갈 때 기본값을 정한다(이미 고친 값은 덮어쓰지 않는다).
  const prepared = useRef(false);
  useEffect(() => {
    if (step !== "review" || !flightDoc || prepared.current) return;
    prepared.current = true;
    const dates = suggestDates(flightDoc, hotelDoc);
    const suggestion = suggestDestinations(flightDoc);
    setStart(dates.start);
    setEnd(dates.end);
    setDestinations(suggestion.destinations);
    setUnknownAirports(suggestion.unknownAirports);
    setPlaces(stays.map(() => null));
    setHotelCities(stays.map((stay) => guessHotelCity(stay, suggestion.destinations)));
  }, [step, flightDoc, hotelDoc, stays]);

  const addCity = (city: CityOption) => {
    if (!destinations.some((item) => item.city_code === city.city_code)) {
      setDestinations([...destinations, { city: city.city, city_code: city.city_code }]);
    }
    setCityQuery("");
  };

  const problems = [
    !start || !end ? "여행 기간을 입력해 주세요." : end < start ? "종료일이 시작일보다 빨라요." : "",
    destinations.length === 0 ? "여행지를 한 곳 이상 추가해 주세요." : "",
  ].filter(Boolean);

  const create = async () => {
    if (!flightDoc || problems.length > 0 || saving) return;
    setSaving(true);
    setError("");
    try {
      const trip = await createTripFromReservations({
        request_id: requestId.current,
        flight: flightDoc,
        hotels: hotelDoc && hotelDoc.stays.length > 0 ? hotelDoc : null,
        start_date: start,
        end_date: end,
        destinations,
        hotel_places: places,
        hotel_cities: hotelCities,
      });
      onComplete(trip);
    } catch (err) {
      setError(toErrorMessage(err));
      setSaving(false);
    }
  };

  const index = STEPS.findIndex((item) => item.key === step);

  return (
    <div className="space-y-5">
      <ol className="flex items-center gap-2 text-xs" aria-label="진행 단계">
        {STEPS.map((item, position) => (
          <li
            key={item.key}
            aria-current={item.key === step ? "step" : undefined}
            className={`rounded-full px-2.5 py-1 font-semibold ${
              position === index ? "bg-indigo-600 text-white" : position < index ? "bg-indigo-50 text-indigo-600" : "bg-slate-100 text-slate-400"
            }`}
          >
            {position + 1}. {item.label}
          </li>
        ))}
      </ol>

      {step === "flight" && (
        <>
          <header>
            <h2 className="text-xl font-bold text-slate-900">항공권 예약 확인서를 올려 주세요</h2>
            <p className="mt-1 text-sm text-slate-500">왕복·경유·다구간 항공권도 구간별로 읽어 와요. 읽은 값은 확인하고 고칠 수 있어요.</p>
          </header>
          <ReservationFlow
            key="flight"
            fixedKind="flight"
            initial={flight}
            confirmLabel="항공권 확인하고 다음"
            onConfirmed={(result) => {
              setFlight(result);
              prepared.current = false;
              setStep("hotel");
            }}
          />
          <button type="button" onClick={onBack} className="text-sm font-medium text-slate-500 hover:text-slate-800">
            ← 직접 등록으로 만들기
          </button>
        </>
      )}

      {step === "hotel" && (
        <>
          <header>
            <h2 className="text-xl font-bold text-slate-900">숙소 예약 확인서가 있나요?</h2>
            <p className="mt-1 text-sm text-slate-500">없으면 건너뛰어도 돼요. 숙소는 여행 상세에서도 추가할 수 있어요.</p>
          </header>
          <ReservationFlow
            key="hotel"
            fixedKind="hotel"
            initial={hotels}
            confirmLabel="숙소 확인하고 다음"
            onConfirmed={(result) => {
              setHotels(result);
              prepared.current = false;
              setStep("review");
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <button type="button" onClick={() => setStep("flight")} className="text-sm font-medium text-slate-500 hover:text-slate-800">
              ← 항공권
            </button>
            <button
              type="button"
              onClick={() => {
                setHotels(null);
                prepared.current = false;
                setStep("review");
              }}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              숙소 없이 다음
            </button>
          </div>
        </>
      )}

      {step === "review" && (
        <div className="space-y-5">
          <header>
            <h2 className="text-xl font-bold text-slate-900">이대로 여행을 만들까요?</h2>
            <p className="mt-1 text-sm text-slate-500">예약 정보의 항공·숙소 일정은 그대로 경로에 들어가고, 관광 일정은 만들지 않아요.</p>
          </header>

          <section aria-label="여행 기간" className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-semibold text-slate-500">
              시작일
              <TextInput compact type="date" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1.5" />
            </label>
            <label className="block text-xs font-semibold text-slate-500">
              종료일
              <TextInput compact type="date" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1.5" />
            </label>
          </section>

          <section aria-label="여행지">
            <span className="mb-1.5 block text-xs font-semibold text-slate-500">여행지 (방문 순서)</span>
            <div className="flex flex-wrap gap-1.5">
              {destinations.map((item, position) => (
                <span key={item.city_code} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-1 text-sm font-medium text-indigo-700">
                  {position + 1}. {item.city}
                  <button
                    type="button"
                    onClick={() => setDestinations(destinations.filter((other) => other.city_code !== item.city_code))}
                    aria-label={`${item.city} 빼기`}
                    className="ml-0.5 text-indigo-400 hover:text-indigo-700"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="mt-2">
              <SuggestInput<CityOption>
                id="reservation-city"
                compact
                value={cityQuery}
                onChange={setCityQuery}
                search={searchCities}
                keyOf={(item) => item.city_code}
                renderLabel={(item) => item.city}
                renderHint={(item) => item.region}
                onPick={addCity}
                placeholder="여행지 추가 (도시 이름)"
              />
            </div>
            {unknownAirports.length > 0 && (
              <p className="mt-1.5 text-xs text-amber-600">
                PinRoute 목록에 없는 공항({unknownAirports.join(", ")})은 여행지로 넣지 않았어요. 필요하면 직접 추가해 주세요.
              </p>
            )}
          </section>

          <section aria-label="항공편" className="space-y-1.5">
            <span className="block text-xs font-semibold text-slate-500">항공편 {segments.length}개 구간</span>
            {segments.map((segment, position) => (
              <p key={position} className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
                <span className="font-semibold">{segment.flight_number}</span> {segment.departure_airport_code} →{" "}
                {segment.arrival_airport_code} · {segment.departure_date && formatMonthDay(segment.departure_date)} {segment.departure_time}
              </p>
            ))}
            <button type="button" onClick={() => setStep("flight")} className="text-xs font-medium text-indigo-600 hover:underline">
              항공권 고치기
            </button>
          </section>

          {stays.length > 0 && (
            <section aria-label="숙소" className="space-y-3">
              <span className="block text-xs font-semibold text-slate-500">숙소 {stays.length}곳</span>
              {stays.map((stay, position) => (
                <div key={position} className="rounded-xl border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-800">{stay.name}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {stay.check_in_date && formatMonthDay(stay.check_in_date)}
                    {stay.check_in_time ? ` ${stay.check_in_time}` : ""} ~ {stay.check_out_date && formatMonthDay(stay.check_out_date)}
                    {stay.check_out_time ? ` ${stay.check_out_time}` : ""}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <label className="text-xs text-slate-500">
                      여행지{" "}
                      <select
                        value={hotelCities[position] ?? ""}
                        onChange={(event) => setHotelCities(hotelCities.map((value, i) => (i === position ? event.target.value : value)))}
                        className="ml-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700"
                      >
                        <option value="">선택 안 함</option>
                        {destinations.map((item) => (
                          <option key={item.city_code} value={item.city_code}>
                            {item.city}
                          </option>
                        ))}
                      </select>
                    </label>
                    {places[position] ? (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
                        <i className="fas fa-map-marker-alt" aria-hidden="true" /> 위치 연결됨 · {places[position]?.address}
                        <button
                          type="button"
                          onClick={() => setPlaces(places.map((value, i) => (i === position ? null : value)))}
                          className="ml-1 text-slate-400 hover:text-rose-500"
                        >
                          해제
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setSearching(searching === position ? null : position)}
                        className="text-xs font-medium text-indigo-600 hover:underline"
                      >
                        지도 위치 찾기(선택)
                      </button>
                    )}
                  </div>
                  {searching === position && !places[position] && (
                    <HotelPlaceSearch
                      name={stay.name ?? ""}
                      city={destinations.find((item) => item.city_code === hotelCities[position])?.city ?? ""}
                      onPick={(place) => {
                        setPlaces(places.map((value, i) => (i === position ? place : value)));
                        setSearching(null);
                      }}
                    />
                  )}
                </div>
              ))}
            </section>
          )}

          {(problems.length > 0 || error) && (
            <div role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">
              {[...problems, error].filter(Boolean).map((message) => (
                <p key={message}>{message}</p>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setStep("hotel")}
              disabled={saving}
              className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              이전
            </button>
            <button
              type="button"
              onClick={create}
              disabled={saving || problems.length > 0}
              className="flex-1 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
            >
              {saving ? "만드는 중…" : "여행 만들기"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
