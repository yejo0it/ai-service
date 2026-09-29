import { useMemo } from "react";
import type { Trip } from "../types/api";
import { tripColor, tripShortTitle, type TripColor } from "../trips/tripUtils";
import { WEEKDAYS_KO, diffDays, monthWeeks, toISODate } from "../utils/date";

/**
 * 한 번에 보여줄 여행 줄 수. 0번 줄 여행은 날짜 줄의 기간 띠로, 1번 줄부터는 아래 막대로 그린다.
 * 넘치면 날짜 옆에 "+n"으로 표시한다.
 */
const MAX_LANES = 3;

/**
 * 여행마다 줄 번호를 정한다. 줄은 달력 화면 전체에서 고정이라 주가 바뀌어도 같은 줄에 그려지고,
 * 같은 줄의 여행끼리는 기간이 겹치지 않는다(0번 줄이 날짜 띠를 겹침 없이 차지한다).
 */
function assignLanes(trips: Trip[]): Map<number, number> {
  const sorted = [...trips].sort(
    (a, b) => a.start_date.localeCompare(b.start_date) || b.end_date.localeCompare(a.end_date),
  );
  const laneEnds: string[] = [];
  const lanes = new Map<number, number>();
  sorted.forEach((trip) => {
    let lane = laneEnds.findIndex((end) => end < trip.start_date);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = trip.end_date;
    lanes.set(trip.id, lane);
  });
  return lanes;
}

/** 한 주 안에 그려지는 여행 조각 */
interface WeekSegment {
  trip: Trip;
  color: TripColor;
  /** 주 안의 시작·끝 요일 칸 (0=일 ~ 6=토) */
  startCol: number;
  endCol: number;
  /** 여행 시작·끝이 이 주에 있는지 */
  startsHere: boolean;
  endsHere: boolean;
  lane: number;
}

function weekSegments(
  trips: Trip[],
  lanes: Map<number, number>,
  weekStart: string,
  weekEnd: string,
): WeekSegment[] {
  return trips
    .filter((trip) => trip.start_date <= weekEnd && trip.end_date >= weekStart)
    .map((trip) => ({
      trip,
      color: tripColor(trip),
      startCol: Math.max(0, diffDays(weekStart, trip.start_date)),
      endCol: Math.min(6, diffDays(weekStart, trip.end_date)),
      startsHere: trip.start_date >= weekStart,
      endsHere: trip.end_date <= weekEnd,
      lane: lanes.get(trip.id) ?? 0,
    }));
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
 * 홈 대형 캘린더.
 * 여행 기간은 날짜 줄에 연한 띠로 잇고, 시작일·종료일은 채운 원, 기간 안 날짜는 굵은 색 숫자로 표시한다.
 * 띠 아래에 여행 제목 뱃지를 달고, 같은 날 겹치는 다른 여행은 그 아래 막대로 그린다.
 * 날짜를 누르면 날짜를, 뱃지·막대를 누르면 여행을 선택한다(선택 내용은 아래 요약 카드에 나온다).
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

  // 이 화면(6주)에 걸친 여행만 줄을 나눈다.
  const visibleStart = toISODate(weeks[0][0]);
  const visibleEnd = toISODate(weeks[5][6]);
  const visibleTrips = useMemo(
    () => trips.filter((trip) => trip.start_date <= visibleEnd && trip.end_date >= visibleStart),
    [trips, visibleStart, visibleEnd],
  );
  const lanes = useMemo(() => assignLanes(visibleTrips), [visibleTrips]);

  const moveMonth = (offset: number) => onMonthChange(new Date(year, monthIndex + offset, 1));

  return (
    <section
      aria-label="여행 캘린더"
      className="overflow-hidden rounded-2xl border border-slate-200 bg-white px-2 pb-3 shadow-sm sm:px-4"
    >
      <div className="flex items-center justify-between gap-3 px-2 py-3 sm:py-4">
        <button
          type="button"
          onClick={() => moveMonth(-1)}
          aria-label="이전 달"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
        >
          <i className="fas fa-chevron-left text-sm" aria-hidden="true" />
        </button>
        <h2 className="text-lg font-bold text-slate-900 tabular-nums">
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

      <div className="grid grid-cols-7 text-center text-xs font-semibold sm:text-sm">
        {WEEKDAYS_KO.map((day, index) => (
          <span
            key={day}
            className={`pb-2 ${index === 0 ? "text-rose-400" : index === 6 ? "text-indigo-400" : "text-slate-500"}`}
          >
            {day}
          </span>
        ))}
      </div>

      {weeks.map((week) => {
        const weekStart = toISODate(week[0]);
        const weekEnd = toISODate(week[6]);
        const segments = weekSegments(visibleTrips, lanes, weekStart, weekEnd);
        const bandSegments = segments.filter((segment) => segment.lane === 0);
        const barSegments = segments.filter((segment) => segment.lane > 0 && segment.lane < MAX_LANES);
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
          <div key={weekStart} className="relative grid grid-cols-7">
            {week.map((date, col) => {
              const iso = toISODate(date);
              const inMonth = date.getMonth() === monthIndex;
              const isToday = iso === today;
              const isSelected = iso === selectedDate;
              const band = bandSegments.find((segment) => segment.startCol <= col && col <= segment.endCol);
              const isCap = band && (iso === band.trip.start_date || iso === band.trip.end_date);
              const bandSelected = band?.trip.id === selectedTripId;

              let numberClass = !inMonth
                ? "text-slate-300"
                : col === 0
                  ? "text-rose-500"
                  : col === 6
                    ? "text-indigo-500"
                    : "text-slate-700";
              if (band) numberClass = isCap ? `${band.color.cap} font-bold` : `${band.color.text} font-bold`;
              if (!inMonth && band && !isCap) numberClass = `${band.color.text} font-semibold opacity-50`;

              return (
                <button
                  key={iso}
                  type="button"
                  onClick={() => onSelectDate(iso)}
                  aria-label={`${date.getMonth() + 1}월 ${date.getDate()}일`}
                  aria-pressed={isSelected}
                  className="group relative flex min-h-[6.5rem] flex-col items-center pt-1 sm:min-h-[7.25rem]"
                >
                  {/* 기간 띠: 시작일은 칸 가운데부터, 종료일은 칸 가운데까지. 주가 끊기는 곳은 둥글게 닫는다. */}
                  {band && (
                    <span
                      aria-hidden="true"
                      className={`absolute top-1 h-9 ${bandSelected ? band.color.bandSelected : band.color.band} ${
                        iso === band.trip.start_date ? "left-1/2" : col === 0 ? "left-1 rounded-l-full" : "left-0"
                      } ${iso === band.trip.end_date ? "right-1/2" : col === 6 ? "right-1 rounded-r-full" : "right-0"}`}
                    />
                  )}
                  <span
                    // 여행 기간 안의 날짜는 띠·원으로 이미 표시되므로 선택·오늘 테두리를 두지 않는다.
                    className={`relative flex h-9 w-9 items-center justify-center rounded-full text-sm tabular-nums transition-colors ${numberClass} ${
                      band
                        ? ""
                        : isSelected
                          ? "ring-2 ring-slate-300 ring-offset-1"
                          : isToday
                            ? "ring-2 ring-indigo-300"
                            : "group-hover:bg-slate-100"
                    }`}
                  >
                    {date.getDate()}
                  </span>
                  {hiddenByCol[col] > 0 && (
                    <span className="absolute right-0.5 top-0 text-[10px] font-medium text-slate-400 sm:text-xs">
                      +{hiddenByCol[col]}
                    </span>
                  )}
                </button>
              );
            })}

            {/* 띠 아래: 0번 줄 여행의 제목 뱃지, 1번 줄부터는 겹친 여행 막대. 이 요소들만 클릭을 받는다. */}
            <div
              className="pointer-events-none absolute inset-x-0 top-11 grid grid-cols-7 gap-y-1"
              style={{ gridAutoRows: "1.25rem" }}
            >
              {bandSegments
                .filter((segment) => segment.startsHere || segment.startCol === 0)
                .map((segment) => (
                  <div
                    key={segment.trip.id}
                    className="flex min-w-0 justify-center px-0.5"
                    style={{ gridColumn: `${segment.startCol + 1} / ${segment.endCol + 2}`, gridRow: 1 }}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectTrip(segment.trip)}
                      title={`${segment.trip.destination_label} (${segment.trip.start_date} ~ ${segment.trip.end_date})`}
                      className={`pointer-events-auto max-w-full truncate rounded-full px-2 text-[10px] font-semibold leading-5 ring-1 ring-inset transition-shadow hover:shadow-sm sm:text-xs ${
                        segment.trip.id === selectedTripId ? segment.color.barSelected : segment.color.badge
                      }`}
                    >
                      {tripShortTitle(segment.trip)}
                    </button>
                  </div>
                ))}
              {barSegments.map((segment) => (
                <button
                  key={segment.trip.id}
                  type="button"
                  onClick={() => onSelectTrip(segment.trip)}
                  title={`${segment.trip.destination_label} (${segment.trip.start_date} ~ ${segment.trip.end_date})`}
                  style={{
                    gridColumn: `${segment.startCol + 1} / ${segment.endCol + 2}`,
                    gridRow: segment.lane + 1,
                  }}
                  className={`pointer-events-auto truncate px-2 text-left text-[10px] font-semibold leading-5 sm:text-xs ${
                    segment.trip.id === selectedTripId ? segment.color.barSelected : segment.color.bar
                  } ${segment.startsHere ? "ml-1 rounded-l-full" : ""} ${segment.endsHere ? "mr-1 rounded-r-full" : ""}`}
                >
                  {segment.startsHere || segment.startCol === 0 ? tripShortTitle(segment.trip) : ""}
                </button>
              ))}
            </div>
          </div>
        );
      })}

      <div className="mt-2 flex justify-end px-2">
        <button
          type="button"
          onClick={() => {
            const now = new Date();
            onMonthChange(new Date(now.getFullYear(), now.getMonth(), 1));
            onSelectDate(today);
          }}
          className="rounded-lg border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
        >
          오늘
        </button>
      </div>
    </section>
  );
}
