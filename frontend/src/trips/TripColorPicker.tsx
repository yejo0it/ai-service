import type { TripColorKey } from "../types/api";
import { TRIP_COLOR_KEYS, TRIP_COLORS } from "./tripUtils";

interface TripColorPickerProps {
  /** 고른 색. 빈 문자열이면 자동 */
  value: TripColorKey | "";
  onChange: (color: TripColorKey | "") => void;
  disabled?: boolean;
}

/** 여행 색 선택: 자동 + 기본 색상·인디고 8색 */
export default function TripColorPicker({ value, onChange, disabled }: TripColorPickerProps) {
  return (
    <div role="radiogroup" aria-label="여행 색상" className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        role="radio"
        aria-checked={value === ""}
        disabled={disabled}
        onClick={() => onChange("")}
        title="자동: 여행마다 색을 알아서 골라요"
        className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
          value === ""
            ? "border-slate-300 bg-slate-100 text-slate-700"
            : "border-slate-200 text-slate-500 hover:border-slate-300"
        }`}
      >
        자동
      </button>
      {TRIP_COLOR_KEYS.map((key) => {
        const selected = key === value;
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={TRIP_COLORS[key].label}
            title={TRIP_COLORS[key].label}
            disabled={disabled}
            onClick={() => onChange(key)}
            className={`flex h-7 w-7 items-center justify-center rounded-full transition-transform hover:scale-110 disabled:opacity-50 ${
              TRIP_COLORS[key].cap
            }`}
          >
            {selected && <i className="fas fa-check text-[10px]" aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}
