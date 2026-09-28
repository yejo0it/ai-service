import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { createTrip, getHotelDetails, searchHotels, toErrorMessage } from "../api/client";
import { findCityByName, searchCities } from "./cities";
import { findAirlineByName, searchAirlines } from "./airlines";

/* ------------------------------------------------------------------ *
 * 온보딩 상태 (Step 1~3 입력값 누적)
 * ------------------------------------------------------------------ */

const TOTAL_STEPS = 3;

/**
 * Step 1의 여행지 한 줄. 도시 이동 순서대로 배열에 쌓인다.
 * id는 행 삭제 시 React key가 밀리지 않게 하기 위한 값으로, 전송 payload에는 포함되지 않는다.
 */
let destinationSeq = 0;
const emptyDestination = () => ({
  id: `destination-${(destinationSeq += 1)}`,
  city: "",
  city_code: "",
});

/**
 * Step 3의 숙소 한 칸. sessionToken은 Google Places 자동완성 세션 단위로 쓰는 UUID이며,
 * 숙소를 고르면(Details 호출로 세션 종료) 새 토큰으로 바꾼다. id·sessionToken은 전송하지 않는다.
 */
let hotelSeq = 0;
const emptyHotel = ({ city = "", checkIn = "", checkOut = "" } = {}) => ({
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

const INITIAL_DATA = {
  // Step 1
  destinations: [emptyDestination()],
  // Step 2
  dateMode: "flight", // "flight" | "dates"
  airline: "",
  airlineCode: "", // 선택한 항공사의 IATA 코드. 편명 앞에 붙는다.
  flightNumber: "",
  departureAt: "",
  sameReturnAirline: true, // 귀국 항공사 동일
  returnAirline: "",
  returnAirlineCode: "",
  returnFlightNumber: "",
  returnArrivalAt: "",
  startDate: "",
  endDate: "",
  // Step 3
  skipHotel: false,
  hotels: [emptyHotel()],
};

const OnboardingContext = createContext(null);

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error("useOnboarding은 <OnboardingWizard> 안에서만 사용할 수 있습니다.");
  }
  return context;
}

/** datetime-local("2026-09-01T10:30") -> "2026-09-01" */
const toDate = (value) => (value ? value.slice(0, 10) : "");

/** '귀국 항공사 동일'이 켜져 있으면 출국 항공사를 그대로 쓴다. */
export function returnAirlineOf(data) {
  return data.sameReturnAirline
    ? { name: data.airline.trim(), code: data.airlineCode }
    : { name: data.returnAirline.trim(), code: data.returnAirlineCode };
}

/** 누적된 상태를 DRF payload로 변환 */
export function buildTripPayload(data) {
  const usesFlight = data.dateMode === "flight";
  const payload = {
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

/** 숙소별 에러를 { [hotel.id]: { name, stay } } 형태로 모은다. */
function validateHotels(hotels) {
  const errors = {};
  const add = (id, key, message) => {
    errors[id] = { ...errors[id], [key]: errors[id]?.[key] ?? message };
  };

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
function validateStep(step, data) {
  const errors = {};
  if (step === 1 && !data.destinations.some((dest) => dest.city.trim())) {
    errors.destinations = "목적지를 입력해 주세요.";
  }
  if (step === 2) {
    if (data.dateMode === "flight") {
      if (!data.airline.trim()) errors.airline = "항공사를 선택해 주세요.";
      if (!data.flightNumber.trim()) errors.flightNumber = "편명을 입력해 주세요.";
      if (!data.sameReturnAirline && !data.returnAirline.trim()) {
        errors.returnAirline = "귀국 항공사를 선택해 주세요.";
      }
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

function ProgressBar({ step }) {
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

function Field({ label, error, hint, children }) {
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

function TextInput({ error, ...props }) {
  const errorClass = error
    ? "border-rose-400 focus:border-rose-500 focus:ring-rose-100"
    : "";
  return <input {...props} className={`${INPUT_CLASS} ${errorClass}`} />;
}

/**
 * 입력하면 후보 목록을 드롭다운으로 보여주는 자동완성 입력.
 * 목록에 없는 값도 그대로 입력할 수 있고, 포커스만으로는 목록이 열리지 않는다.
 * `search`는 모듈 상수 함수를 넘겨야 useMemo가 유효하다.
 */
function SuggestInput({
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
  ...inputProps
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  // items를 넘기면(비동기 검색 결과) search 대신 그대로 후보로 쓴다.
  const suggestions = useMemo(() => items ?? search(value), [items, search, value]);
  const listId = `${id}-listbox`;

  const pick = (item) => {
    onPick(item);
    setOpen(false);
  };

  const handleKeyDown = (event) => {
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
        onBlur={() => setOpen(false)}
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

const cityKey = (city) => city.city_code;
const cityHint = (city) => city.city_code;
const cityLabel = (city) => <span className="block truncate">{city.city}</span>;

/** 타임라인 노드. 입력된 행은 채워진 핀, 빈 행은 흐린 핀으로 표시한다. */
function TimelineNode({ filled }) {
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

function DestinationRow({ dest, index, total, error, onChange, onRemove }) {
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
            // 목록에 없는 도시도 그대로 입력할 수 있다. 이름이 정확히 맞으면 코드를 채워준다.
            onChange={(value) =>
              onChange({ city: value, city_code: findCityByName(value)?.city_code ?? "" })
            }
            onPick={(city) => onChange({ city: city.city, city_code: city.city_code })}
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

  const setDestination = (index, patch) =>
    update({
      destinations: destinations.map((dest, position) =>
        position === index ? { ...dest, ...patch } : dest,
      ),
    });

  const addDestination = () =>
    update({ destinations: [...destinations, emptyDestination()] });

  const removeDestination = (index) =>
    update({
      destinations: destinations.filter((_, position) => position !== index),
    });

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
              error={errors.destinations}
              onChange={(patch) => setDestination(index, patch)}
              onRemove={() => removeDestination(index)}
            />
          ))}
        </div>
        {errors.destinations && (
          // 타임라인 레일(w-6) + gap(2) 만큼 들여써 입력칸과 좌측을 맞춘다.
          <span className="mt-1 block pl-8 text-xs text-rose-600">
            {errors.destinations}
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

const DATE_MODES = [
  { key: "flight", label: "항공권 등록" },
  { key: "dates", label: "날짜만 등록" },
];

const pad2 = (value) => String(value).padStart(2, "0");

/** Date -> "2026-10-01" */
const toISODate = (date) =>
  date ? `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` : "";

/** "2026-10-01" -> Date (타임존 밀림을 피하려고 로컬 자정으로 만든다) */
const fromISODate = (value) => (value ? new Date(`${value}T00:00:00`) : null);

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-10-01" -> "2026년 10월 1일 (목)" */
const formatKoreanDate = (value) => {
  const date = fromISODate(value);
  if (!date) return "";
  return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 (${
    WEEKDAYS[date.getDay()]
  })`;
};

const HOURS = Array.from({ length: 24 }, (_, index) => pad2(index));
const MINUTES = Array.from({ length: 12 }, (_, index) => pad2(index * 5));

/** 팝오버 바깥을 누르면 닫는다. */
function useOutsideClose(ref, onClose) {
  useEffect(() => {
    const handle = (event) => {
      if (ref.current && !ref.current.contains(event.target)) onClose();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [ref, onClose]);
}

/** 달력/시간 팝오버를 여는 버튼. 좌측 아이콘 + 값 + 우측 쉐브론. */
function PickerButton({ icon, children, placeholder, open, invalid, onClick, ariaLabel }) {
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
const WEEKDAY_KO = {
  Sunday: "일",
  Monday: "월",
  Tuesday: "화",
  Wednesday: "수",
  Thursday: "목",
  Friday: "금",
  Saturday: "토",
};
const formatWeekDay = (name) => WEEKDAY_KO[name] ?? name.slice(0, 1);

/** 달력 상단의 ‹ 2026년 10월 › 헤더. */
function CalendarHeader({ date, decreaseMonth, increaseMonth, prevMonthButtonDisabled }) {
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
function useScrollToSelected(listRef, itemRef) {
  useEffect(() => {
    const list = listRef.current;
    const item = itemRef.current;
    if (!list || !item) return;
    list.scrollTop = item.offsetTop - list.clientHeight / 2 + item.clientHeight / 2;
  }, [listRef, itemRef]);
}

/** 시·분을 각각 세로로 스크롤해 고르는 목록. */
function TimeColumns({ hour, minute, onPick }) {
  const hourList = useRef(null);
  const hourItem = useRef(null);
  const minuteList = useRef(null);
  const minuteItem = useRef(null);
  useScrollToSelected(hourList, hourItem);
  useScrollToSelected(minuteList, minuteItem);

  const cell = (value, active, onClick, ref) => (
    <button
      key={value}
      ref={active ? ref : undefined}
      type="button"
      onClick={onClick}
      className={`w-full rounded-lg px-4 py-1.5 text-center text-sm tabular-nums transition-colors ${
        active ? "bg-slate-900 font-semibold text-white" : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {value}
    </button>
  );

  return (
    <div className="flex gap-1">
      <div ref={hourList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
        {HOURS.map((item) =>
          cell(item, item === hour, () => onPick(item, minute || "00"), hourItem),
        )}
      </div>
      <div className="w-px bg-slate-100" />
      <div ref={minuteList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
        {MINUTES.map((item) =>
          cell(item, item === minute, () => onPick(hour || "09", item), minuteItem),
        )}
      </div>
    </div>
  );
}

/** 달력 + 시각 드롭다운 한 쌍. 값은 "YYYY-MM-DDTHH:mm" 문자열. */
function DateTimeField({ value, onChange, minDate, error, ariaLabel }) {
  const [open, setOpen] = useState(null); // null | "date" | "time"
  const wrapperRef = useRef(null);
  const close = useCallback(() => setOpen(null), []);
  useOutsideClose(wrapperRef, close);

  const datePart = value ? value.slice(0, 10) : "";
  const [hour = "", minute = ""] = value ? value.slice(11, 16).split(":") : [];

  const pickDate = (date) => {
    const iso = toISODate(date);
    // 날짜를 먼저 고르는 흐름이라, 시각이 비어 있으면 09:00을 기본으로 채운다.
    onChange(iso ? `${iso}T${hour || "09"}:${minute || "00"}` : "");
    setOpen(null);
  };

  const pickTime = (nextHour, nextMinute) => {
    if (!datePart) return;
    onChange(`${datePart}T${nextHour}:${nextMinute}`);
  };

  return (
    <div ref={wrapperRef}>
      <div className="grid grid-cols-[1.6fr_1fr] gap-2">
        <div className="relative">
          <PickerButton
            icon="far fa-calendar"
            open={open === "date"}
            invalid={Boolean(error)}
            placeholder="날짜 선택"
            ariaLabel={ariaLabel}
            onClick={() => setOpen(open === "date" ? null : "date")}
          >
            {datePart ? formatKoreanDate(datePart) : ""}
          </PickerButton>

          {open === "date" && (
            // Field가 <label>이라 날짜 클릭이 PickerButton으로 전달돼 달력이 다시 열리는 것을 막는다.
            <div className={POPOVER_CLASS} onClick={(event) => event.preventDefault()}>
              <DatePicker
                inline
                selected={fromISODate(datePart)}
                minDate={minDate ? fromISODate(minDate) : new Date()}
                onChange={pickDate}
                renderCustomHeader={CalendarHeader}
                formatWeekDay={formatWeekDay}
              />
            </div>
          )}
        </div>

        <div className="relative">
          <PickerButton
            icon="far fa-clock"
            open={open === "time"}
            placeholder={datePart ? "시각" : "—"}
            ariaLabel={`${ariaLabel} 시각`}
            onClick={() => datePart && setOpen(open === "time" ? null : "time")}
          >
            {hour && minute ? `${hour}:${minute}` : ""}
          </PickerButton>

          {open === "time" && (
            <div className="absolute right-0 z-30 mt-1.5 rounded-2xl border border-slate-100 bg-white p-2 shadow-xl">
              <div className="mb-1 flex gap-1 px-1 text-center text-[11px] font-medium text-slate-400">
                <span className="w-16">시</span>
                <span className="w-px" />
                <span className="w-16">분</span>
              </div>
              <TimeColumns hour={hour} minute={minute} onPick={pickTime} />
            </div>
          )}
        </div>
      </div>

      {!datePart && (
        <span className="mt-1 block text-xs text-slate-400">
          날짜를 먼저 선택하면 시각을 고를 수 있어요.
        </span>
      )}
    </div>
  );
}

const airlineKey = (airline) => airline.code;
const airlineHint = (airline) => airline.code;

// 항공사 칸이 절반 너비라 국문/영문을 두 줄로 나눠 잘리지 않게 한다.
const airlineLabel = (airline) => (
  <span className="block">
    <span className="block truncate">{airline.name}</span>
    {airline.name_en && (
      <span className="block truncate text-xs text-slate-400">{airline.name_en}</span>
    )}
  </span>
);

/** 항공사 자동완성 + IATA 코드가 앞에 붙는 편명 입력 한 쌍. */
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
}) {
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

  // '날짜만 등록' 캘린더 안에서만 맴도는 임시 기간값
  const [tempRange, setTempRange] = useState([
    fromISODate(data.startDate),
    fromISODate(data.endDate),
  ]);
  const [rangeStart, rangeEnd] = tempRange;
  const [rangeOpen, setRangeOpen] = useState(false);

  const closeRange = () => {
    setTempRange([fromISODate(data.startDate), fromISODate(data.endDate)]);
    setRangeOpen(false);
  };

  const applyRange = () => {
    update({ startDate: toISODate(rangeStart), endDate: toISODate(rangeEnd) });
    setRangeOpen(false);
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
          <div className="relative w-full">
            <PickerButton
              icon="far fa-calendar"
              open={rangeOpen}
              invalid={Boolean(errors.startDate || errors.endDate)}
              placeholder="여행 기간을 선택하세요"
              ariaLabel="여행 기간"
              onClick={() => setRangeOpen((previous) => !previous)}
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
                  startDate={rangeStart}
                  endDate={rangeEnd}
                  onChange={setTempRange}
                  renderCustomHeader={CalendarHeader}
                formatWeekDay={formatWeekDay}
                />
                <div className="mt-3 flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
                  <button
                    type="button"
                    onClick={closeRange}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-slate-500 hover:bg-slate-50"
                  >
                    취소
                  </button>
                  <button
                    type="button"
                    onClick={applyRange}
                    disabled={!rangeStart || !rangeEnd}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-200"
                  >
                    선택
                  </button>
                </div>
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
function useHotelSuggestions(query, city, sessionToken, enabled) {
  const [items, setItems] = useState([]);
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

const hotelKey = (hotel) => hotel.place_id;
const hotelHint = () => null;
const hotelLabel = (hotel) => (
  <span className="block">
    <span className="block truncate">{hotel.name}</span>
    {hotel.description && (
      <span className="block truncate text-xs text-slate-400">{hotel.description}</span>
    )}
  </span>
);

/** "2026-10-01" -> "10월 1일 (목)" */
const formatShortDate = (value) => formatKoreanDate(value).replace(/^\d+년 /, "");

/** 체크인~체크아웃 범위 선택. 두 날짜를 모두 고르면 바로 반영하고 닫는다. */
function StayRangeField({ checkIn, checkOut, min, max, error, ariaLabel, onChange }) {
  const [open, setOpen] = useState(false);
  const [temp, setTemp] = useState([null, null]);
  const wrapperRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useOutsideClose(wrapperRef, close);

  const toggle = () => {
    setTemp([fromISODate(checkIn), fromISODate(checkOut)]);
    setOpen((previous) => !previous);
  };

  const pick = ([start, end]) => {
    setTemp([start, end]);
    if (start && end) {
      onChange(toISODate(start), toISODate(end));
      setOpen(false);
    }
  };

  const nights =
    checkIn && checkOut
      ? Math.round((fromISODate(checkOut) - fromISODate(checkIn)) / 86400000)
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
            minDate={fromISODate(min)}
            maxDate={fromISODate(max)}
            startDate={temp[0]}
            endDate={temp[1]}
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
function HotelRow({ hotel, index, total, cities, tripRange, error, onChange, onRemove }) {
  // 여행지가 바뀌어 저장된 도시가 사라졌으면 첫 여행지로 검색한다.
  const city = cities.find((item) => item.city === hotel.city) ?? cities[0];
  const { items, failed } = useHotelSuggestions(
    hotel.name,
    city,
    hotel.sessionToken,
    !hotel.place_id,
  );

  const pickHotel = async (item) => {
    const selection = {
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

      {cities.length > 1 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="숙소가 있는 여행지">
          {cities.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange({ city: item.city })}
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

      <Field
        label="숙박 기간"
        hint={
          tripRange.start && tripRange.end
            ? `여행 기간(${formatShortDate(tripRange.start)} ~ ${formatShortDate(tripRange.end)}) 안에서 선택할 수 있어요.`
            : undefined
        }
        error={error?.stay}
      >
        <StayRangeField
          checkIn={hotel.check_in}
          checkOut={hotel.check_out}
          min={tripRange.start}
          max={tripRange.end}
          error={error?.stay}
          ariaLabel={`숙소 ${index + 1} 숙박 기간`}
          onChange={(checkIn, checkOut) => onChange({ check_in: checkIn, check_out: checkOut })}
        />
      </Field>
    </div>
  );
}

function StepHotel() {
  const { data, update, errors, tripRange } = useOnboarding();
  const hotels = data.hotels;
  const cities = data.destinations.filter((dest) => dest.city.trim());

  const setHotel = (id, patch) =>
    update({
      hotels: hotels.map((hotel) => (hotel.id === id ? { ...hotel, ...patch } : hotel)),
    });

  // 새 숙소는 앞 숙소의 체크아웃 날부터, 여행지는 순서상 다음 도시로 시작한다.
  const addHotel = () => {
    const last = hotels[hotels.length - 1];
    const nextCity = cities[Math.min(hotels.length, cities.length - 1)];
    update({
      hotels: [
        ...hotels,
        emptyHotel({ city: nextCity?.city ?? "", checkIn: last?.check_out || tripRange.start }),
      ],
    });
  };

  const removeHotel = (id) => update({ hotels: hotels.filter((hotel) => hotel.id !== id) });

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-slate-900">숙소를 등록할까요?</h2>
        <p className="mt-1 text-sm text-slate-500">
          숙소를 기준으로 매일의 동선을 최적화해요. 나중에 추가해도 괜찮아요.
        </p>
      </header>

      <fieldset disabled={data.skipHotel} className="space-y-3 disabled:opacity-40">
        {hotels.map((hotel, index) => (
          <HotelRow
            key={hotel.id}
            hotel={hotel}
            index={index}
            total={hotels.length}
            cities={cities}
            tripRange={tripRange}
            error={errors.hotels?.[hotel.id]}
            onChange={(patch) => setHotel(hotel.id, patch)}
            onRemove={() => removeHotel(hotel.id)}
          />
        ))}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={addHotel}
            className="rounded-xl border border-dashed border-indigo-300 px-3.5 py-2 text-sm font-medium text-indigo-600 transition-colors hover:border-indigo-500 hover:bg-indigo-50"
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
        {data.skipHotel ? "숙소 직접 입력하기" : "아직 숙소가 없어요 · Skip"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Wizard
 * ------------------------------------------------------------------ */

export default function OnboardingWizard({ onComplete }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState(INITIAL_DATA);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const update = useCallback((patch) => {
    setData((previous) => ({ ...previous, ...patch }));
    setErrors((previous) => {
      const next = { ...previous };
      Object.keys(patch).forEach((key) => delete next[key]);
      return next;
    });
  }, []);

  // Step 3의 체크인/체크아웃 선택 범위를 제한하기 위한 여행 기간
  const tripRange = useMemo(
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

  const contextValue = useMemo(
    () => ({ data, update, errors, step, tripRange }),
    [data, update, errors, step, tripRange],
  );

  const nextLabel =
    step < TOTAL_STEPS ? "다음" : data.skipHotel ? "건너뛰고 시작하기" : "여행 만들기";

  return (
    <OnboardingContext.Provider value={contextValue}>
      <div className="flex min-h-screen justify-center bg-slate-50 px-4 py-8 sm:items-center">
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
