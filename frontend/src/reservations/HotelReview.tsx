import type { HotelBooking, ReservationIssue } from "../types/api";
import ReviewInput from "./ReviewInput";
import { EMPTY_STAY, issueMap, setByPath } from "./reservationUtils";

interface HotelReviewProps {
  original: HotelBooking;
  value: HotelBooking;
  errors: ReservationIssue[];
  warnings: ReservationIssue[];
  onChange: (value: HotelBooking) => void;
}

/**
 * 숙소 확인·수정 화면: 숙소 예약마다 이름·주소·체크인/체크아웃 날짜·시각을 보여 주고 고치게 한다.
 * 체크인·체크아웃 시각은 문서에 있을 때만 채워지며, 비어 있어도 괜찮은 선택 항목이다.
 */
export default function HotelReview({ original, value, errors, warnings, onChange }: HotelReviewProps) {
  const errorOf = issueMap(errors);
  const warningOf = issueMap(warnings);
  const update = (path: string, next: string | null) => onChange(setByPath(value, path, next));

  const input = (
    index: number,
    field: string,
    label: string,
    extra: Partial<React.ComponentProps<typeof ReviewInput>> = {},
  ) => {
    const path = `stays.${index}.${field}`;
    return (
      <ReviewInput
        id={path}
        label={label}
        path={path}
        original={original}
        current={value}
        error={errorOf.get(path)}
        warning={warningOf.get(path)}
        onChange={update}
        {...extra}
      />
    );
  };

  return (
    <div className="space-y-4">
      {errorOf.get("stays") && <p className="text-sm text-rose-600">{errorOf.get("stays")}</p>}
      {value.stays.map((stay, index) => (
        <section key={index} aria-label={`숙소 예약 ${index + 1}`} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">숙소 예약 {index + 1}</h3>
              {stay.status && (
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">{stay.status}</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => onChange(setByPath(value, "stays", value.stays.filter((_, i) => i !== index)))}
              aria-label={`숙소 예약 ${index + 1} 삭제`}
              className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-rose-50 hover:text-rose-500"
            >
              삭제
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {input(index, "name", "숙소 이름", { className: "sm:col-span-2", maxLength: 150 })}
            {input(index, "address", "주소", { className: "sm:col-span-2", optional: true, maxLength: 255 })}
            {input(index, "check_in_date", "체크인 날짜", { type: "date" })}
            {input(index, "check_in_time", "체크인 시각", { type: "time", optional: true })}
            {input(index, "check_out_date", "체크아웃 날짜", { type: "date" })}
            {input(index, "check_out_time", "체크아웃 시각", { type: "time", optional: true })}
          </div>
          {stay.notes.length > 0 && (
            <ul className="mt-3 space-y-0.5 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">
              {stay.notes.map((note, i) => (
                <li key={i}>확인 필요: {note}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
      <button
        type="button"
        onClick={() => onChange(setByPath(value, "stays", [...value.stays, { ...EMPTY_STAY }]))}
        className="rounded-xl border border-dashed border-slate-300 px-3 py-2 text-sm font-medium text-slate-500 hover:border-indigo-300 hover:text-indigo-600"
      >
        + 숙소 추가
      </button>
    </div>
  );
}
