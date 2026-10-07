import type { ReactDatePickerCustomHeaderProps } from "react-datepicker";

/**
 * react-datepicker 달력 공통: 날짜 문자열 변환, 한국어 날짜 표기, 요일·월 헤더.
 * 새 여행 만들기와 여행 상세(장소 직접 추가)가 같은 달력 모양을 쓴다.
 */

const pad2 = (value: number) => String(value).padStart(2, "0");

/** Date -> "2026-10-01" */
export const toISODate = (date: Date | null) =>
  date ? `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` : "";

/** "2026-10-01" -> Date (타임존 밀림을 피하려고 로컬 자정으로 만든다) */
export const fromISODate = (value: string | undefined): Date | null =>
  value ? new Date(`${value}T00:00:00`) : null;

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-10-01" -> "2026년 10월 1일 (목)" */
export const formatKoreanDate = (value: string) => {
  const date = fromISODate(value);
  if (!date) return "";
  return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 (${
    WEEKDAYS[date.getDay()]
  })`;
};

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
export const formatWeekDay = (name: string) => WEEKDAY_KO[name] ?? name.slice(0, 1);

/** 달력 상단의 ‹ 2026년 10월 › 헤더. */
export function CalendarHeader({ date, decreaseMonth, increaseMonth }: ReactDatePickerCustomHeaderProps) {
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
