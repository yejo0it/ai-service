import { useState, type KeyboardEvent } from "react";
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
import {
  addChecklistItem,
  deleteChecklistItem,
  toErrorMessage,
  updateChecklistItem,
  updateItineraryItem,
} from "../api/client";
import type { ChecklistItem, ItineraryItem, ItineraryKind } from "../types/api";
import { PIN_STYLE } from "./TripMap";
import { stopKey } from "./tripDays";

export const KIND_STYLE: Record<ItineraryKind, { icon: string; tile: string; label: string }> = {
  flight: { icon: "fas fa-plane", tile: "bg-violet-100 text-violet-600", label: "항공편" },
  hotel: { icon: "fas fa-bed", tile: "bg-rose-100 text-rose-500", label: "숙소" },
  airport: { icon: "fas fa-plane-departure", tile: "bg-indigo-100 text-indigo-600", label: "공항" },
  sight: { icon: "fas fa-landmark", tile: "bg-emerald-100 text-emerald-600", label: "관광지" },
  restaurant: { icon: "fas fa-utensils", tile: "bg-orange-100 text-orange-500", label: "식당" },
  cafe: { icon: "fas fa-coffee", tile: "bg-amber-100 text-amber-600", label: "카페" },
};

/** 카드 펼침: 메모 + 체크리스트. 체크리스트의 가방 아이콘은 짐싸기 노트 표시(예약·티켓·준비물은 자동으로 켜진다). */
function CardNotes({ item, onChange }: { item: ItineraryItem; onChange: (item: ItineraryItem) => void }) {
  const [memo, setMemo] = useState(item.memo);
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  const run = async (task: () => Promise<void>) => {
    setError("");
    try {
      await task();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  };

  const saveMemo = () =>
    memo !== item.memo &&
    run(async () => onChange({ ...item, memo: (await updateItineraryItem(item.id, { memo })).memo }));

  const setChecklist = (checklist: ChecklistItem[]) => onChange({ ...item, checklist });

  const addCheck = () => {
    const value = text.trim();
    if (!value) return;
    run(async () => {
      const created = await addChecklistItem(item.id, value);
      setChecklist([...item.checklist, created]);
      setText("");
    });
  };

  const patchCheck = (check: ChecklistItem, patch: Partial<ChecklistItem>) =>
    run(async () => {
      const updated = await updateChecklistItem(check.id, patch);
      setChecklist(item.checklist.map((c) => (c.id === check.id ? updated : c)));
    });

  const removeCheck = (check: ChecklistItem) =>
    run(async () => {
      await deleteChecklistItem(check.id);
      setChecklist(item.checklist.filter((c) => c.id !== check.id));
    });

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      addCheck();
    }
  };

  return (
    <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
      <textarea
        value={memo}
        onChange={(event) => setMemo(event.target.value)}
        onBlur={saveMemo}
        rows={2}
        placeholder="메모 (예: 전화 예약 필수)"
        aria-label={`${item.title} 메모`}
        className="w-full resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
      />
      <ul className="space-y-1.5" aria-label={`${item.title} 체크리스트`}>
        {item.checklist.map((check) => (
          <li key={check.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={check.done}
              onChange={(event) => patchCheck(check, { done: event.target.checked })}
              aria-label={check.text}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600"
            />
            <span className={`min-w-0 flex-1 truncate ${check.done ? "text-slate-400 line-through" : "text-slate-700"}`}>
              {check.text}
            </span>
            <button
              type="button"
              onClick={() => patchCheck(check, { in_packing_note: !check.in_packing_note })}
              aria-pressed={check.in_packing_note}
              aria-label={`${check.text} 짐싸기 노트 ${check.in_packing_note ? "표시 끄기" : "표시"}`}
              title={check.in_packing_note ? "짐싸기 노트에 표시 중" : "짐싸기 노트에 표시"}
              className={`flex h-6 w-6 items-center justify-center rounded-md text-xs transition-colors ${
                check.in_packing_note ? "bg-indigo-50 text-indigo-600" : "text-slate-300 hover:text-slate-500"
              }`}
            >
              <i className="fas fa-suitcase" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => removeCheck(check)}
              aria-label={`${check.text} 삭제`}
              className="flex h-6 w-6 items-center justify-center rounded-md text-xs text-slate-300 hover:text-rose-500"
            >
              <i className="fas fa-times" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="체크리스트 추가 (예: 웹으로 티켓 사전 예매)"
          aria-label={`${item.title} 체크리스트 추가`}
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
        <button
          type="button"
          onClick={addCheck}
          className="shrink-0 rounded-xl border border-slate-200 px-3 text-sm font-medium text-slate-600 hover:bg-slate-50"
        >
          추가
        </button>
      </div>
      <p className="text-[11px] text-slate-400">
        <i className="fas fa-suitcase mr-1" aria-hidden="true" />
        예약·티켓·준비물 항목은 짐싸기 노트에 자동으로 표시돼요.
      </p>
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  );
}

interface ItineraryCardProps {
  item: ItineraryItem;
  first: boolean;
  last: boolean;
  /** 위치별 지도 핀 번호 (stopKey -> 번호) */
  numbers: Map<string, number>;
  onRemove: (id: number) => void;
  onChange: (item: ItineraryItem) => void;
}

/** 일정 카드: 타임라인 점, 드래그 손잡이, 지도 번호·이름·주소, 전화·영업시간, 메모·체크리스트, x 삭제 */
function ItineraryCard({ item, first, last, numbers, onRemove, onChange }: ItineraryCardProps) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id });
  const [open, setOpen] = useState(false);
  const style = KIND_STYLE[item.kind];
  const noteCount = item.checklist.length + (item.memo ? 1 : 0);

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
                <p className="truncate text-sm font-semibold text-slate-900">
                  {item.title}
                  {item.source === "ai" && (
                    <span className="ml-1.5 rounded-full bg-violet-50 px-1.5 py-0.5 align-middle text-[10px] font-semibold text-violet-600">
                      AI
                    </span>
                  )}
                </p>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="text-xs tabular-nums text-slate-400">{item.time ?? item.time_label}</span>
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
                        aria-label={number ? `지도 ${number}번` : "지도에 표시하지 않음"}
                      >
                        {number ?? "–"}
                      </span>
                      <dt className="shrink-0 text-slate-400">{stop.caption}</dt>
                      <dd className="min-w-0 flex-1 truncate text-right font-medium text-slate-700">{stop.label}</dd>
                    </div>
                  );
                })}
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

              <button
                type="button"
                onClick={() => setOpen((previous) => !previous)}
                aria-expanded={open}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-indigo-600"
              >
                <i className="far fa-sticky-note" aria-hidden="true" />
                메모·체크리스트{noteCount > 0 ? ` ${noteCount}` : ""}
                <i className={`fas fa-chevron-${open ? "up" : "down"} text-[10px]`} aria-hidden="true" />
              </button>
            </div>
          </div>
          {open && <CardNotes item={item} onChange={onChange} />}
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
  onChange: (item: ItineraryItem) => void;
}

/** 그날의 일정 카드 목록. 손잡이를 끌어(또는 키보드로) 순서를 바꾸고, x로 뺀다. 모두 저장된다. */
export default function TripItinerary({ items, numbers, onReorder, onRemove, onChange }: TripItineraryProps) {
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
                onChange={onChange}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <p className="mt-3 text-center text-[11px] text-slate-400">카드를 끌어 순서를 바꿀 수 있어요.</p>
    </div>
  );
}
