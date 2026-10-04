import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

/**
 * 버튼 + 팝오버 선택기 공통 부품. 온보딩(날짜·항공권 일시)과 여행 상세(장소 시간)가 같은 모양을 쓴다.
 */

const pad2 = (value: number) => String(value).padStart(2, "0");

const HOURS = Array.from({ length: 24 }, (_, index) => pad2(index));
/** 오전/오후 표기의 시: 12, 01 ~ 11 */
const HOURS_12 = ["12", ...Array.from({ length: 11 }, (_, index) => pad2(index + 1))];
const MINUTES = Array.from({ length: 12 }, (_, index) => pad2(index * 5));
const PERIODS = ["오전", "오후"] as const;
type Period = (typeof PERIODS)[number];

export const POPOVER_CLASS =
  "pin-calendar absolute left-0 z-30 mt-1.5 rounded-2xl border border-slate-100 bg-white p-3 shadow-xl";

/** "19:05" -> "오후 7:05" */
export function formatMeridiemTime(value: string): string {
  const [hour, minute] = value.split(":");
  if (!hour || !minute) return "";
  const h = Number(hour);
  return `${h < 12 ? "오전" : "오후"} ${h % 12 === 0 ? 12 : h % 12}:${minute}`;
}

/** 팝오버 바깥을 누르면 닫는다. */
export function useOutsideClose(ref: RefObject<HTMLElement>, onClose: () => void) {
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

export function PickerButton({
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

export type TimePart = "period" | "hour" | "minute";

/** 시·분(오전/오후 표기면 오전·오후까지)을 각각 세로 목록으로 고른다. */
interface TimeColumnsProps {
  /** "00"~"23", 아직 고르지 않았으면 빈 문자열 */
  hour: string;
  /** "00"~"55"(5분 단위), 아직 고르지 않았으면 빈 문자열 */
  minute: string;
  /** part는 이번에 누른 목록. hour는 언제나 24시 표기로 돌려준다. */
  onPick: (hour: string, minute: string, part: TimePart) => void;
  /** 오전/오후 + 12시 표기 */
  meridiem?: boolean;
}

export function TimeColumns({ hour, minute, onPick, meridiem = false }: TimeColumnsProps) {
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
    ref?: RefObject<HTMLButtonElement>,
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

  const header = (labels: string[]) => (
    <div className="mb-1 flex gap-1 px-1 text-center text-[11px] font-medium text-slate-400">
      {labels.flatMap((label, index) => [
        ...(index > 0 ? [<span key={`gap-${label}`} className="w-px" />] : []),
        <span key={label} className="w-16">
          {label}
        </span>,
      ])}
    </div>
  );

  const minuteColumn = (
    <div ref={minuteList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
      {MINUTES.map((item) => cell(item, item === minute, () => onPick(hour || "09", item, "minute"), minuteItem))}
    </div>
  );

  if (!meridiem) {
    return (
      <div>
        {header(["시", "분"])}
        <div className="flex gap-1">
          <div ref={hourList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
            {HOURS.map((item) => cell(item, item === hour, () => onPick(item, minute || "00", "hour"), hourItem))}
          </div>
          <div className="w-px bg-slate-100" />
          {minuteColumn}
        </div>
      </div>
    );
  }

  // 오전/오후 표기: 24시 값 <-> (오전·오후, 12·01~11)
  const period: Period | "" = hour ? (Number(hour) < 12 ? "오전" : "오후") : "";
  const hour12 = hour ? (Number(hour) % 12 === 0 ? "12" : pad2(Number(hour) % 12)) : "";
  const to24 = (nextPeriod: Period, nextHour12: string) =>
    pad2((Number(nextHour12) % 12) + (nextPeriod === "오후" ? 12 : 0));

  return (
    <div>
      {header(["오전/오후", "시", "분"])}
      <div className="flex gap-1">
        <div className="w-16 space-y-0.5 pr-1">
          {PERIODS.map((item) =>
            cell(item, item === period, () => onPick(to24(item, hour12 || "09"), minute || "00", "period")),
          )}
        </div>
        <div className="w-px bg-slate-100" />
        <div ref={hourList} className="max-h-48 w-16 space-y-0.5 overflow-y-auto pr-1">
          {HOURS_12.map((item) =>
            cell(
              item,
              item === hour12,
              () => onPick(to24(period || "오전", item), minute || "00", "hour"),
              hourItem,
            ),
          )}
        </div>
        <div className="w-px bg-slate-100" />
        {minuteColumn}
      </div>
    </div>
  );
}

/**
 * 시간만 고르는 칸 (오전/오후). 항공권 일시와 같은 버튼 + 팝오버 모양이고, 분까지 고르면 닫는다.
 * 값은 "HH:MM"(24시), 비어 있으면 빈 문자열. optional이면 '시간 지우기'를 보여준다.
 */
interface TimeFieldProps {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  optional?: boolean;
}

export function TimeField({ value, onChange, ariaLabel, placeholder = "시간 선택", optional = false }: TimeFieldProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useOutsideClose(wrapperRef, close);
  const [hour = "", minute = ""] = value ? value.split(":") : [];

  const pick = (nextHour: string, nextMinute: string, part: TimePart) => {
    onChange(`${nextHour}:${nextMinute}`);
    if (part === "minute") setOpen(false);
  };

  return (
    <div ref={wrapperRef} className="relative">
      <PickerButton
        icon="far fa-clock"
        open={open}
        placeholder={placeholder}
        ariaLabel={ariaLabel}
        onClick={() => setOpen((previous) => !previous)}
      >
        {value ? formatMeridiemTime(value) : ""}
      </PickerButton>
      {open && (
        <div className={`${POPOVER_CLASS} left-auto right-0`}>
          <TimeColumns hour={hour} minute={minute} onPick={pick} meridiem />
          {optional && value && (
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              className="mt-2 w-full rounded-lg py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-50 hover:text-rose-500"
            >
              시간 지우기
            </button>
          )}
        </div>
      )}
    </div>
  );
}
