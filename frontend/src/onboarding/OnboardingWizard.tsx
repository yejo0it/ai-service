import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import DatePicker, { type ReactDatePickerCustomHeaderProps } from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { createTrip, getHotelDetails, searchHotels, toErrorMessage } from "../api/client";
import type { Airport, HotelSuggestion, Trip, TripPayload } from "../types/api";
import type {
  AirlineSelection,
  AirportDraft,
  DateMode,
  DestinationDraft,
  HotelDraft,
  HotelErrors,
  OnboardingContextValue,
  OnboardingData,
  OnboardingErrors,
  OnboardingPatch,
  Stay,
  TripRange,
} from "../types/onboarding";
import { findCityByName, searchCities, type CityOption } from "./cities";
import { findAirlineByName, searchAirlines, type AirlineOption } from "./airlines";
import { findAirportByName, searchAirports, type AirportOption } from "./airports";

/* ------------------------------------------------------------------ *
 * 온보딩 상태 (Step 1~3 입력값 누적)
 * ------------------------------------------------------------------ */

const TOTAL_STEPS = 3;

/**
 * Step 1의 여행지 한 줄. 도시 이동 순서대로 배열에 쌓인다.
 * id는 행 삭제 시 React key가 밀리지 않게 하기 위한 값으로, 전송 payload에는 포함되지 않는다.
 */
let destinationSeq = 0;
const emptyDestination = (): DestinationDraft => ({
  id: `destination-${(destinationSeq += 1)}`,
  city: "",
  city_code: "",
});

/**
 * Step 3의 숙소 한 칸. sessionToken은 Google Places 자동완성 세션 단위로 쓰는 UUID이며,
 * 숙소를 고르면(Details 호출로 세션 종료) 새 토큰으로 바꾼다. id·sessionToken은 전송하지 않는다.
 */
let hotelSeq = 0;

interface EmptyHotelOptions {
  city?: string;
  checkIn?: string;
  checkOut?: string;
}

const emptyHotel = ({ city = "", checkIn = "", checkOut = "" }: EmptyHotelOptions = {}): HotelDraft => ({
  id: `hotel-${(hotelSeq += 1)}`,
  sessionToken: crypto.randomUUID(),
  city, // 검색 범위로 쓰는 여행지(Step 1의 도시명)
  name: "",
  place_id: "",
  address: "",
  latitude: null,
  longitude: null,
  city_code: "",
  check_in: checkIn,
  check_out: checkOut,
});

const EMPTY_AIRPORT: AirportDraft = { text: "", airport: null };

const INITIAL_DATA: OnboardingData = {
  // Step 1
  destinations: [emptyDestination()],
  // Step 2
  dateMode: "flight",
  airline: "",
  airlineCode: "", // 선택한 항공사의 IATA 코드. 편명 앞에 붙는다.
  flightNumber: "",
  departureAirport: EMPTY_AIRPORT,
  arrivalAirport: EMPTY_AIRPORT,
  departureAt: "",
  sameReturnAirline: true, // 귀국 항공사 동일
  returnAirline: "",
  returnAirlineCode: "",
  returnFlightNumber: "",
  returnDepartureAirport: EMPTY_AIRPORT,
  returnArrivalAirport: EMPTY_AIRPORT,
  returnArrivalAt: "",
  startDate: "",
  endDate: "",
  // Step 3
  skipHotel: false,
  hotels: [emptyHotel()],
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function useOnboarding(): OnboardingContextValue {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error("useOnboarding은 <OnboardingWizard> 안에서만 사용할 수 있습니다.");
  }
  return context;
}

/** datetime-local("2026-09-01T10:30") -> "2026-09-01" */
const toDate = (value: string) => (value ? value.slice(0, 10) : "");

/** '귀국 항공사 동일'이 켜져 있으면 출국 항공사를 그대로 쓴다. */
export function returnAirlineOf(data: OnboardingData): AirlineSelection {
  return data.sameReturnAirline
    ? { name: data.airline.trim(), code: data.airlineCode }
    : { name: data.returnAirline.trim(), code: data.returnAirlineCode };
}

/** 목록에서 고른 공항만 보낸다. */
const airportPayload = ({ airport }: AirportDraft): Airport | null =>
  airport ? { code: airport.code, name: airport.name } : null;

/** 누적된 상태를 DRF payload로 변환 */
export function buildTripPayload(data: OnboardingData): TripPayload {
  const usesFlight = data.dateMode === "flight";
  const payload: TripPayload = {
    // 빈 줄은 제외하고 [{city, city_code}] 형태로 보낸다.
    destinations: data.destinations
      .map(({ city, city_code }) => ({
        city: city.trim(),
        city_code: (city_code || "").trim(),
      }))
      .filter((dest) => dest.city),
    start_date: usesFlight ? toDate(data.departureAt) : data.startDate,
    end_date: usesFlight ? toDate(data.returnArrivalAt) : data.endDate,
    date_source: usesFlight ? "flight" : "manual",
    flight_info: usesFlight
      ? {
          airline: data.airline.trim(),
          // IATA 코드와 번호를 합쳐 "KE001" 형태로 보낸다.
          flight_number: data.airlineCode + data.flightNumber.trim(),
          departure_at: data.departureAt,
          departure_airport: airportPayload(data.departureAirport),
          arrival_airport: airportPayload(data.arrivalAirport),
          return_departure_airport: airportPayload(data.returnDepartureAirport),
          return_arrival_airport: airportPayload(data.returnArrivalAirport),
          return_airline: returnAirlineOf(data).name,
          return_flight_number:
            returnAirlineOf(data).code + data.returnFlightNumber.trim(),
          return_arrival_at: data.returnArrivalAt,
        }
      : null,
    hotels: [],
  };

  if (!data.skipHotel) {
    // 목록에서 고른 숙소만 보낸다. 주소·좌표는 선택 시 Places Details로 채워진 값이다.
    payload.hotels = data.hotels
      .filter((hotel) => hotel.place_id)
      .map((hotel) => ({
        name: hotel.name.trim(),
        address: hotel.address,
        place_id: hotel.place_id,
        latitude: hotel.latitude,
        longitude: hotel.longitude,
        city_code: hotel.city_code,
        check_in: hotel.check_in,
        check_out: hotel.check_out || null,
      }));
  }
  return payload;
}

/** 숙소명을 입력하지 않은 칸. 숙소는 선택 사항이라 빈 칸은 검증·전송하지 않는다. */
const isBlankHotel = (hotel: HotelDraft) => !hotel.place_id && !hotel.name.trim();

/** 숙소별 에러를 { [hotel.id]: { name, stay } } 형태로 모은다. */
function validateHotels(allHotels: HotelDraft[]): Record<string, HotelErrors> {
  const errors: Record<string, HotelErrors> = {};
  const add = (id: string, key: keyof HotelErrors, message: string) => {
    errors[id] = { ...errors[id], [key]: errors[id]?.[key] ?? message };
  };

  const hotels = allHotels.filter((hotel) => !isBlankHotel(hotel));
  hotels.forEach((hotel) => {
    if (!hotel.place_id) add(hotel.id, "name", "검색 목록에서 숙소를 선택해 주세요.");
    if (!hotel.check_in || !hotel.check_out) {
      add(hotel.id, "stay", "숙박 기간을 선택해 주세요.");
    } else if (hotel.check_out <= hotel.check_in) {
      add(hotel.id, "stay", "최소 1박 이상 선택해 주세요.");
    }
  });

  // 체크인 순으로 늘어놓고 앞 숙소의 체크아웃이 다음 숙소 체크인보다 늦으면 겹친 것이다.
  // (체크아웃 날 다른 숙소로 체크인하는 것은 허용)
  const dated = hotels
    .filter((hotel) => hotel.check_in && hotel.check_out)
    .sort((a, b) => a.check_in.localeCompare(b.check_in));
  dated.slice(1).forEach((hotel, index) => {
    if (dated[index].check_out > hotel.check_in) {
      add(hotel.id, "stay", "다른 숙소의 숙박 기간과 겹쳐요.");
    }
  });
  return errors;
}

/** 각 단계의 진행 가능 여부 */
function validateStep(step: number, data: OnboardingData): OnboardingErrors {
  const errors: OnboardingErrors = {};
  if (step === 1) {
    if (!data.destinations.some((dest) => dest.city.trim())) {
      errors.destinations = "목적지를 입력해 주세요.";
    } else if (data.destinations.some((dest) => dest.city.trim() && !dest.city_code)) {
      errors.destinations = "여행지는 검색 목록에서 선택해 주세요.";
    }
  }
  if (step === 2) {
    if (data.dateMode === "flight") {
      if (!data.airline.trim()) errors.airline = "항공사를 선택해 주세요.";
      if (!data.flightNumber.trim()) errors.flightNumber = "편명을 입력해 주세요.";
      if (!data.sameReturnAirline && !data.returnAirline.trim()) {
        errors.returnAirline = "귀국 항공사를 선택해 주세요.";
      }
      // 공항은 선택 사항이지만, 입력했다면 목록에서 고른 공항이어야 한다.
      const airportFields = [
        "departureAirport",
        "arrivalAirport",
        "returnDepartureAirport",
        "returnArrivalAirport",
      ] as const;
      airportFields.forEach((field) => {
        if (data[field].text.trim() && !data[field].airport) {
          errors[field] = "공항은 검색 목록에서 선택해 주세요.";
        }
      });
      if (!data.departureAt) errors.departureAt = "출국 일시를 선택해 주세요.";
      if (!data.returnArrivalAt) errors.returnArrivalAt = "귀국 일시를 선택해 주세요.";
      if (
        data.departureAt &&
        data.returnArrivalAt &&
        data.returnArrivalAt < data.departureAt
      ) {
        errors.returnArrivalAt = "귀국은 출국 이후여야 합니다.";
      }
    } else {
      if (!data.startDate) errors.startDate = "시작일을 선택해 주세요.";
      if (!data.endDate) errors.endDate = "종료일을 선택해 주세요.";
      if (data.startDate && data.endDate && data.endDate < data.startDate) {
        errors.endDate = "종료일은 시작일 이후여야 합니다.";
      }
    }
  }
  if (step === 3 && !data.skipHotel) {
    const hotelErrors = validateHotels(data.hotels);
    if (Object.keys(hotelErrors).length > 0) errors.hotels = hotelErrors;
  }
  return errors;
}

/* ------------------------------------------------------------------ *
 * 공용 UI 조각
 * ------------------------------------------------------------------ */

function ProgressBar({ step }: { step: number }) {
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-slate-700">여행 만들기</span>
        <span className="text-xs font-medium tabular-nums text-slate-500">
          {step}/{TOTAL_STEPS}
        </span>
      </div>
      <div
        className="flex gap-1.5"
        role="progressbar"
        aria-valuenow={step}
        aria-valuemin={1}
        aria-valuemax={TOTAL_STEPS}
      >
        {Array.from({ length: TOTAL_STEPS }, (_, index) => (
          <span
            key={index}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${
              index < step ? "bg-indigo-600" : "bg-slate-200"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

interface FieldProps {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}

function Field({ label, error, hint, children }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-rose-600">{error}</span>}
    </label>
  );
}

const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 " +
  "placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 " +
  "focus:ring-indigo-100 disabled:bg-slate-50";

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & { error?: string };

function TextInput({ error, ...props }: TextInputProps) {
  const errorClass = error
    ? "border-rose-400 focus:border-rose-500 focus:ring-rose-100"
    : "";
  return <input {...props} className={`${INPUT_CLASS} ${errorClass}`} />;
}

/**
 * 입력하면 후보 목록을 드롭다운으로 보여주는 자동완성 입력.
 * 목록에 없는 값도 그대로 입력할 수 있고, 포커스만으로는 목록이 열리지 않는다.
 * 목록 선택만 허용하려면 onBlur에서 확정되지 않은 값을 정리한다.
 * `search`는 모듈 상수 함수를 넘겨야 useMemo가 유효하다.
 */
type SuggestInputProps<T> = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "value" | "onChange" | "onBlur"
> & {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onPick: (item: T) => void;
  /** 입력어로 후보를 찾는 동기 검색 (모듈 상수 함수) */
  search?: (query: string) => T[];
  /** 비동기 검색 결과. 넘기면 search 대신 그대로 후보로 쓴다. */
  items?: T[];
  keyOf: (item: T) => string;
  renderLabel: (item: T) => ReactNode;
  renderHint: (item: T) => ReactNode;
  error?: string;
  onBlur?: () => void;
};

function SuggestInput<T>({
  id,
  value,
  onChange,
  onPick,
  search,
  items,
  keyOf,
  renderLabel,
  renderHint,
  error,
  onBlur,
  ...inputProps
}: SuggestInputProps<T>) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  // items를 넘기면(비동기 검색 결과) search 대신 그대로 후보로 쓴다.
  const suggestions = useMemo(() => items ?? search?.(value) ?? [], [items, search, value]);
  const listId = `${id}-listbox`;

  const pick = (item: T) => {
    onPick(item);
    setOpen(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (suggestions.length === 0) return;
    if (!open) {
      // 포커스만으로는 열지 않으므로, ↓ 키로 명시적으로 열 수 있게 해준다.
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlight(0);
        setOpen(true);
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => (current - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter") {
      // 폼 제출(다음 단계)보다 목록 선택이 우선이다.
      event.preventDefault();
      pick(suggestions[Math.min(highlight, suggestions.length - 1)]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <TextInput
        {...inputProps}
        value={value}
        error={error}
        onChange={(event) => {
          onChange(event.target.value);
          setHighlight(0);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          setOpen(false);
          onBlur?.();
        }}
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
      />

      {open && suggestions.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
        >
          {suggestions.map((item, position) => (
            <li key={keyOf(item)} role="option" aria-selected={position === highlight}>
              <button
                type="button"
                // onBlur보다 먼저 실행되어 목록이 닫히는 것을 막는다.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(item)}
                onMouseEnter={() => setHighlight(position)}
                className={`flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-sm transition-colors ${
                  position === highlight ? "bg-indigo-50 text-indigo-700" : "text-slate-700"
                }`}
              >
                {/* 줄 수는 renderLabel이 정한다(항공사는 국문/영문 2줄). */}
                <span className="min-w-0 flex-1">{renderLabel(item)}</span>
                <span className="shrink-0 text-xs tabular-nums text-slate-400">
                  {renderHint(item)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Step 1 — 목적지
 * ------------------------------------------------------------------ */

const cityKey = (city: CityOption) => city.city_code;
const cityHint = (city: CityOption) => city.city_code;
const cityLabel = (city: CityOption) => <span className="block truncate">{city.city}</span>;

/** 타임라인 노드. 입력된 행은 채워진 핀, 빈 행은 흐린 핀으로 표시한다. */
function TimelineNode({ filled }: { filled: boolean }) {
  return (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] transition-colors ${
        filled
          ? "border-indigo-500 bg-indigo-500 text-white"
          : "border-indigo-200 bg-white text-indigo-300"
      }`}
    >
      <i className="fas fa-map-pin" aria-hidden="true" />
    </span>
  );
}

interface DestinationRowProps {
  dest: DestinationDraft;
  index: number;
  total: number;
  error?: string;
  onChange: (patch: Partial<DestinationDraft>) => void;
  onBlur: () => void;
  onRemove: () => void;
}

function DestinationRow({ dest, index, total, error, onChange, onBlur, onRemove }: DestinationRowProps) {
  const isFirst = index === 0;
  const isLast = index === total - 1;

  return (
    <div className="flex gap-2">
      {/* 첫 행 위/마지막 행 아래로는 선이 뻗지 않는다. */}
      <div className="flex w-6 shrink-0 flex-col items-center" aria-hidden="true">
        <span className={`w-px flex-1 ${isFirst ? "bg-transparent" : "bg-indigo-200"}`} />
        <TimelineNode filled={Boolean(dest.city.trim())} />
        <span className={`w-px flex-1 ${isLast ? "bg-transparent" : "bg-indigo-200"}`} />
      </div>

      <div className="flex flex-1 items-center gap-2 py-1">
        <div className="flex-1">
          <SuggestInput
            id={dest.id}
            value={dest.city}
            error={error}
            search={searchCities}
            keyOf={cityKey}
            renderLabel={cityLabel}
            renderHint={cityHint}
            // 입력 중인 값은 확정되지 않은 상태(city_code 없음)이고, 목록에서 골라야 확정된다.
            onChange={(value) => onChange({ city: value, city_code: "" })}
            onPick={(city) => onChange({ city: city.city, city_code: city.city_code })}
            onBlur={onBlur}
            placeholder="도시"
            autoFocus={isFirst}
            aria-label={`여행지 ${index + 1}`}
          />
        </div>

        {total > 1 && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`여행지 ${index + 1} 삭제`}
            title="삭제"
            className="shrink-0 rounded-xl border border-slate-200 px-3 py-3 text-slate-400 transition-colors hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600"
          >
            <i className="fas fa-trash" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}

function StepDestination() {
  const { data, update, errors } = useOnboarding();
  const destinations = data.destinations;

  const setDestination = (index: number, patch: Partial<DestinationDraft>) =>
    update({
      destinations: destinations.map((dest, position) =>
        position === index ? { ...dest, ...patch } : dest,
      ),
    });

  const addDestination = () =>
    update({ destinations: [...destinations, emptyDestination()] });

  const removeDestination = (index: number) =>
    update({
      destinations: destinations.filter((_, position) => position !== index),
    });

  // 목록에서 고르지 않고 포커스를 떠나면, 도시명이 정확히 일치할 때만 그 도시로 확정하고
  // 아니면 입력을 비우고 안내한다.
  const [rejectedCity, setRejectedCity] = useState("");
  const confirmDestination = (index: number) => {
    const dest = destinations[index];
    const typed = dest.city.trim();
    if (dest.city_code || !typed) return;
    const city = findCityByName(typed);
    setDestination(index, city ?? { city: "", city_code: "" });
    setRejectedCity(city ? "" : typed);
  };
  const destinationError = rejectedCity
    ? `'${rejectedCity}'은(는) 목록에 없는 여행지예요. 목록에서 선택해 주세요.`
    : errors.destinations;

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-slate-900">어디로 떠나시나요?</h2>
        <p className="mt-1 text-sm text-slate-500">
          여러 도시를 이동한다면 순서대로 추가해 주세요.
        </p>
      </header>

      <div>
        <span className="mb-1.5 block text-sm font-medium text-slate-700">여행지</span>
        {/* 도시 이동 순서를 왼쪽 세로 타임라인으로 표현한다.
            행 사이 여백을 안쪽 래퍼(py-1)에 두어 레일의 선이 끊기지 않게 한다. */}
        <div>
          {destinations.map((dest, index) => (
            <DestinationRow
              key={dest.id}
              dest={dest}
              index={index}
              total={destinations.length}
              error={destinationError}
              onChange={(patch) => {
                setDestination(index, patch);
                setRejectedCity("");
              }}
              onBlur={() => confirmDestination(index)}
              onRemove={() => removeDestination(index)}
            />
          ))}
        </div>
        {destinationError && (
          // 타임라인 레일(w-6) + gap(2) 만큼 들여써 입력칸과 좌측을 맞춘다.
          <span className="mt-1 block pl-8 text-xs text-rose-600">
            {destinationError}
          </span>
        )}
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={addDestination}
            className="rounded-xl border border-dashed border-indigo-300 px-3.5 py-2 text-sm font-medium text-indigo-600 transition-colors hover:border-indigo-500 hover:bg-indigo-50"
          >
            + 여행지 추가
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Step 2 — 항공권 / 날짜만 등록
 * ------------------------------------------------------------------ */

const DATE_MODES: { key: DateMode; label: string }[] = [
  { key: "flight", label: "항공권 등록" },
  { key: "dates", label: "날짜만 등록" },
];

const pad2 = (value: number) => String(value).padStart(2, "0");

/** Date -> "2026-10-01" */
const toISODate = (date: Date | null) =>
  date ? `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` : "";

/** "2026-10-01" -> Date (타임존 밀림을 피하려고 로컬 자정으로 만든다) */
const fromISODate = (value: string | undefined): Date | null =>
  value ? new Date(`${value}T00:00:00`) : null;

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-10-01" -> "2026년 10월 1일 (목)" */
const formatKoreanDate = (value: string) => {
  const date = fromISODate(value);
  if (!date) return "";
  return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 (${
    WEEKDAYS[date.getDay()]
  })`;
};

const HOURS = Array.from({ length: 24 }, (_, index) => pad2(index));
const MINUTES = Array.from({ length: 12 }, (_, index) => pad2(index * 5));

/** 팝오버 바깥을 누르면 닫는다. */
function useOutsideClose(ref: RefObject<HTMLElement>, onClose: () => void) {
  useEffect(() => {
    const handle = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [ref, onClose]);
}

/** 달력/시간 팝오버를 여는 버튼. 좌측 아이콘 + 값 + 우측 쉐브론. */
interface PickerButtonProps {
  /** Font Awesome 클래스 (예: "far fa-calendar") */
  icon: string;
  /** 선택된 값 표기. 비어 있으면 placeholder를 보여준다. */
  children: ReactNode;
  placeholder: string;
  open: boolean;
  invalid?: boolean;
  onClick: () => void;
  ariaLabel: string;
}

function PickerButton({
  icon,
  children,
  placeholder,
  open,
  invalid,
  onClick,
  ariaLabel,
}: PickerButtonProps) {
  const filled = Boolean(children);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-expanded={open}
      className={`flex w-full items-center gap-2 rounded-xl border bg-white px-3 py-3 text-left text-base transition-colors ${
        invalid
          ? "border-rose-400"
          : open
            ? "border-indigo-500 ring-2 ring-indigo-100"
            : "border-slate-200 hover:border-slate-300"
      }`}
    >
      <i className={`${icon} shrink-0 text-slate-400`} aria-hidden="true" />
      <span className={`flex-1 truncate ${filled ? "text-slate-900" : "text-slate-400"}`}>
        {filled ? children : placeholder}
      </span>
      <i
        className={`fas fa-chevron-down shrink-0 text-xs text-slate-400 transition-transform ${
          open ? "rotate-180" : ""
        }`}
        aria-hidden="true"
      />
    </button>
  );
}

const POPOVER_CLASS =
  "pin-calendar absolute left-0 z-30 mt-1.5 rounded-2xl border border-slate-100 bg-white p-3 shadow-xl";

// react-datepicker 기본 로케일이 영문이라, 요일만 한글로 바꿔 표기한다.
// (date-fns ko 로케일은 직접 의존하지 않는 패키지라 끌어다 쓰지 않는다)
const WEEKDAY_KO: Record<string, string> = {
  Sunday: "일",
  Monday: "월",
  Tuesday: "화",
  Wednesday: "수",
  Thursday: "목",
  Friday: "금",
  Saturday: "토",
};
const formatWeekDay = (name: string) => WEEKDAY_KO[name] ?? name.slice(0, 1);

/** 달력 상단의 ‹ 2026년 10월 › 헤더. */
function CalendarHeader({ date, decreaseMonth, increaseMonth }: ReactDatePickerCustomHeaderProps) {
  const navClass =
    "flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 disabled:hover:bg-transparent";
  return (
    <div className="mb-1 flex items-center justify-between px-1">
      <button
        type="button"
        onClick={decreaseMonth}
        aria-label="이전 달"
        className={navClass}
      >
        <i className="fas fa-chevron-left text-xs" aria-hidden="true" />
      </button>
      <span className="text-sm font-semibold text-slate-800">
        {date.getFullYear()}년 {date.getMonth() + 1}월
      </span>
      <button
        type="button"
        onClick={increaseMonth}
        aria-label="다음 달"
        className={navClass}
      >
        <i className="fas fa-chevron-right text-xs" aria-hidden="true" />
      </button>
    </div>
  );
}

/** 열릴 때 선택된 항목이 목록 가운데로 오도록 스크롤한다(페이지는 움직이지 않게 직접 계산). */
function useScrollToSelected(
  listRef: RefObject<HTMLDivElement>,
  itemRef: RefObject<HTMLButtonElement>,
  hasSelection: boolean,
) {
  // 열릴 때, 그리고 날짜를 골라 기본 시각이 처음 채워질 때 스크롤한다(누를 때마다 목록이 튀지 않게).
  useEffect(() => {
    const list = listRef.current;
    const item = itemRef.current;
    if (!list || !item) return;
    list.scrollTop = item.offsetTop - list.clientHeight / 2 + item.clientHeight / 2;
  }, [listRef, itemRef, hasSelection]);
}

/** 시·분을 각각 세로로 스크롤해 고르는 목록. */
interface TimeColumnsProps {
  /** "00"~"23", 아직 고르지 않았으면 빈 문자열 */
  hour: string;
  /** "00"~"55"(5분 단위), 아직 고르지 않았으면 빈 문자열 */
  minute: string;
  /** part는 이번에 누른 목록(시 또는 분) */
  onPick: (hour: string, minute: string, part: "hour" | "minute") => void;
}

function TimeColumns({ hour, minute, onPick }: TimeColumnsProps) {
  const hourList = useRef<HTMLDivElement>(null);
  const hourItem = useRef<HTMLButtonElement>(null);
  const minuteList = useRef<HTMLDivElement>(null);
  const minuteItem = useRef<HTMLButtonElement>(null);
  useScrollToSelected(hourList, hourItem, Boolean(hour));
  useScrollToSelected(minuteList, minuteItem, Boolean(minute));

  const cell = (
    value: string,
    active: boolean,
    onClick: () => void,
    ref: RefObject<HTMLButtonElement>,
  ) => (
    <button
      key={value}
      ref={active ? ref : undefined}
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg px-4 py-1.5 text-center text-sm tabular-nums transition-colors ${
        active ? "bg-indigo-200 font-semibold text-indigo-800" : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {value}
    </button>
  );

  return (
    <div className="flex gap-1">
      <div ref={hourList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
        {HOURS.map((item) =>
          cell(item, item === hour, () => onPick(item, minute || "00", "hour"), hourItem),
        )}
      </div>
      <div className="w-px bg-slate-100" />
      <div ref={minuteList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
        {MINUTES.map((item) =>
          cell(item, item === minute, () => onPick(hour || "09", item, "minute"), minuteItem),
        )}
      </div>
    </div>
  );
}

/**
 * 출국·귀국 일시. '날짜만 등록'·'숙박 기간'과 같은 버튼 + 달력 팝오버이고, 팝오버 안에서 시·분까지 고른다.
 * 날짜를 고르면 열어 둔 채 시각을 고르게 하고(기본 09:00), 분까지 고르면 닫는다. 값은 "YYYY-MM-DDTHH:mm".
 */
interface DateTimeFieldProps {
  /** "YYYY-MM-DDTHH:mm", 비어 있으면 빈 문자열 */
  value: string;
  onChange: (value: string) => void;
  /** 고를 수 있는 가장 이른 날짜 "YYYY-MM-DD" (없으면 오늘) */
  minDate?: string;
  error?: string;
  ariaLabel: string;
}

function DateTimeField({ value, onChange, minDate, error, ariaLabel }: DateTimeFieldProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useOutsideClose(wrapperRef, close);

  const datePart = value ? value.slice(0, 10) : "";
  const [hour = "", minute = ""] = value ? value.slice(11, 16).split(":") : [];

  const pickDate = (date: Date | null) => {
    const iso = toISODate(date);
    onChange(iso ? `${iso}T${hour || "09"}:${minute || "00"}` : "");
  };

  const pickTime = (nextHour: string, nextMinute: string, part: "hour" | "minute") => {
    if (!datePart) return;
    onChange(`${datePart}T${nextHour}:${nextMinute}`);
    if (part === "minute") setOpen(false);
  };

  return (
    <div ref={wrapperRef} className="relative">
      <PickerButton
        icon="far fa-calendar"
        open={open}
        invalid={Boolean(error)}
        placeholder="날짜와 시각을 선택하세요"
        ariaLabel={ariaLabel}
        onClick={() => setOpen((previous) => !previous)}
      >
        {datePart ? `${formatKoreanDate(datePart)} ${hour}:${minute}` : ""}
      </PickerButton>

      {open && (
        // Field가 <label>이라 날짜 클릭이 PickerButton으로 전달돼 달력이 닫히는 것을 막는다.
        <div className={POPOVER_CLASS} onClick={(event) => event.preventDefault()}>
          <div className="flex flex-col gap-3 sm:flex-row">
            <DatePicker
              inline
              selected={fromISODate(datePart)}
              minDate={fromISODate(minDate) ?? new Date()}
              onChange={pickDate}
              renderCustomHeader={CalendarHeader}
              formatWeekDay={formatWeekDay}
            />
            <div
              className={`border-t border-slate-100 pt-3 sm:border-l sm:border-t-0 sm:pl-3 sm:pt-0 ${
                datePart ? "" : "pointer-events-none opacity-40"
              }`}
            >
              <div className="mb-1 flex gap-1 px-1 text-center text-[11px] font-medium text-slate-400">
                <span className="w-16">시</span>
                <span className="w-px" />
                <span className="w-16">분</span>
              </div>
              <TimeColumns hour={hour} minute={minute} onPick={pickTime} />
            </div>
          </div>
          {!datePart && (
            <p className="mt-2 text-center text-xs text-slate-400">날짜를 먼저 고르면 시각을 고를 수 있어요.</p>
          )}
        </div>
      )}
    </div>
  );
}

/* 공항: 목록에서 고른 공항만 확정한다(직접 입력 불가). */

const airportKey = (item: AirportOption) => item.id;
const airportHint = (item: AirportOption) => item.code;
const airportLabel = (item: AirportOption) => (
  <span className="block">
    <span className="block truncate">{item.name}</span>
    <span className="block truncate text-xs text-slate-400">{item.city}</span>
  </span>
);

interface AirportInputProps {
  id: string;
  label: string;
  /** 가는 편·오는 편 칸을 구분하는 스크린 리더용 이름 */
  ariaLabel: string;
  value: AirportDraft;
  error?: string;
  onChange: (value: AirportDraft) => void;
}

/**
 * 공항 검색 자동완성. 목록에서 골라야 확정되고, 고르지 않고 포커스를 떠나면
 * 공항명이 정확히 일치할 때만 확정하고 아니면 입력을 비우고 안내한다.
 */
function AirportInput({ id, label, ariaLabel, value, error, onChange }: AirportInputProps) {
  const [rejected, setRejected] = useState("");

  const confirm = () => {
    const typed = value.text.trim();
    if (value.airport || !typed) return;
    const found = findAirportByName(typed);
    onChange(found ? { text: found.name, airport: found } : EMPTY_AIRPORT);
    setRejected(found ? "" : typed);
  };

  const message = rejected ? `'${rejected}'은(는) 목록에 없는 공항이에요.` : error;
  return (
    <Field label={label} error={message}>
      <SuggestInput
        id={id}
        value={value.text}
        error={message}
        search={searchAirports}
        keyOf={airportKey}
        renderLabel={airportLabel}
        renderHint={airportHint}
        onChange={(text) => {
          onChange({ text, airport: null });
          setRejected("");
        }}
        onPick={(item) => {
          onChange({ text: item.name, airport: item });
          setRejected("");
        }}
        onBlur={confirm}
        placeholder="예) 인천"
        aria-label={ariaLabel}
      />
    </Field>
  );
}

const airlineKey = (airline: AirlineOption) => airline.code;
const airlineHint = (airline: AirlineOption) => airline.code;

// 항공사 칸이 절반 너비라 국문/영문을 두 줄로 나눠 잘리지 않게 한다.
const airlineLabel = (airline: AirlineOption) => (
  <span className="block">
    <span className="block truncate">{airline.name}</span>
    {airline.name_en && (
      <span className="block truncate text-xs text-slate-400">{airline.name_en}</span>
    )}
  </span>
);

/** 항공사 자동완성 + IATA 코드가 앞에 붙는 편명 입력 한 쌍. */
interface AirlineFlightFieldsProps {
  id: string;
  airlineLabelText: string;
  flightLabelText: string;
  airline: string;
  airlineCode: string;
  /** IATA 코드를 뺀 편명 숫자 */
  flightNumber: string;
  /** '귀국 항공사 동일'이면 항공사 칸을 읽기 전용으로 둔다. */
  disabled?: boolean;
  airlineError?: string;
  flightError?: string;
  onAirlineChange: (airline: AirlineSelection) => void;
  onFlightNumberChange: (value: string) => void;
}

function AirlineFlightFields({
  id,
  airlineLabelText,
  flightLabelText,
  airline,
  airlineCode,
  flightNumber,
  disabled = false,
  airlineError,
  flightError,
  onAirlineChange,
  onFlightNumberChange,
}: AirlineFlightFieldsProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label={airlineLabelText} error={airlineError}>
        {disabled ? (
          // '귀국 항공사 동일'이면 출국 값이 그대로 채워진 읽기 전용 입력.
          <TextInput value={airline} disabled readOnly aria-label={airlineLabelText} />
        ) : (
          <SuggestInput
            id={id}
            value={airline}
            error={airlineError}
            search={searchAirlines}
            keyOf={airlineKey}
            renderLabel={airlineLabel}
            renderHint={airlineHint}
            // 목록에 없는 항공사도 입력할 수 있다. 이름이 맞으면 IATA 코드를 채워준다.
            onChange={(value) =>
              onAirlineChange({
                name: value,
                code: findAirlineByName(value)?.code ?? "",
              })
            }
            onPick={(item) => onAirlineChange({ name: item.name, code: item.code })}
            placeholder="예) 대한항공"
            aria-label={airlineLabelText}
          />
        )}
      </Field>

      <Field label={flightLabelText} error={flightError}>
        <div
          className={`flex items-center rounded-xl border focus-within:ring-2 focus-within:ring-indigo-100 ${
            flightError
              ? "border-rose-400 focus-within:border-rose-500"
              : "border-slate-200 focus-within:border-indigo-500"
          }`}
        >
          <span
            className={`w-11 shrink-0 rounded-l-xl border-r py-3 text-center text-base font-semibold tabular-nums ${
              airlineCode
                ? "border-slate-200 text-slate-600"
                : "border-slate-100 text-slate-300"
            } ${disabled ? "bg-slate-50" : "bg-white"}`}
            aria-hidden="true"
          >
            {airlineCode || "--"}
          </span>
          <input
            value={flightNumber}
            onChange={(event) =>
              onFlightNumberChange(event.target.value.replace(/\D/g, "").slice(0, 4))
            }
            inputMode="numeric"
            placeholder="001"
            aria-label={flightLabelText}
            className="w-full min-w-0 rounded-r-xl bg-transparent px-3 py-3 text-base tabular-nums text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
        </div>
      </Field>
    </div>
  );
}

function StepFlight() {
  const { data, update, errors } = useOnboarding();

  // '날짜만 등록' 캘린더: 숙박 기간처럼 시작일·종료일을 모두 고르면 바로 반영하고 닫는다.
  const [tempRange, setTempRange] = useState<[Date | null, Date | null]>([null, null]);
  const [rangeOpen, setRangeOpen] = useState(false);
  const rangeRef = useRef<HTMLDivElement>(null);
  const closeRange = useCallback(() => setRangeOpen(false), []);
  useOutsideClose(rangeRef, closeRange);

  const toggleRange = () => {
    setTempRange([fromISODate(data.startDate), fromISODate(data.endDate)]);
    setRangeOpen((previous) => !previous);
  };

  const pickRange = ([start, end]: [Date | null, Date | null]) => {
    setTempRange([start, end]);
    if (start && end) {
      update({ startDate: toISODate(start), endDate: toISODate(end) });
      setRangeOpen(false);
    }
  };

  const sameAirline = data.sameReturnAirline;
  const returnAirline = returnAirlineOf(data);

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-slate-900">언제 다녀오시나요?</h2>
        <p className="mt-1 text-sm text-slate-500">
          항공권이 있으면 도착 시각에 맞춰 첫날 일정을 배치해요.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        {DATE_MODES.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => update({ dateMode: tab.key })}
            className={`rounded-lg py-2.5 text-sm font-medium transition-colors ${
              data.dateMode === tab.key
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {data.dateMode === "flight" ? (
        <div className="space-y-5">
          <section className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-700">가는 편</h3>
            <AirlineFlightFields
              id="departure-airline"
              airlineLabelText="항공사"
              flightLabelText="편명"
              airline={data.airline}
              airlineCode={data.airlineCode}
              flightNumber={data.flightNumber}
              airlineError={errors.airline}
              flightError={errors.flightNumber}
              onAirlineChange={({ name, code }) =>
                update({ airline: name, airlineCode: code })
              }
              onFlightNumberChange={(value) => update({ flightNumber: value })}
            />
            <div className="grid grid-cols-2 gap-3">
              <AirportInput
                id="departure-airport"
                ariaLabel="가는 편 출발 공항"
                label="출발 공항"
                value={data.departureAirport}
                error={errors.departureAirport}
                onChange={(value) => update({ departureAirport: value })}
              />
              <AirportInput
                id="arrival-airport"
                ariaLabel="가는 편 도착 공항"
                label="도착 공항"
                value={data.arrivalAirport}
                error={errors.arrivalAirport}
                onChange={(value) => update({ arrivalAirport: value })}
              />
            </div>
            <Field label="출국 일시" error={errors.departureAt}>
              <DateTimeField
                value={data.departureAt}
                error={errors.departureAt}
                ariaLabel="출국 일시"
                onChange={(value) => update({ departureAt: value })}
              />
            </Field>
          </section>

          <section className="space-y-3 border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-700">오는 편</h3>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={sameAirline}
                  onChange={(event) =>
                    update({
                      sameReturnAirline: event.target.checked,
                      // 직접 입력으로 바꾸면 출국 항공사를 기본값으로 얹어준다.
                      returnAirline: event.target.checked ? "" : data.airline,
                      returnAirlineCode: event.target.checked ? "" : data.airlineCode,
                    })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-200"
                />
                귀국 항공사 동일
              </label>
            </div>

            <AirlineFlightFields
              id="return-airline"
              airlineLabelText="귀국 항공사"
              flightLabelText="귀국 편명"
              airline={returnAirline.name}
              airlineCode={returnAirline.code}
              flightNumber={data.returnFlightNumber}
              disabled={sameAirline}
              airlineError={errors.returnAirline}
              onAirlineChange={({ name, code }) =>
                update({ returnAirline: name, returnAirlineCode: code })
              }
              onFlightNumberChange={(value) => update({ returnFlightNumber: value })}
            />
            <div className="grid grid-cols-2 gap-3">
              <AirportInput
                id="return-departure-airport"
                ariaLabel="오는 편 출발 공항"
                label="출발 공항"
                value={data.returnDepartureAirport}
                error={errors.returnDepartureAirport}
                onChange={(value) => update({ returnDepartureAirport: value })}
              />
              <AirportInput
                id="return-arrival-airport"
                ariaLabel="오는 편 도착 공항"
                label="도착 공항"
                value={data.returnArrivalAirport}
                error={errors.returnArrivalAirport}
                onChange={(value) => update({ returnArrivalAirport: value })}
              />
            </div>
            <Field label="귀국 일시" error={errors.returnArrivalAt}>
              <DateTimeField
                value={data.returnArrivalAt}
                error={errors.returnArrivalAt}
                minDate={data.departureAt ? data.departureAt.slice(0, 10) : undefined}
                ariaLabel="귀국 일시"
                onChange={(value) => update({ returnArrivalAt: value })}
              />
            </Field>
          </section>
        </div>
      ) : (
        <Field label="여행 기간" error={errors.startDate || errors.endDate}>
          <div ref={rangeRef} className="relative w-full">
            <PickerButton
              icon="far fa-calendar"
              open={rangeOpen}
              invalid={Boolean(errors.startDate || errors.endDate)}
              placeholder="여행 기간을 선택하세요"
              ariaLabel="여행 기간"
              onClick={toggleRange}
            >
              {data.startDate && data.endDate
                ? `${formatKoreanDate(data.startDate)} ~ ${formatKoreanDate(data.endDate)}`
                : ""}
            </PickerButton>

            {rangeOpen && (
              // Field가 <label>이라 날짜 클릭이 PickerButton으로 전달돼 달력이 닫히는 것을 막는다.
              <div className={POPOVER_CLASS} onClick={(event) => event.preventDefault()}>
                <DatePicker
                  selectsRange
                  inline
                  minDate={new Date()}
                  startDate={tempRange[0]}
                  endDate={tempRange[1]}
                  onChange={pickRange}
                  renderCustomHeader={CalendarHeader}
                  formatWeekDay={formatWeekDay}
                />
              </div>
            )}
          </div>
        </Field>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Step 3 — 숙소 (Skip 가능)
 * ------------------------------------------------------------------ */

/** 입력어가 바뀌면 300ms 뒤 숙소 자동완성을 요청한다. 숙소를 고른 뒤(enabled=false)에는 멈춘다. */
function useHotelSuggestions(
  query: string,
  city: DestinationDraft | undefined,
  sessionToken: string,
  enabled: boolean,
) {
  const [items, setItems] = useState<HotelSuggestion[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const keyword = query.trim();
    if (!enabled || keyword.length < 2) {
      setItems([]);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      searchHotels({
        input: keyword,
        sessionToken,
        city: city?.city ?? "",
        cityCode: city?.city_code ?? "",
      })
        .then((result) => {
          if (cancelled) return;
          setItems(result);
          setFailed(false);
        })
        .catch(() => {
          if (cancelled) return;
          setItems([]);
          setFailed(true);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, city?.city, city?.city_code, sessionToken, enabled]);

  return { items, failed };
}

const hotelKey = (hotel: HotelSuggestion) => hotel.place_id;
const hotelHint = () => null;
const hotelLabel = (hotel: HotelSuggestion) => (
  <span className="block">
    <span className="block truncate">{hotel.name}</span>
    {hotel.description && (
      <span className="block truncate text-xs text-slate-400">{hotel.description}</span>
    )}
  </span>
);

/** "2026-10-01" -> "10월 1일 (목)" */
const formatShortDate = (value: string) => formatKoreanDate(value).replace(/^\d+년 /, "");

/** "2026-10-26" -> "2026-10-27" */
const nextDay = (value: string) => {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + 1);
  return toISODate(date);
};

/** 다른 숙소가 이미 묵는 밤인지. 체크아웃 날은 비어 있으므로 다음 숙소의 체크인으로 쓸 수 있다. */
const isNightTaken = (date: string, stays: Stay[]) =>
  stays.some((stay) => stay.check_in <= date && date < stay.check_out);

/** start에 체크인했을 때 가장 늦은 체크아웃 날. 뒤 숙소의 체크인 날 또는 여행 종료일이다. */
const stayLimitFrom = (start: string, stays: Stay[], end: string) =>
  stays.reduce(
    (limit, stay) => (stay.check_in > start && stay.check_in < limit ? stay.check_in : limit),
    end,
  );

/**
 * 체크인~체크아웃 범위 선택. 두 날짜를 모두 고르면 바로 반영하고 닫는다.
 * 다른 숙소(otherStays)가 묵는 밤은 고를 수 없고, 그 사이의 빈 구간은 자유롭게 고를 수 있다.
 */
interface StayRangeFieldProps {
  checkIn: string;
  checkOut: string;
  /** 여행 시작일 */
  min: string;
  /** 여행 종료일 */
  max: string;
  /** 다른 숙소들의 숙박 기간. 이미 묵는 밤은 고를 수 없다. */
  otherStays: Stay[];
  error?: string;
  ariaLabel: string;
  onChange: (checkIn: string, checkOut: string) => void;
}

function StayRangeField({
  checkIn,
  checkOut,
  min,
  max,
  otherStays,
  error,
  ariaLabel,
  onChange,
}: StayRangeFieldProps) {
  const [open, setOpen] = useState(false);
  const [temp, setTemp] = useState<[Date | null, Date | null]>([null, null]);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useOutsideClose(wrapperRef, close);

  const toggle = () => {
    setTemp([fromISODate(checkIn), fromISODate(checkOut)]);
    setOpen((previous) => !previous);
  };

  const pick = ([start, end]: [Date | null, Date | null]) => {
    setTemp([start, end]);
    if (start && end) {
      onChange(toISODate(start), toISODate(end));
      setOpen(false);
    }
  };

  // 체크인을 고른 뒤에는 그 뒤로 이어서 묵을 수 있는 날까지만 체크아웃으로 고를 수 있다.
  // 체크인보다 앞선 날을 누르면 체크인을 다시 고르는 것이다.
  const lastDay = max || "9999-12-31";
  const filterDate = (date: Date) => {
    const value = toISODate(date);
    const start = temp[0] && !temp[1] ? toISODate(temp[0]) : "";
    if (start && value === start) return false;
    if (start && value > start) return value <= stayLimitFrom(start, otherStays, lastDay);
    return value < lastDay && !isNightTaken(value, otherStays);
  };

  const checkInDate = fromISODate(checkIn);
  const checkOutDate = fromISODate(checkOut);
  const nights =
    checkInDate && checkOutDate
      ? Math.round((checkOutDate.getTime() - checkInDate.getTime()) / 86400000)
      : 0;

  return (
    <div ref={wrapperRef} className="relative">
      <PickerButton
        icon="far fa-calendar"
        open={open}
        invalid={Boolean(error)}
        placeholder="체크인 ~ 체크아웃"
        ariaLabel={ariaLabel}
        onClick={toggle}
      >
        {checkIn && checkOut
          ? `${formatShortDate(checkIn)} ~ ${formatShortDate(checkOut)} · ${nights}박`
          : ""}
      </PickerButton>

      {open && (
        // Field가 <label>이라 날짜 클릭이 PickerButton으로 전달돼 달력이 닫히는 것을 막는다.
        <div className={POPOVER_CLASS} onClick={(event) => event.preventDefault()}>
          <DatePicker
            selectsRange
            inline
            minDate={fromISODate(min) ?? undefined}
            maxDate={fromISODate(max) ?? undefined}
            startDate={temp[0]}
            endDate={temp[1]}
            filterDate={filterDate}
            onChange={pick}
            renderCustomHeader={CalendarHeader}
            formatWeekDay={formatWeekDay}
          />
        </div>
      )}
    </div>
  );
}

/** 숙소 한 칸: (여행지 선택) + 숙소 검색 + 자동 매핑된 주소 + 숙박 기간. */
interface HotelRowProps {
  hotel: HotelDraft;
  index: number;
  total: number;
  /** Step 1에서 입력한 여행지(빈 줄 제외) */
  cities: DestinationDraft[];
  tripRange: TripRange;
  otherStays: Stay[];
  error?: HotelErrors;
  onChange: (patch: Partial<HotelDraft>) => void;
  onRemove: () => void;
}

function HotelRow({
  hotel,
  index,
  total,
  cities,
  tripRange,
  otherStays,
  error,
  onChange,
  onRemove,
}: HotelRowProps) {
  // 도시를 아직 정하지 않았으면 첫 여행지로 검색한다.
  const city = cities.find((item) => item.city === hotel.city) ?? cities[0];
  const { items, failed } = useHotelSuggestions(
    hotel.name,
    city,
    hotel.sessionToken,
    !hotel.place_id,
  );

  const pickHotel = async (item: HotelSuggestion) => {
    const selection: Partial<HotelDraft> = {
      name: item.name,
      place_id: item.place_id,
      city: city?.city ?? "",
      city_code: city?.city_code ?? "",
      // Details 호출로 이 세션이 끝나므로, 다음 검색은 새 토큰으로 시작한다.
      sessionToken: crypto.randomUUID(),
    };
    onChange(selection);
    try {
      const detail = await getHotelDetails(item.place_id, hotel.sessionToken);
      // onChange는 호출 시점의 숙소 목록에 덮어쓰므로, 선택값을 함께 다시 넣는다.
      onChange({
        ...selection,
        address: detail.address,
        latitude: detail.latitude,
        longitude: detail.longitude,
      });
    } catch {
      onChange({ ...selection, place_id: "" });
    }
  };

  // 다른 여행지로 바꾸면 이전 도시에서 고른 숙소는 남기지 않는다.
  const selectCity = (item: DestinationDraft) => {
    if (item.city === city?.city) return;
    onChange({
      city: item.city,
      name: "",
      place_id: "",
      address: "",
      latitude: null,
      longitude: null,
      city_code: "",
    });
  };

  const nameError =
    error?.name ?? (failed ? "숙소 검색을 사용할 수 없어요. 잠시 후 다시 시도해 주세요." : "");

  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-700">숙소 {index + 1}</span>
        {total > 1 && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`숙소 ${index + 1} 삭제`}
            title="삭제"
            className="rounded-lg px-2.5 py-1.5 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-600"
          >
            <i className="fas fa-trash" aria-hidden="true" />
          </button>
        )}
      </div>

      {cities.length > 1 ? (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="숙소가 있는 여행지">
          {cities.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => selectCity(item)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                item.city === city?.city
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"
              }`}
            >
              {item.city}
            </button>
          ))}
        </div>
      ) : (
        city && (
          <p className="text-xs text-slate-500">
            <i className="fas fa-location-dot mr-1 text-slate-400" aria-hidden="true" />
            {city.city} 지역에서 검색해요
          </p>
        )
      )}

      <Field label="숙소명" error={nameError}>
        <SuggestInput
          id={hotel.id}
          value={hotel.name}
          error={nameError}
          items={items}
          keyOf={hotelKey}
          renderLabel={hotelLabel}
          renderHint={hotelHint}
          // 다시 입력하면 이전 선택(주소·좌표)은 무효가 된다.
          onChange={(value) =>
            onChange({ name: value, place_id: "", address: "", latitude: null, longitude: null })
          }
          onPick={pickHotel}
          placeholder={city ? `${city.city}의 숙소 검색` : "숙소 검색"}
          aria-label={`숙소 ${index + 1} 이름`}
        />
        {hotel.address && (
          <span className="mt-1.5 flex items-start gap-1.5 text-xs text-slate-500">
            <i className="fas fa-location-dot mt-0.5 text-slate-400" aria-hidden="true" />
            {hotel.address}
          </span>
        )}
      </Field>

      <Field label="숙박 기간" error={error?.stay}>
        <StayRangeField
          checkIn={hotel.check_in}
          checkOut={hotel.check_out}
          min={tripRange.start}
          max={tripRange.end}
          otherStays={otherStays}
          error={error?.stay}
          ariaLabel={`숙소 ${index + 1} 숙박 기간`}
          onChange={(checkIn, checkOut) => onChange({ check_in: checkIn, check_out: checkOut })}
        />
      </Field>
    </div>
  );
}

/** 여행 기간 중 어느 숙소도 묵지 않는 첫 구간. 여행 기간이 모두 채워졌으면 null. */
function firstFreeStay(
  stays: Stay[],
  tripRange: TripRange,
): { checkIn: string; checkOut: string } | null {
  for (let date = tripRange.start; date < tripRange.end; date = nextDay(date)) {
    if (!isNightTaken(date, stays)) {
      return { checkIn: date, checkOut: stayLimitFrom(date, stays, tripRange.end) };
    }
  }
  return null;
}

function StepHotel() {
  const { data, update, errors, tripRange, hotelNotice, dismissHotelNotice } = useOnboarding();
  const hotels = data.hotels;
  const cities = data.destinations.filter((dest) => dest.city.trim());
  const stays = hotels.filter((hotel) => hotel.check_in && hotel.check_out);
  // 여행 기간 중 비어 있는 밤이 하나도 없으면 더 추가할 수 없다.
  const freeStay =
    tripRange.start && tripRange.end ? firstFreeStay(stays, tripRange) : undefined;
  const canAddHotel = freeStay !== null;

  const setHotel = (id: string, patch: Partial<HotelDraft>) =>
    update({
      hotels: hotels.map((hotel) => (hotel.id === id ? { ...hotel, ...patch } : hotel)),
    });

  // 새 숙소는 비어 있는 첫 구간으로, 여행지는 순서상 다음 도시로 시작한다.
  const addHotel = () => {
    const nextCity = cities[Math.min(hotels.length, cities.length - 1)];
    update({
      hotels: [
        ...hotels,
        emptyHotel({
          city: nextCity?.city ?? "",
          checkIn: freeStay?.checkIn ?? "",
          checkOut: freeStay?.checkOut ?? "",
        }),
      ],
    });
  };

  const removeHotel = (id: string) => update({ hotels: hotels.filter((hotel) => hotel.id !== id) });

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-slate-900">숙소를 등록할까요?</h2>
        <p className="mt-1 text-sm text-slate-500">
          숙소를 기준으로 매일의 동선을 최적화해요. 일부 일정만 등록하거나 나중에 추가해도
          괜찮아요.
        </p>
      </header>

      {hotelNotice && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <i className="fas fa-circle-info mt-0.5" aria-hidden="true" />
          <span className="flex-1">{hotelNotice}</span>
          <button
            type="button"
            onClick={dismissHotelNotice}
            aria-label="안내 닫기"
            className="text-amber-500 hover:text-amber-700"
          >
            <i className="fas fa-xmark" aria-hidden="true" />
          </button>
        </div>
      )}

      <fieldset disabled={data.skipHotel} className="space-y-3 disabled:opacity-40">
        {hotels.map((hotel, index) => (
          <HotelRow
            key={hotel.id}
            hotel={hotel}
            index={index}
            total={hotels.length}
            cities={cities}
            tripRange={tripRange}
            otherStays={stays.filter((stay) => stay.id !== hotel.id)}
            error={errors.hotels?.[hotel.id]}
            onChange={(patch) => setHotel(hotel.id, patch)}
            onRemove={() => removeHotel(hotel.id)}
          />
        ))}
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-slate-400">숙소명을 비워둔 칸은 저장하지 않아요.</p>
          <button
            type="button"
            onClick={addHotel}
            disabled={!canAddHotel}
            title={canAddHotel ? undefined : "여행 기간이 모두 채워졌어요"}
            className="shrink-0 rounded-xl border border-dashed border-indigo-300 px-3.5 py-2 text-sm font-medium text-indigo-600 transition-colors hover:border-indigo-500 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
          >
            + 숙소 추가
          </button>
        </div>
      </fieldset>

      <button
        type="button"
        onClick={() => update({ skipHotel: !data.skipHotel })}
        className="w-full rounded-xl border border-dashed border-slate-300 py-3 text-sm font-medium text-slate-500 transition-colors hover:border-indigo-300 hover:text-indigo-600"
      >
        {data.skipHotel ? "숙소 직접 입력하기" : "숙소 선택 없이 계속하기 · 건너뛰기"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Wizard
 * ------------------------------------------------------------------ */

/**
 * Step 1에서 여행지가 빠지거나 바뀌면 그 도시에 연결된 숙소를 정리한다.
 * 고른 숙소는 목록에서 빼고(안내 문구로 알림), 아직 고르지 않은 칸은 첫 여행지로 옮긴다.
 */
function syncHotelsWithDestinations(
  hotels: HotelDraft[],
  destinations: DestinationDraft[],
): { hotels: HotelDraft[]; notice: string } {
  const cityNames = destinations.map((dest) => dest.city.trim()).filter(Boolean);
  const removed: HotelDraft[] = [];
  const kept: HotelDraft[] = [];
  hotels.forEach((hotel) => {
    if (!hotel.city || cityNames.includes(hotel.city)) {
      kept.push(hotel);
    } else if (hotel.place_id) {
      removed.push(hotel);
    } else {
      kept.push({ ...hotel, city: cityNames[0] ?? "", name: "" });
    }
  });
  if (removed.length === 0) return { hotels: kept, notice: "" };

  const removedCities = [...new Set(removed.map((hotel) => hotel.city))].join(", ");
  return {
    hotels: kept.length > 0 ? kept : [emptyHotel({ city: cityNames[0] ?? "" })],
    notice: `여행지에서 ${removedCities}이(가) 빠져서 선택했던 숙소 ${removed.length}곳을 목록에서 뺐어요.`,
  };
}

interface OnboardingWizardProps {
  /** 여행 저장이 끝나면 만들어진 여행으로 호출한다. */
  onComplete?: (trip: Trip) => void;
}

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<OnboardingData>(INITIAL_DATA);
  const [errors, setErrors] = useState<OnboardingErrors>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [hotelNotice, setHotelNotice] = useState("");
  const dismissHotelNotice = useCallback(() => setHotelNotice(""), []);

  // 값을 바꾼 필드의 에러는 지운다(에러 키는 OnboardingData 필드명과 같다).
  const update = useCallback((patch: OnboardingPatch) => {
    setData((previous) => ({ ...previous, ...patch }));
    setErrors((previous) => {
      const next = { ...previous };
      for (const key of Object.keys(patch)) delete next[key as keyof OnboardingErrors];
      return next;
    });
  }, []);

  // Step 3의 체크인/체크아웃 선택 범위를 제한하기 위한 여행 기간
  const tripRange = useMemo<TripRange>(
    () =>
      data.dateMode === "flight"
        ? { start: toDate(data.departureAt), end: toDate(data.returnArrivalAt) }
        : { start: data.startDate, end: data.endDate },
    [data.dateMode, data.departureAt, data.returnArrivalAt, data.startDate, data.endDate],
  );

  const submit = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const trip = await createTrip(buildTripPayload(data));
      onComplete?.(trip);
    } catch (error) {
      setSubmitError(toErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const goNext = () => {
    const stepErrors = validateStep(step, data);
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    setErrors({});

    if (step === TOTAL_STEPS) {
      submit();
      return;
    }
    if (step === 1) {
      const synced = syncHotelsWithDestinations(data.hotels, data.destinations);
      update({ hotels: synced.hotels });
      setHotelNotice(synced.notice);
    }
    // Step 2를 마치면 숙소가 하나뿐이고 기간이 비어 있을 때 여행 기간 전체로 채워둔다.
    if (step === 2 && data.hotels.length === 1 && !data.hotels[0].check_in) {
      update({
        hotels: [
          { ...data.hotels[0], check_in: tripRange.start, check_out: tripRange.end },
        ],
      });
    }
    setStep(step + 1);
  };

  const goBack = () => {
    setErrors({});
    setSubmitError("");
    setStep((previous) => Math.max(1, previous - 1));
  };

  const contextValue = useMemo<OnboardingContextValue>(
    () => ({ data, update, errors, step, tripRange, hotelNotice, dismissHotelNotice }),
    [data, update, errors, step, tripRange, hotelNotice, dismissHotelNotice],
  );

  const hasHotel = !data.skipHotel && data.hotels.some((hotel) => !isBlankHotel(hotel));
  const nextLabel =
    step < TOTAL_STEPS ? "다음" : hasHotel ? "여행 만들기" : "숙소 없이 시작하기";

  return (
    <OnboardingContext.Provider value={contextValue}>
      {/* 상단 내비게이션 바(AppLayout) 아래에 그리므로 로그아웃은 헤더에 있다. */}
      <div className="flex justify-center px-4 py-8 sm:py-12">
        <div className="w-full max-w-md">
          <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 sm:p-7">
            <ProgressBar step={step} />

            <form
              onSubmit={(event) => {
                event.preventDefault();
                goNext();
              }}
            >
              {step === 1 && <StepDestination />}
              {step === 2 && <StepFlight />}
              {step === 3 && <StepHotel />}

              {submitError && (
                <p className="mt-5 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {submitError}
                </p>
              )}

              <div className="mt-7 flex gap-2">
                {step > 1 && (
                  <button
                    type="button"
                    onClick={goBack}
                    disabled={submitting}
                    className="rounded-xl border border-slate-200 px-5 py-3.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
                  >
                    이전
                  </button>
                )}
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 rounded-xl bg-indigo-600 px-5 py-3.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
                >
                  {submitting ? "저장하는 중..." : nextLabel}
                </button>
              </div>
            </form>
          </div>

          <p className="mt-4 text-center text-xs text-slate-400">
            입력한 정보는 언제든 여행 상세에서 수정할 수 있어요.
          </p>
        </div>
      </div>
    </OnboardingContext.Provider>
  );
}
