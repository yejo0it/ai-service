import { useState, type FormEvent } from "react";
import { toErrorMessage, updateItineraryItem } from "../api/client";
import { COMPACT_LABEL_CLASS } from "../components/formFields";
import { TimeField } from "../components/pickers";
import type { HotelSuggestion, ItineraryItem, PlaceKind, Trip } from "../types/api";
import Drawer from "./Drawer";
import { KIND_STYLE, canResearchPlace } from "./TripItinerary";
import usePlaceSearch, { cityCodeFor } from "./usePlaceSearch";

interface EditItemDrawerProps {
  item: ItineraryItem;
  trip: Trip;
  dates: string[];
  onClose: () => void;
  onSaved: (item: ItineraryItem) => void;
}

/**
 * 경로 카드 수정: 장소 다시 검색(주소·전화·영업시간이 새 장소로 바뀐다)과 방문 시간(오전/오후, 미정 가능).
 * [저장]을 눌러야 반영된다. 순서는 그대로 두고, 바꾸려면 카드를 끌어 옮긴다.
 */
export default function EditItemDrawer({ item, trip, dates, onClose, onSaved }: EditItemDrawerProps) {
  const placeEditable = canResearchPlace(item);
  const kind = item.kind as PlaceKind;
  const [researching, setResearching] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<HotelSuggestion | null>(null);
  const [sessionToken] = useState(() => crypto.randomUUID());
  const [time, setTime] = useState(item.time ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const cityCode = cityCodeFor(trip, Math.max(0, dates.indexOf(item.day)), dates.length);
  const { suggestions, searchError } = usePlaceSearch({
    query,
    enabled: placeEditable && researching && !selected,
    sessionToken,
    cityCode,
    kind,
  });

  const timeChanged = time !== (item.time ?? "");
  const changed = Boolean(selected) || timeChanged;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!changed) {
      onClose();
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await updateItineraryItem(item.id, {
        ...(timeChanged ? { time: time || null } : {}),
        ...(selected ? { place_id: selected.place_id, session_token: sessionToken } : {}),
      });
      onSaved(updated);
    } catch (err) {
      setError(toErrorMessage(err));
      setSaving(false);
    }
  };

  const style = KIND_STYLE[item.kind];
  const inputClass =
    "w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100";

  return (
    <Drawer
      title="일정 수정"
      onClose={onClose}
      footer={
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-xl border border-slate-200 py-3 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="submit"
            form="edit-item-form"
            disabled={saving || !changed}
            className="flex-1 rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            {saving ? "저장하는 중..." : "저장"}
          </button>
        </div>
      }
    >
      <form id="edit-item-form" onSubmit={submit} className="space-y-5">
        <div>
          <p className={COMPACT_LABEL_CLASS}>{placeEditable ? "장소" : "일정"}</p>
          {selected || !researching ? (
            <div
              className={`flex items-start justify-between gap-2 rounded-xl border px-3 py-2.5 ${
                selected ? "border-indigo-200 bg-indigo-50" : "border-slate-200"
              }`}
            >
              <div className="flex min-w-0 items-start gap-2.5">
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs ${style.tile}`}>
                  <i className={style.icon} aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">{selected?.name ?? item.title}</p>
                  <p className="truncate text-xs text-slate-500">
                    {selected ? selected.description : item.address || item.stops[0]?.label || style.label}
                  </p>
                </div>
              </div>
              {placeEditable && (
                <button
                  type="button"
                  onClick={() => {
                    setSelected(null);
                    setResearching(true);
                  }}
                  className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
                >
                  {selected ? "다시 검색" : "장소 다시 검색"}
                </button>
              )}
            </div>
          ) : (
            <>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`${style.label} 이름을 입력하세요`}
                aria-label="장소 검색"
                autoComplete="off"
                autoFocus
                className={inputClass}
              />
              {suggestions.length > 0 && (
                <ul className="mt-1.5 overflow-hidden rounded-xl border border-slate-200" aria-label="검색 결과">
                  {suggestions.map((suggestion) => (
                    <li key={suggestion.place_id} className="border-t border-slate-100 first:border-t-0">
                      <button
                        type="button"
                        onClick={() => setSelected(suggestion)}
                        className="block w-full px-3 py-2.5 text-left hover:bg-slate-50"
                      >
                        <span className="block truncate text-sm font-medium text-slate-800">{suggestion.name}</span>
                        <span className="block truncate text-xs text-slate-400">{suggestion.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {searchError && <p className="mt-1.5 text-xs text-rose-600">{searchError}</p>}
              <button
                type="button"
                onClick={() => {
                  setResearching(false);
                  setQuery("");
                }}
                className="mt-1.5 text-xs font-medium text-slate-500 hover:text-slate-700"
              >
                검색 취소
              </button>
            </>
          )}
          {selected && (
            <p className="mt-1.5 text-xs text-slate-500">
              저장하면 주소·전화번호·영업시간이 새 장소 정보로 바뀌어요.
            </p>
          )}
        </div>

        <div>
          <p className={COMPACT_LABEL_CLASS}>
            방문 시간 <span className="font-normal text-slate-400">(선택)</span>
          </p>
          <TimeField value={time} onChange={setTime} ariaLabel="방문 시간" placeholder="시간 미정" optional compact />
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}
      </form>
    </Drawer>
  );
}
