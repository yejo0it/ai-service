import { useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { PIN_STYLE } from "./TripMap";
import { stopKey, type ItineraryItem, type ItineraryKind } from "./tripDays";

const KIND_STYLE: Record<ItineraryKind, { icon: string; tile: string }> = {
  flight: { icon: "fas fa-plane", tile: "bg-violet-100 text-violet-600" },
  hotel: { icon: "fas fa-bed", tile: "bg-rose-100 text-rose-500" },
  place: { icon: "fas fa-map-marker-alt", tile: "bg-emerald-100 text-emerald-600" },
};

interface ItineraryCardProps {
  item: ItineraryItem;
  first: boolean;
  last: boolean;
  /** 위치별 지도 핀 번호 (stopKey -> 번호) */
  numbers: Map<string, number>;
  onRemove: (id: string) => void;
}

/** 일정 카드 한 장: 왼쪽 타임라인 점, 드래그 손잡이, 위치별 지도 번호, x 삭제 */
function ItineraryCard({ item, first, last, numbers, onRemove }: ItineraryCardProps) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id });
  const style = KIND_STYLE[item.kind];

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`relative flex gap-3 ${isDragging ? "z-10" : ""}`}
    >
      {/* 타임라인: 첫 일정은 채운 점, 나머지는 빈 점. 점 사이를 점선으로 잇는다. */}
      <div className="flex w-3 shrink-0 flex-col items-center pt-6" aria-hidden="true">
        <span
          className={`h-3 w-3 rounded-full border-2 ${first ? "border-indigo-500 bg-indigo-500" : "border-slate-300 bg-white"}`}
        />
        {!last && <span className="w-0 flex-1 border-l-2 border-dashed border-slate-200" />}
      </div>

      <div className={`min-w-0 flex-1 ${last ? "" : "pb-3"}`}>
        <div
          className={`flex gap-3 rounded-2xl border bg-white p-3.5 transition-shadow ${
            isDragging ? "border-indigo-200 shadow-lg" : "border-slate-100 shadow-sm"
          }`}
        >
          <button
            ref={setActivatorNodeRef}
            type="button"
            {...attributes}
            {...listeners}
            aria-label={`${item.title} 순서 옮기기 (끌어서 이동, 키보드는 스페이스 후 화살표)`}
            title="끌어서 순서 바꾸기"
            className="-ml-1 flex w-5 shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-slate-300 hover:bg-slate-50 hover:text-slate-500 active:cursor-grabbing"
          >
            <i className="fas fa-grip-vertical text-xs" aria-hidden="true" />
          </button>

          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${style.tile}`} aria-hidden="true">
            <i className={style.icon} />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
              <div className="flex shrink-0 items-center gap-1">
                <span className="text-xs tabular-nums text-slate-400">{item.time}</span>
                <button
                  type="button"
                  onClick={() => onRemove(item.id)}
                  aria-label={`${item.title} 삭제`}
                  title="삭제"
                  className="flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-500"
                >
                  <i className="fas fa-times text-xs" aria-hidden="true" />
                </button>
              </div>
            </div>
            {item.subtitle && <p className="text-xs text-slate-500">{item.subtitle}</p>}

            {/* 위치: 지도 핀과 같은 번호·색. 좌표가 없는 위치는 번호 없이 표시한다. */}
            <dl className="mt-1.5 space-y-1 text-xs">
              {item.stops.map((stop, index) => {
                const number = numbers.get(stopKey(item.id, index));
                return (
                  <div key={index} className="flex items-center gap-2">
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                        number ? `${PIN_STYLE[stop.kind].badge} text-white` : "bg-slate-100 text-slate-300"
                      }`}
                      aria-label={number ? `지도 ${number}번` : "지도 위치 없음"}
                    >
                      {number ?? "–"}
                    </span>
                    <dt className="shrink-0 text-slate-400">{stop.caption}</dt>
                    <dd className="min-w-0 flex-1 truncate text-right font-medium text-slate-700">{stop.label}</dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>
      </div>
    </li>
  );
}

interface TripItineraryProps {
  items: ItineraryItem[];
  numbers: Map<string, number>;
  onChange: (items: ItineraryItem[]) => void;
}

/**
 * 그날의 일정 카드 목록. 손잡이를 끌어(또는 키보드로) 순서를 바꾸고, x로 뺀다.
 * 아직 일정 저장 기능이 없어 순서 변경·삭제는 이 화면에서만 반영된다.
 */
export default function TripItinerary({ items, numbers, onChange }: TripItineraryProps) {
  const sensors = useSensors(
    // 살짝 움직인 뒤부터 드래그로 본다(버튼 클릭과 구분).
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = items.findIndex((item) => item.id === active.id);
    const to = items.findIndex((item) => item.id === over.id);
    onChange(arrayMove(items, from, to));
  };

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center">
        <p className="text-sm font-medium text-slate-600">이 날은 아직 일정이 없어요</p>
        <p className="mt-1 text-xs text-slate-400">위 버튼으로 경로를 추가해 보세요.</p>
      </div>
    );
  }

  return (
    <div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={items.map((item) => item.id)} strategy={verticalListSortingStrategy}>
          <ol aria-label="일정">
            {items.map((item, index) => (
              <ItineraryCard
                key={item.id}
                item={item}
                first={index === 0}
                last={index === items.length - 1}
                numbers={numbers}
                onRemove={(id) => onChange(items.filter((current) => current.id !== id))}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <p className="mt-3 text-center text-[11px] text-slate-400">
        카드를 끌어 순서를 바꿀 수 있어요. 순서 변경·삭제는 아직 저장되지 않아요.
      </p>
    </div>
  );
}

/** 경로 추가 버튼 (다음 단계에서 기능을 붙인다) */
const ROUTE_ACTIONS = [
  { label: "AI와 함께 만들기", icon: "fas fa-magic", primary: true },
  { label: "AI한테 추천 받기", icon: "far fa-lightbulb", primary: false },
  { label: "직접 추가", icon: "fas fa-plus", primary: false },
  { label: "일행 초대하기", icon: "fas fa-user-plus", primary: false },
];

export function RouteActions() {
  const [notice, setNotice] = useState("");

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {ROUTE_ACTIONS.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => setNotice(`'${action.label}'은(는) 준비 중이에요.`)}
            className={`flex items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
              action.primary
                ? "bg-indigo-600 text-white hover:bg-indigo-700"
                : "border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
            }`}
          >
            <i className={`${action.icon} text-xs`} aria-hidden="true" />
            {action.label}
          </button>
        ))}
      </div>
      {notice && (
        <p role="status" className="mt-2 text-center text-xs text-slate-500">
          {notice}
        </p>
      )}
    </div>
  );
}
