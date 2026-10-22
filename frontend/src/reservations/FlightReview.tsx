import { AIRPORTS, searchAirports } from "../onboarding/airports";
import type { FlightBooking, ReservationIssue } from "../types/api";
import ReviewInput from "./ReviewInput";
import { EMPTY_SEGMENT, getByPath, issueMap, setByPath } from "./reservationUtils";

interface FlightReviewProps {
  /** 분석 직후 값(추출됨·수정함 표시의 기준) */
  original: FlightBooking;
  value: FlightBooking;
  errors: ReservationIssue[];
  warnings: ReservationIssue[];
  onChange: (value: FlightBooking) => void;
}

const upper = (text: string) => text.toUpperCase();

/** 공항 코드 칸 아래 안내: PinRoute 공항 목록과 맞춰 보고, 코드가 없으면 이름으로 후보를 보여 준다. */
function AirportHint({ code, name, onPick }: { code: string | null; name: string | null; onPick: (code: string) => void }) {
  if (code) {
    const found = AIRPORTS.find((item) => item.code === code);
    return found ? (
      <p className="mt-1 text-xs text-slate-400">{found.name}</p>
    ) : /^[A-Z]{3}$/.test(code) ? (
      <p className="mt-1 text-xs text-amber-600">PinRoute 공항 목록에 없는 코드예요. 맞는지 확인해 주세요.</p>
    ) : null;
  }
  const candidates = name ? searchAirports(name, 3) : [];
  if (candidates.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
      <span>공항을 골라 주세요:</span>
      {candidates.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onPick(item.code)}
          className="rounded-full border border-slate-200 px-2 py-0.5 hover:border-indigo-300 hover:text-indigo-600"
        >
          {item.name} ({item.code})
        </button>
      ))}
    </div>
  );
}

const DIRECTION_LABEL = { "": "구분 안 함", outbound: "가는 편", return: "오는 편" } as const;

/**
 * 항공권 확인·수정 화면: 예약마다 비행 구간(왕복·경유·다구간)을 구간별로 보여 주고 고치게 한다.
 * 추출한 값·고친 값·확인 필요한 값을 구분해 표시하며, 한 칸을 고쳐도 다른 칸을 바꾸지 않는다.
 */
export default function FlightReview({ original, value, errors, warnings, onChange }: FlightReviewProps) {
  const errorOf = issueMap(errors);
  const warningOf = issueMap(warnings);
  const update = (path: string, next: string | null) => onChange(setByPath(value, path, next));

  const addSegment = (index: number) =>
    onChange(
      setByPath(value, `itineraries.${index}.segments`, [...value.itineraries[index].segments, { ...EMPTY_SEGMENT }]),
    );
  const removeSegment = (index: number, number: number) =>
    onChange(
      setByPath(
        value,
        `itineraries.${index}.segments`,
        value.itineraries[index].segments.filter((_, i) => i !== number),
      ),
    );

  const input = (base: string, field: string, label: string, extra: Partial<React.ComponentProps<typeof ReviewInput>> = {}) => (
    <ReviewInput
      key={field}
      id={`${base}-${field}`}
      label={label}
      path={`${base}.${field}`}
      original={original}
      current={value}
      error={errorOf.get(`${base}.${field}`)}
      warning={warningOf.get(`${base}.${field}`)}
      onChange={update}
      {...extra}
    />
  );

  return (
    <div className="space-y-6">
      {errorOf.get("itineraries") && <p className="text-sm text-rose-600">{errorOf.get("itineraries")}</p>}
      {value.itineraries.map((itinerary, index) => (
        <section key={index} aria-label={`항공권 예약 ${index + 1}`} className="space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">항공권 예약 {index + 1}</h3>
            {itinerary.status && (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                {itinerary.status}
              </span>
            )}
          </div>
          {errorOf.get(`itineraries.${index}.segments`) && (
            <p className="text-sm text-rose-600">{errorOf.get(`itineraries.${index}.segments`)}</p>
          )}
          {itinerary.segments.map((segment, number) => {
            const base = `itineraries.${index}.segments.${number}`;
            const direction = (getByPath(value, `${base}.direction`) as string | null) ?? "";
            return (
              <div key={number} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-slate-800">구간 {number + 1}</h4>
                  <div className="flex items-center gap-2">
                    <label htmlFor={`${base}-direction`} className="sr-only">
                      가는 편·오는 편
                    </label>
                    <select
                      id={`${base}-direction`}
                      value={direction}
                      onChange={(event) => update(`${base}.direction`, event.target.value || null)}
                      className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:border-indigo-400 focus:outline-none"
                    >
                      {Object.entries(DIRECTION_LABEL).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => removeSegment(index, number)}
                      className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-rose-50 hover:text-rose-500"
                      aria-label={`구간 ${number + 1} 삭제`}
                    >
                      삭제
                    </button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {input(base, "airline_name", "항공사", { optional: true })}
                  {input(base, "flight_number", "항공편명", { placeholder: "KE703", format: upper, maxLength: 12 })}

                  <div className="space-y-3">
                    {input(base, "departure_airport_code", "출발 공항 코드", { placeholder: "ICN", format: upper, maxLength: 3,
                      hint: (
                        <AirportHint
                          code={segment.departure_airport_code}
                          name={segment.departure_airport_name}
                          onPick={(code) => update(`${base}.departure_airport_code`, code)}
                        />
                      ) })}
                    {input(base, "departure_airport_name", "출발 공항 이름", { optional: true })}
                  </div>
                  <div className="space-y-3">
                    {input(base, "arrival_airport_code", "도착 공항 코드", { placeholder: "NRT", format: upper, maxLength: 3,
                      hint: (
                        <AirportHint
                          code={segment.arrival_airport_code}
                          name={segment.arrival_airport_name}
                          onPick={(code) => update(`${base}.arrival_airport_code`, code)}
                        />
                      ) })}
                    {input(base, "arrival_airport_name", "도착 공항 이름", { optional: true })}
                  </div>

                  {input(base, "departure_date", "출발 날짜 (현지)", { type: "date" })}
                  {input(base, "departure_time", "출발 시각 (현지)", { type: "time" })}
                  {input(base, "arrival_date", "도착 날짜 (현지)", { type: "date" })}
                  {input(base, "arrival_time", "도착 시각 (현지)", { type: "time" })}
                </div>

                {segment.notes.length > 0 && (
                  <ul className="mt-3 space-y-0.5 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">
                    {segment.notes.map((note, i) => (
                      <li key={i}>확인 필요: {note}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
          <button
            type="button"
            onClick={() => addSegment(index)}
            className="rounded-xl border border-dashed border-slate-300 px-3 py-2 text-sm font-medium text-slate-500 hover:border-indigo-300 hover:text-indigo-600"
          >
            + 구간 추가
          </button>
        </section>
      ))}
    </div>
  );
}
