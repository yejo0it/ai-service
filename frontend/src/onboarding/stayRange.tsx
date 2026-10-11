import { useCallback, useRef, useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { CalendarHeader, formatKoreanDate, formatWeekDay, fromISODate, toISODate } from "../components/calendar";
import { POPOVER_CLASS, PickerButton, useOutsideClose } from "../components/pickers";
import type { Stay } from "../types/onboarding";

/**
 * 숙박 기간(체크인~체크아웃) 선택. 새 여행 만들기의 숙소 단계와 여행 상세의 숙소 직접 추가가 함께 쓴다.
 */

/** "2026-10-01" -> "10월 1일 (목)" */
export const formatShortDate = (value: string) => formatKoreanDate(value).replace(/^\d+년 /, "");

/** 다른 숙소가 이미 묵는 밤인지. 체크아웃 날은 비어 있으므로 다음 숙소의 체크인으로 쓸 수 있다. */
export const isNightTaken = (date: string, stays: Stay[]) =>
  stays.some((stay) => stay.check_in <= date && date < stay.check_out);

/** start에 체크인했을 때 가장 늦은 체크아웃 날. 뒤 숙소의 체크인 날 또는 여행 종료일이다. */
export const stayLimitFrom = (start: string, stays: Stay[], end: string) =>
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
  /** 작은 버튼 (여행 상세 직접 추가) */
  compact?: boolean;
}

export function StayRangeField({
  checkIn,
  checkOut,
  min,
  max,
  otherStays,
  error,
  ariaLabel,
  onChange,
  compact = false,
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
        compact={compact}
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
