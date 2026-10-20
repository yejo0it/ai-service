import { formatMinutes } from "../utils/date";
import type { ItineraryLeg, LegStep } from "../types/api";

/** 이동 구간이 없는 곳(첫 카드 앞 등)에는 아무것도 그리지 않는다. 시안 3b: 환승 단계 스트립. */

const WALK_CHIP = "flex items-center gap-1 text-xs text-slate-500";

/** 접힌 줄의 단계 칩: 도보는 걷는 아이콘 + 시간, 노선은 노선색 배지 + 소요 시간 */
function StepChip({ step }: { step: LegStep }) {
  if (step.type === "transit") {
    return (
      <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-900">
        <span
          className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white"
          style={{ backgroundColor: step.line_color }}
        >
          {step.line_name}
        </span>
        {formatMinutes(step.minutes)}
      </span>
    );
  }
  return (
    <span className={WALK_CHIP}>
      <i className={step.type === "drive" ? "fas fa-taxi" : "fas fa-walking"} aria-hidden="true" />
      {formatMinutes(step.minutes)}
    </span>
  );
}

/** 이름 + 원어(한국어와 다를 때만) + 역 번호: "시부야역(渋谷駅) JY20" */
function NameWithOriginal({ name, original, number }: { name: string; original?: string; number?: string }) {
  return (
    <>
      {name}
      {original && original !== name && <span className="font-normal text-slate-400">({original})</span>}
      {number && (
        <span className="ml-1 rounded border border-slate-200 px-1 align-middle text-[10px] font-semibold text-slate-500">
          {number}
        </span>
      )}
    </>
  );
}

/** 펼친 목록의 한 단계: 시작 시각 · 도보 설명 / 노선색 세로선 + 탑승·하차역 + 노선·운영사·행선지·소요 (환승 시간은 아래 한 줄) */
function StepRow({ step, showTime }: { step: LegStep; showTime: boolean }) {
  // 출발 시각을 모르는 구간(저장된 시간·예상 도착이 없는 일정)은 시각 열을 비우지 않고 숨긴다.
  const timeColumn = showTime && <span className="w-14 shrink-0 text-xs tabular-nums text-slate-400">{step.start_time}</span>;
  if (step.type !== "transit") {
    return (
      <li className="flex items-start gap-3 py-1">
        {timeColumn}
        <span className="text-xs text-slate-500">
          <i className={`${step.type === "drive" ? "fas fa-taxi" : "fas fa-walking"} mr-1 w-4`} aria-hidden="true" />
          {step.description}
        </span>
      </li>
    );
  }
  const details = [
    <span key="line">
      <NameWithOriginal name={step.line_name} original={step.line_name_ja} />
    </span>,
    step.train_type ? (
      <span
        key="type"
        title={step.train_type_ja}
        className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
      >
        {step.train_type}
      </span>
    ) : null,
    step.operator ? <span key="operator">{step.operator}</span> : null,
    step.direction ? (
      <span key="direction">
        <NameWithOriginal name={step.direction} original={step.direction_ja} />
      </span>
    ) : null,
    <span key="time">
      {step.stop_count > 0 ? `${step.stop_count}개 정거장 · ` : ""}
      {formatMinutes(step.minutes)}
    </span>,
  ].filter(Boolean);
  return (
    <>
      <li className="flex items-start gap-3 py-1">
        {timeColumn}
        <span className="flex min-w-0 flex-col gap-0.5 border-l-[3px] pl-2.5" style={{ borderColor: step.line_color }}>
          <span className="text-sm font-semibold text-slate-900">
            <span className="mr-1 text-xs font-normal text-slate-400">탑승</span>
            <NameWithOriginal name={step.from_stop} original={step.from_stop_ja} number={step.from_number} />
            <span className="mx-1.5 font-normal text-slate-300">→</span>
            <span className="mr-1 text-xs font-normal text-slate-400">하차</span>
            <NameWithOriginal name={step.to_stop} original={step.to_stop_ja} number={step.to_number} />
          </span>
          <span className="text-xs text-slate-500">
            {details.map((node, index) => (
              <span key={index}>
                {index > 0 && " · "}
                {node}
              </span>
            ))}
          </span>
        </span>
      </li>
      {step.transfer_minutes ? (
        <li className="flex items-start gap-3 py-0.5 text-xs text-slate-400">
          {showTime && <span className="w-14 shrink-0" aria-hidden="true" />}
          <span>
            <i className="fas fa-exchange-alt mr-1 w-4 text-center" aria-hidden="true" />
            {step.to_stop}에서 환승 · {formatMinutes(step.transfer_minutes)}
          </span>
        </li>
      ) : null}
    </>
  );
}

/** 로딩: 같은 높이의 회색 바 */
export function RouteLegSkeleton() {
  return <div className="mb-2 h-10 animate-pulse rounded-xl bg-slate-100" aria-hidden="true" />;
}

interface RouteLegProps {
  leg: ItineraryLeg;
  legKey: string;
  open: boolean;
  onToggle: (key: string) => void;
}

/**
 * 직전 일정 -> 이 일정 이동 구간.
 * - 대중교통: 접힌 줄(단계 칩 · 총 소요 · 요금)을 누르면 승하차역·시각이 펼쳐진다.
 * - 도보만 가능한 짧은 거리 · 택시만 있는 구간: 한 줄 표시(펼침 없음)
 * - 경로를 찾지 못한 구간: 숨기지 않고 안내 한 줄
 */
export default function RouteLeg({ leg, legKey, open, onToggle }: RouteLegProps) {
  if (leg.status === "not_found" || leg.steps.length === 0) {
    return <p className="mb-2 px-1 text-xs text-slate-400">이동 경로를 찾을 수 없어요</p>;
  }

  const simple = leg.mode !== "transit" || leg.steps.every((step) => step.type !== "transit");
  if (simple) {
    const step = leg.steps[0];
    return (
      <p className="mb-2 flex items-center gap-1.5 rounded-xl bg-slate-50 px-3.5 py-2.5 text-xs text-slate-500">
        <i className={leg.mode === "drive" ? "fas fa-taxi" : "fas fa-walking"} aria-hidden="true" />
        {step.type === "transit" ? formatMinutes(leg.total_minutes) : step.description}
      </p>
    );
  }

  const listId = `leg-${legKey}`;
  return (
    <div className="mb-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => onToggle(legKey)}
        className="flex w-full items-center gap-3 rounded-xl bg-slate-50 px-3.5 py-2.5 text-left hover:bg-slate-100"
      >
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {leg.steps.map((step, index) => (
            <span key={index} className="flex items-center gap-1.5">
              {index > 0 && <i className="fas fa-chevron-right text-[9px] text-slate-300" aria-hidden="true" />}
              <StepChip step={step} />
            </span>
          ))}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="whitespace-nowrap text-sm font-bold text-slate-900">{formatMinutes(leg.total_minutes)}</span>
          {leg.fare_label && <span className="whitespace-nowrap text-xs text-slate-400">{leg.fare_label}</span>}
          <i className={`fas ${open ? "fa-chevron-up" : "fa-chevron-down"} text-[11px] text-slate-400`} aria-hidden="true" />
        </span>
      </button>
      {open && (
        <ul id={listId} className="space-y-0.5 px-3.5 pb-1 pt-2.5">
          {leg.steps.map((step, index) => (
            <StepRow key={index} step={step} showTime={leg.steps.some((item) => item.start_time)} />
          ))}
        </ul>
      )}
    </div>
  );
}
