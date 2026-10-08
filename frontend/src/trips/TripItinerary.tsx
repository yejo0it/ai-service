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
import type { ItineraryItem, ItineraryKind } from "../types/api";
import { PIN_STYLE } from "./TripMap";
import { pinKind, stopKey } from "./tripDays";

export const KIND_STYLE: Record<ItineraryKind, { icon: string; tile: string; label: string }> = {
  flight: { icon: "fas fa-plane", tile: "bg-violet-100 text-violet-600", label: "항공편" },
  hotel: { icon: "fas fa-bed", tile: "bg-rose-100 text-rose-500", label: "숙소" },
  airport: { icon: "fas fa-plane-departure", tile: "bg-indigo-100 text-indigo-600", label: "공항" },
  sight: { icon: "fas fa-landmark", tile: "bg-emerald-100 text-emerald-600", label: "관광지" },
  restaurant: { icon: "fas fa-utensils", tile: "bg-orange-100 text-orange-500", label: "식당" },
  cafe: { icon: "fas fa-coffee", tile: "bg-amber-100 text-amber-600", label: "카페" },
};

interface ItineraryCardProps {
  item: ItineraryItem;
  first: boolean;
  last: boolean;
  /** 위치별 지도 핀 번호 (stopKey -> 번호) */
  numbers: Map<string, number>;
  onRemove: (id: number) => void;
  onEdit: (item: ItineraryItem) => void;
}

/** 수정할 수 있는 카드 (등록 정보에서 만든 항공·숙소 카드는 등록 정보·AI로 관리한다) */
export const canEditItem = (item: ItineraryItem) => item.source !== "auto";

/** 장소를 다시 검색해 바꿀 수 있는 카드 (직접·AI로 추가한 장소. 항공편은 시간만 바꾼다) */
export const canResearchPlace = (item: ItineraryItem) => canEditItem(item) && item.kind !== "flight";

/** 일정 카드: 타임라인 점, 드래그 손잡이, 이름 + 지도 번호, 주소, 전화·영업시간, 수정(연필)·삭제(x) */
function ItineraryCard({ item, first, last, numbers, onRemove, onEdit }: ItineraryCardProps) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id });
  const style = KIND_STYLE[item.kind];
  // 지도 핀 번호 (항공편은 출발지 쪽 공항을 빼므로 현지 공항 번호만 남는다)
  const pins = item.stops.flatMap((stop, index) => {
    const number = numbers.get(stopKey(item.id, index));
    return number ? [{ number, badge: PIN_STYLE[pinKind(item, stop)].badge }] : [];
  });

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
          className={`rounded-2xl border bg-white p-3.5 transition-shadow ${
            isDragging ? "border-indigo-200 shadow-lg" : "border-slate-100 shadow-sm"
          }`}
        >
          <div className="flex gap-3">
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
                <div className="flex min-w-0 items-center gap-1.5">
                  <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
                  {pins.map((pin) => (
                    <span
                      key={pin.number}
                      className={`flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white ${pin.badge}`}
                      aria-label={`지도 ${pin.number}번`}
                      title={`지도 ${pin.number}번`}
                    >
                      {pin.number}
                    </span>
                  ))}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="text-xs tabular-nums text-slate-400">{item.time ?? item.time_label}</span>
                  {canEditItem(item) && (
                    <button
                      type="button"
                      onClick={() => onEdit(item)}
                      aria-label={`${item.title} 수정`}
                      title="수정"
                      className="flex h-6 w-6 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600"
                    >
                      <i className="fas fa-pen text-[11px]" aria-hidden="true" />
                    </button>
                  )}
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

              <dl className="mt-1.5 space-y-1 text-xs">
                {item.stops.map((stop, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <dt className="shrink-0 text-slate-400">{stop.caption}</dt>
                    <dd className="min-w-0 flex-1 truncate text-right font-medium text-slate-700">{stop.label}</dd>
                  </div>
                ))}
              </dl>

              {(item.phone || item.opening_hours.length > 0) && (
                <div className="mt-2 space-y-1 text-xs text-slate-500">
                  {item.phone && (
                    <p>
                      <i className="fas fa-phone mr-1.5 text-slate-300" aria-hidden="true" />
                      <a href={`tel:${item.phone}`} className="hover:text-indigo-600">
                        {item.phone}
                      </a>
                    </p>
                  )}
                  {item.opening_hours.length > 0 && (
                    <details>
                      <summary className="cursor-pointer select-none">
                        <i className="far fa-clock mr-1.5 text-slate-300" aria-hidden="true" />
                        영업일·영업시간
                      </summary>
                      <ul className="mt-1 space-y-0.5 pl-5">
                        {item.opening_hours.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

interface TripItineraryProps {
  items: ItineraryItem[];
  numbers: Map<string, number>;
  onReorder: (items: ItineraryItem[]) => void;
  onRemove: (id: number) => void;
  onEdit: (item: ItineraryItem) => void;
}

/** 그날의 일정 카드 목록. 손잡이를 끌어(또는 키보드로) 순서를 바꾸고, x로 뺀다. 모두 저장된다. */
export default function TripItinerary({ items, numbers, onReorder, onRemove, onEdit }: TripItineraryProps) {
  const sensors = useSensors(
    // 살짝 움직인 뒤부터 드래그로 본다(버튼 클릭과 구분).
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = items.findIndex((item) => item.id === active.id);
    const to = items.findIndex((item) => item.id === over.id);
    onReorder(arrayMove(items, from, to));
  };

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-8 text-center">
        <p className="text-sm font-medium text-slate-600">이 날은 아직 일정이 없어요</p>
        <p className="mt-1 text-xs text-slate-400">위 메뉴에서 AI와 함께 만들거나 장소를 직접 추가해 보세요.</p>
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
                onRemove={onRemove}
                onEdit={onEdit}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <p className="mt-3 text-center text-[11px] text-slate-400">카드를 끌어 순서를 바꿀 수 있어요.</p>
    </div>
  );
}
