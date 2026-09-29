import { useMemo } from "react";
import type { Trip } from "../types/api";
import { tripColor, tripShortTitle } from "../trips/tripUtils";
import { WEEKDAYS_KO, diffDays, monthWeeks, toISODate } from "../utils/date";

/** 한 주에 보여줄 여행 막대 줄 수. 넘치면 날짜 칸에 "+n"으로 표시한다. */
const MAX_LANES = 3;

/** 한 주 안에 그려지는 여행 막대 조각 */
interface WeekSegment {
  trip: Trip;
  /** 주 안의 시작·끝 요일 칸 (0=일 ~ 6=토) */
  startCol: number;
  endCol: number;
  /** 여행 시작·끝이 이 주에 있는지(막대 끝을 둥글게) */
  startsHere: boolean;
  endsHere: boolean;
  lane: number;
}

/** 주에 걸친 여행을 칸 위치로 바꾸고, 겹치지 않게 줄(lane)을 나눈다. */
function weekSegments(trips: Trip[], weekStart: string, weekEnd: string): WeekSegment[] {
  const overlapping = trips
    .filter((trip) => trip.start_date <= weekEnd && trip.end_date >= weekStart)
    // 먼저 시작하고, 같으면 긴 여행을 윗줄에 둔다.
    .sort(
      (a, b) =>
        a.start_date.localeCompare(b.start_date) || b.end_date.localeCompare(a.end_date),
    );

  const laneEnds: number[] = [];
  return overlapping.map((trip) => {
    const startCol = Math.max(0, diffDays(weekStart, trip.start_date));
    const endCol = Math.min(6, diffDays(weekStart, trip.end_date));
    let lane = laneEnds.findIndex((end) => end < startCol);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = endCol;
    return {
      trip,
      startCol,
      endCol,
      startsHere: trip.start_date >= weekStart,
      endsHere: trip.end_date <= weekEnd,
      lane,
    };
  });
}

interface TripCalendarProps {
  trips: Trip[];
  /** 보고 있는 달 (1일) */
  month: Date;
  onMonthChange: (month: Date) => void;
  today: string;
  selectedTripId: number | null;
  selectedDate: string | null;
  onSelectTrip: (trip: Trip) => void;
  onSelectDate: (date: string) => void;
}

/**
 * 홈 대형 캘린더. 여행 기간을 여행별 색 막대(제목 뱃지)로 표시한다.
 * 막대를 누르면 여행을, 날짜를 누르면 그 날짜를 선택한다(선택 내용은 아래 요약 카드에 나온다).
 */
export default function TripCalendar({
  trips,
  month,
  onMonthChange,
  today,
  selectedTripId,
  selectedDate,
  onSelectTrip,
  onSelectDate,
}: TripCalendarProps) {
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const weeks = useMemo(() => monthWeeks(year, monthIndex), [year, monthIndex]);

  const moveMonth = (offset: number) => onMonthChange(new Date(year, monthIndex + offset, 1));

  return (
    <section
      aria-label="여행 캘린더"
      className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5 sm:py-4">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => moveMonth(-1)}
            aria-label="이전 달"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <i className="fas fa-chevron-left text-sm" aria-hidden="true" />
          </button>
          <h2 className="min-w-[8.5rem] text-center text-lg font-bold text-slate-900 tabular-nums">
            {year}년 {monthIndex + 1}월
          </h2>
          <button
            type="button"
            onClick={() => moveMonth(1)}
            aria-label="다음 달"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            <i className="fas fa-chevron-right text-sm" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={() => {
            const now = new Date();
            onMonthChange(new Date(now.getFullYear(), now.getMonth(), 1));
            onSelectDate(today);
          }}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
        >
          오늘
        </button>
      </div>

      <div className="grid grid-cols-7 border-t border-slate-100 bg-slate-50/60 text-center text-xs font-medium">
        {WEEKDAYS_KO.map((day, index) => (
          <span
            key={day}
            className={`py-2 ${
              index === 0 ? "text-rose-400" : index === 6 ? "text-indigo-400" : "text-slate-400"
            }`}
          >
            {day}
          </span>
        ))}
      </div>

      {weeks.map((week) => {
        const weekStart = toISODate(week[0]);
        const weekEnd = toISODate(week[6]);
        const segments = weekSegments(trips, weekStart, weekEnd);
        const visible = segments.filter((segment) => segment.lane < MAX_LANES);
        // 날짜 칸별로 넘친 여행 수
        const hiddenByCol = Array.from(
          { length: 7 },
          (_, col) =>
            segments.filter(
              (segment) =>
                segment.lane >= MAX_LANES && segment.startCol <= col && col <= segment.endCol,
            ).length,
        );

        return (
          <div key={weekStart} className="relative grid grid-cols-7 border-t border-slate-100">
            {week.map((date, col) => {
              const iso = toISODate(date);
              const inMonth = date.getMonth() === monthIndex;
              const isToday = iso === today;
              const isSelected = iso === selectedDate;
              return (
                <button
                  key={iso}
                  type="button"
                  onClick={() => onSelectDate(iso)}
                  aria-label={`${date.getMonth() + 1}월 ${date.getDate()}일`}
                  aria-pressed={isSelected}
                  className={`relative flex min-h-[6.75rem] flex-col items-start border-l border-slate-100 p-1.5 text-left transition-colors first:border-l-0 sm:min-h-[7.75rem] sm:p-2 ${
                    isSelected ? "bg-indigo-50/70" : "hover:bg-slate-50"
                  }`}
                >
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium tabular-nums sm:text-sm ${
                      isToday
                        ? "bg-indigo-600 font-semibold text-white"
                        : !inMonth
                          ? "text-slate-300"
                          : col === 0
                            ? "text-rose-500"
                            : col === 6
                              ? "text-indigo-500"
                              : "text-slate-700"
                    }`}
                  >
                    {date.getDate()}
                  </span>
                  {hiddenByCol[col] > 0 && (
                    <span className="absolute right-1.5 top-2 text-[10px] font-medium text-slate-400 sm:right-2 sm:top-2.5 sm:text-xs">
                      +{hiddenByCol[col]}
                    </span>
                  )}
                </button>
              );
            })}

            {/* 여행 기간 막대. 날짜 칸 위에 겹쳐 그리고, 막대만 클릭을 받는다. */}
            <div
              className="pointer-events-none absolute inset-x-0 top-8 grid grid-cols-7 gap-y-1 sm:top-10"
              style={{ gridAutoRows: "1.25rem" }}
            >
              {visible.map((segment) => {
                const color = tripColor(segment.trip);
                const selected = segment.trip.id === selectedTripId;
                return (
                  <button
                    key={segment.trip.id}
                    type="button"
                    onClick={() => onSelectTrip(segment.trip)}
                    title={`${segment.trip.destination_label} (${segment.trip.start_date} ~ ${segment.trip.end_date})`}
                    style={{
                      gridColumn: `${segment.startCol + 1} / ${segment.endCol + 2}`,
                      gridRow: segment.lane + 1,
                    }}
                    className={`pointer-events-auto truncate px-1.5 text-left text-[10px] font-semibold leading-5 transition-colors sm:text-xs ${
                      selected ? color.barSelected : color.bar
                    } ${segment.startsHere ? "ml-1 rounded-l-md" : ""} ${
                      segment.endsHere ? "mr-1 rounded-r-md" : ""
                    }`}
                  >
                    {/* 이어지는 막대에는 제목을 반복하지 않고 주가 바뀔 때만 다시 쓴다. */}
                    {segment.startsHere || segment.startCol === 0 ? tripShortTitle(segment.trip) : ""}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
