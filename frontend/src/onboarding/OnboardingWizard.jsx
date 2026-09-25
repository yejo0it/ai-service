import { createContext, useCallback, useContext, useMemo, useState, useEffect } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { createTrip, toErrorMessage, getAirlines } from "../api/client";
import { findCityByName, searchCities } from "./cities";

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

const INITIAL_DATA = {
  // Step 1
  destinations: [emptyDestination()],
  // Step 2
  dateMode: "flight", // "flight" | "dates"
  // selectOption: [Airline.name_ko],
  airline: "",
  flightNumber: "",
  departureAt: "",
  returnFlightNumber: "",
  returnArrivalAt: "",
  startDate: "",
  endDate: "",
  // Step 3
  skipHotel: false,
  hotelName: "",
  hotelAddress: "",
  checkIn: "",
  checkOut: "",
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
          flight_number: data.flightNumber.trim(),
          departure_at: data.departureAt,
          return_flight_number: data.returnFlightNumber.trim(),
          return_arrival_at: data.returnArrivalAt,
        }
      : null,
    hotels: [],
  };

  if (!data.skipHotel && data.hotelName.trim()) {
    payload.hotels.push({
      name: data.hotelName.trim(),
      address: data.hotelAddress.trim(),
      check_in: data.checkIn,
      check_out: data.checkOut || null,
    });
  }
  return payload;
}

/** 각 단계의 진행 가능 여부 */
function validateStep(step, data) {
  const errors = {};
  if (step === 1 && !data.destinations.some((dest) => dest.city.trim())) {
    errors.destinations = "목적지를 입력해 주세요.";
  }
  if (step === 2) {
    if (data.dateMode === "flight") {
      if (!data.flightNumber.trim()) errors.flightNumber = "편명을 입력해 주세요.";
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
    if (!data.hotelName.trim()) errors.hotelName = "숙소명을 입력해 주세요.";
    if (!data.hotelAddress.trim()) errors.hotelAddress = "주소를 입력해 주세요.";
    if (!data.checkIn) errors.checkIn = "체크인 날짜를 선택해 주세요.";
    if (data.checkIn && data.checkOut && data.checkOut < data.checkIn) {
      errors.checkOut = "체크아웃은 체크인 이후여야 합니다.";
    }
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

/* ------------------------------------------------------------------ *
 * Step 1 — 목적지
 * ------------------------------------------------------------------ */

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

/** 여행지 한 줄: 타임라인 노드 + 도시 자동완성 입력 + 삭제 버튼. */
function DestinationRow({ dest, index, total, error, onChange, onRemove }) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const suggestions = useMemo(() => searchCities(dest.city), [dest.city]);
  const isFirst = index === 0;
  const isLast = index === total - 1;
  const listId = `${dest.id}-listbox`;

  const pick = (city) => {
    onChange({ city: city.city, city_code: city.city_code });
    setOpen(false);
  };

  const handleChange = (value) => {
    // 목록에 없는 도시도 그대로 입력할 수 있다. 이름이 정확히 맞으면 코드를 채워준다.
    onChange({ city: value, city_code: findCityByName(value)?.city_code ?? "" });
    setHighlight(0);
    setOpen(true);
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
    <div className="flex gap-2">
      {/* 첫 행 위/마지막 행 아래로는 선이 뻗지 않는다. */}
      <div className="flex w-6 shrink-0 flex-col items-center" aria-hidden="true">
        <span className={`w-px flex-1 ${isFirst ? "bg-transparent" : "bg-indigo-200"}`} />
        <TimelineNode filled={Boolean(dest.city.trim())} />
        <span className={`w-px flex-1 ${isLast ? "bg-transparent" : "bg-indigo-200"}`} />
      </div>

      <div className="flex flex-1 items-center gap-2 py-1">
        <div className="relative flex-1">
          <TextInput
            value={dest.city}
            error={error}
            onChange={(event) => handleChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => setOpen(false)}
            placeholder={"도시"}
            autoFocus={isFirst}
            aria-label={`여행지 ${index + 1}`}
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
              {suggestions.map((city, position) => (
                <li key={city.city_code} role="option" aria-selected={position === highlight}>
                  <button
                    type="button"
                    // onBlur보다 먼저 실행되어 목록이 닫히는 것을 막는다.
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => pick(city)}
                    onMouseEnter={() => setHighlight(position)}
                    className={`flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-sm transition-colors ${
                      position === highlight
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-slate-700"
                    }`}
                  >
                    <span>{city.city}</span>
                    <span className="text-xs tabular-nums text-slate-400">
                      {city.city_code}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
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

function StepFlight() {
  const { data, update, errors } = useOnboarding();

  
  // 1. 항공사 목록 상태 관리
  const [airlines, setAirlines] = useState([]);
  const [loading, setLoading] = useState(true);

  // 2. 비동기 데이터 불러오기 (useEffect 사용)
  useEffect(() => {
    async function fetchAirlines() {
      try {
        const response = await getAirlines();

        // API 응답이 { results: [...] } 형태일 경우 response.results 사용
        if (Array.isArray(response)) {
        setAirlines(response);
        } else if (response && Array.isArray(response.results)) {
          setAirlines(response.results);
        } else if (response && Array.isArray(response.data)) {
          setAirlines(response.data);
        } else {
          setAirlines([]); // 예외 시 빈 배열로 안전하게 초기화
        }
      } catch (error) {
        console.error("항공사 목록 조회 실패:", error);
      } finally {
        setLoading(false);
      }
    }
    fetchAirlines();
  }, []);

  // 옵셔널 체이닝 및 Array 검사 적용)
  const selectedIataCode = Array.isArray(airlines) 
  ? airlines.find((item) => item.name_ko === data.airline)?.iata_code || ""
  : "";
  

  // 캘린더 내에서만 맴도는 임시값
  const [tempDates, setTempDates] = useState([data.startDate ? new Date(data.startDate) : null, data.endDate ? new Date(data.endDate) : null]);
  const [startDate, endDate] = tempDates;

  // 2. 캘린더 열림/닫힘 상태 직접 제어
  const [isOpen, setIsOpen] = useState(false);

  const formatDate = (dateObj) => {
    if (!dateObj) return "";
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  // 날짜 클릭 시 임시 상태만 업데이트 (바로 update() 호출 안 함)
  const handleDateChange = (dates) => {
    setTempDates(dates);
  };

  const handleCancel = () => {
    setTempDates([data.startDate ? new Date(data.startDate) : null, data.endDate ? new Date(data.endDate) : null]);
    setIsOpen(false);
  };

  // 선택 버튼 클릭 시 최종 부모 상태(update)로 반영 후 캘린더 닫기
  const handleApply = () =>{
    const [start, end] = tempDates;
    update({ startDate: formatDate(start), endDate: formatDate(end) });
    setIsOpen(false);
  };

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
        <div className="space-y-4"> 
          <div className="grid grid-cols-2 gap-3">
            <Field label="항공사">
              <select
                value={data.airline || ""}
                onChange={(event) => update({ airline: event.target.value })}
                className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              >
                <option value="" disabled>
                  {loading ? "항공사 목록 로딩 중..." : "항공사 선택"}
                </option>
                {airlines.map((airline) => (
                  <option key={airline.id || airline.iata_code} value={airline.name_ko}>
                    {airline.name_ko}
                  </option>
                ))}
              </select>
            </Field>
            {/* 편명 입력 영역 (IATA 코드가 앞에 프리픽스로 노출됨) */}
            <Field label="편명" error={errors.flightNumber}>
              <div className="flex items-center rounded-xl border border-slate-200 bg-white px-3 py-2.5 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
                {selectedIataCode && (
                  <span className="mr-1.5 font-bold text-slate-600">
                    {selectedIataCode}
                  </span>
                )}
              </div>
              <TextInput
                value={data.flightNumber}
                error={errors.flightNumber}
                onChange={(event) => update({ flightNumber: event.target.value })}
                placeholder="001"
              />
            </Field>
          </div>
          <Field label="출국 일시" error={errors.departureAt}>
            <TextInput
              type="datetime-local"
              value={data.departureAt}
              error={errors.departureAt}
              onChange={(event) => update({ departureAt: event.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="귀국 편명">
              <TextInput
                value={data.returnFlightNumber}
                onChange={(event) => update({ returnFlightNumber: event.target.value })}
                placeholder="KE002"
              />
            </Field>
            <Field label="귀국 일시" error={errors.returnArrivalAt}>
              <TextInput
                type="datetime-local"
                value={data.returnArrivalAt}
                error={errors.returnArrivalAt}
                min={data.departureAt || undefined}
                onChange={(event) => update({ returnArrivalAt: event.target.value })}
              />
            </Field>
          </div>
        </div>
      ) : (
        // <div className="grid">
        <div className="space-y-5">
          <div className="relative w-full">
            {/* 인풋 영역 (클릭 시 캘린더 팝업 열기) */}
            <button
              type="button"
              onClick={() => setIsOpen(!isOpen)}
              className={`${INPUT_CLASS} text-left ${
                !data.startDate || !data.endDate ? "!text-slate-400" : "!text-slate-900"
              }`}
              >
                {data.startDate && data.endDate
                  ? `${data.startDate} ~ ${data.endDate}`
                  : "여행 기간을 선택하세요"}
            </button>
            {isOpen && (  
              <div className="absolute z-10 mt-1 w-full rounded-2xl border border-slate-100 bg-white p-4 shadow-xl">
                <DatePicker
                  selectsRange={true}
                  inline
                  minDate={new Date()}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                  dateFormat="yyyy년 MM월 dd일"
                  startDate={startDate}
                  endDate={endDate}
                  onChange={handleDateChange}
                />
                {/* 하단 확인/적용 버튼 영역 */}
                <div className="mt-4 flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="rounded-lg px-3 py-2 text-xs font-medium text-slate-500 hover:bg-slate-50"
                  >취소</button>
                  <button
                    type="button"
                    onClick={handleApply}
                    disabled={!startDate || !endDate} //시작일과 종료일이 모두 지정되어야 활성화
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:bg-slate-200 disabled:cursor-not-allowed"
                    >선택</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Step 3 — 숙소 (Skip 가능)
 * ------------------------------------------------------------------ */

function StepHotel() {
  const { data, update, errors, tripRange } = useOnboarding();

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-bold text-slate-900">숙소를 등록할까요?</h2>
        <p className="mt-1 text-sm text-slate-500">
          숙소를 기준으로 매일의 동선을 최적화해요. 나중에 추가해도 괜찮아요.
        </p>
      </header>

      <fieldset disabled={data.skipHotel} className="space-y-4 disabled:opacity-40">
        <Field label="숙소명" error={errors.hotelName}>
          <TextInput
            value={data.hotelName}
            error={errors.hotelName}
            onChange={(event) => update({ hotelName: event.target.value })}
            placeholder="예) 신주쿠 그랜비아 호텔"
          />
        </Field>
        <Field label="주소" error={errors.hotelAddress}>
          <TextInput
            value={data.hotelAddress}
            error={errors.hotelAddress}
            onChange={(event) => update({ hotelAddress: event.target.value })}
            placeholder="도쿄도 신주쿠구 ..."
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="체크인" error={errors.checkIn}>
            <TextInput
              type="date"
              value={data.checkIn}
              error={errors.checkIn}
              min={tripRange.start || undefined}
              max={tripRange.end || undefined}
              onChange={(event) => update({ checkIn: event.target.value })}
            />
          </Field>
          <Field label="체크아웃" hint="미정이면 비워두세요" error={errors.checkOut}>
            <TextInput
              type="date"
              value={data.checkOut}
              error={errors.checkOut}
              min={data.checkIn || tripRange.start || undefined}
              max={tripRange.end || undefined}
              onChange={(event) => update({ checkOut: event.target.value })}
            />
          </Field>
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
    // Step 2를 마치면 체크인/체크아웃 기본값을 여행 기간으로 채워둔다.
    if (step === 2) {
      update({
        checkIn: data.checkIn || tripRange.start,
        checkOut: data.checkOut || tripRange.end,
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
