import { Link } from "react-router-dom";
import { ROUTES } from "../routes";
import { dDayLabel, tripStatus } from "../trips/tripUtils";
import type { Trip } from "../types/api";
import { diffDays, formatMonthDay, formatShortDot } from "../utils/date";

const CARD_CLASS = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

interface DDayCardProps {
  /** 진행 중이거나 가장 가까운 다가오는 여행. 없으면 빈 상태를 보여준다. */
  trip: Trip | null;
  today: string;
  onShowTrip: (trip: Trip) => void;
}

/** D-Day 카운트다운: 가장 가까운 여행과 남은 날 */
export function DDayCard({ trip, today, onShowTrip }: DDayCardProps) {
  if (!trip) {
    return (
      <section aria-label="다가오는 여행" className={`${CARD_CLASS} text-center`}>
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
          <i className="far fa-calendar-plus text-lg" aria-hidden="true" />
        </span>
        <p className="mt-3 font-semibold text-slate-800">등록된 여행이 없습니다</p>
        <p className="mt-1 text-sm text-slate-500">가고 싶은 도시와 날짜만 정하면 동선을 짜 드려요.</p>
        <Link
          to={ROUTES.ONBOARDING}
          className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
        >
          <i className="fas fa-plus text-xs" aria-hidden="true" />새 여행 만들기
        </Link>
      </section>
    );
  }

  const ongoing = tripStatus(trip, today) === "ongoing";
  return (
    <section
      aria-label="다가오는 여행"
      className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 p-5 text-white shadow-sm"
    >
      <p className="text-xs font-medium text-indigo-100">{ongoing ? "지금 여행 중" : "다가오는 여행"}</p>
      <div className="mt-2 flex items-end justify-between gap-3">
        <h2 className="min-w-0 truncate text-lg font-bold">{trip.destination_label} 여행</h2>
        {/* 여행 중이면 "여행 중"을 반복하지 않고 며칠째인지 보여준다. */}
        <span className="shrink-0 text-3xl font-extrabold tracking-tight tabular-nums">
          {ongoing ? `${diffDays(trip.start_date, today) + 1}일차` : dDayLabel(trip, today)}
        </span>
      </div>
      <p className="mt-1 text-sm text-indigo-100">
        {formatMonthDay(trip.start_date)} ~ {formatMonthDay(trip.end_date)} · {trip.nights}박
      </p>
      <button
        type="button"
        onClick={() => onShowTrip(trip)}
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/25"
      >
        캘린더에서 보기
        <i className="fas fa-arrow-right text-xs" aria-hidden="true" />
      </button>
    </section>
  );
}

interface RouteTimelineProps {
  trip: Trip | null;
}

/** 여행 경로 요약: 출발 → 여행지들 → 귀국을 세로 타임라인 노드로 */
export function RouteTimeline({ trip }: RouteTimelineProps) {
  if (!trip) return null;
  const cities = trip.destinations.filter((dest) => dest.city);
  const nodes = [
    { key: "start", label: "출발", sub: formatShortDot(trip.start_date), tone: "edge" as const },
    ...cities.map((dest, index) => ({
      key: `${dest.city}-${index}`,
      label: dest.city,
      sub: "",
      tone: "city" as const,
    })),
    { key: "end", label: "귀국", sub: formatShortDot(trip.end_date), tone: "edge" as const },
  ];

  return (
    <section aria-label="여행 경로" className={CARD_CLASS}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-800">여행 경로</h2>
        <span className="text-xs text-slate-400">{cities.length}개 도시</span>
      </div>
      <ol className="mt-4">
        {nodes.map((node, index) => (
          <li key={node.key} className="flex gap-3">
            {/* 노드와 이어지는 선. 마지막 노드 아래로는 선이 없다. */}
            <div className="flex w-5 flex-col items-center" aria-hidden="true">
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] ${
                  node.tone === "city"
                    ? "bg-indigo-500 text-white"
                    : "border border-slate-300 bg-white text-slate-400"
                }`}
              >
                <i
                  className={`fas ${node.tone === "city" ? "fa-map-pin" : node.key === "start" ? "fa-plane-departure" : "fa-plane-arrival"}`}
                />
              </span>
              {index < nodes.length - 1 && <span className="w-px flex-1 bg-indigo-100" />}
            </div>
            <div className={`flex min-w-0 flex-1 items-baseline justify-between gap-2 ${index < nodes.length - 1 ? "pb-4" : ""}`}>
              <span
                className={`truncate text-sm ${node.tone === "city" ? "font-semibold text-slate-800" : "text-slate-500"}`}
              >
                {node.label}
              </span>
              {node.sub && <span className="shrink-0 text-xs tabular-nums text-slate-400">{node.sub}</span>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
