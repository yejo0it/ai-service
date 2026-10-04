import { useMemo, useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode } from "react";

/**
 * 폼 입력 공통 부품: 라벨 칸 · 텍스트 입력 · 자동완성 입력.
 * 온보딩(새 여행 만들기)과 여행 상세(장소 직접 추가)가 같은 모양을 쓴다.
 */

/** 작은 라벨 (여행 상세 직접 추가처럼 좁은 패널) */
export const COMPACT_LABEL_CLASS = "mb-2 block text-xs font-semibold text-slate-500";

interface FieldProps {
  label: string;
  error?: string;
  hint?: string;
  /** 작은 라벨 */
  compact?: boolean;
  children: ReactNode;
}

export function Field({ label, error, hint, compact = false, children }: FieldProps) {
  return (
    <label className="block">
      <span className={compact ? COMPACT_LABEL_CLASS : "mb-1.5 block text-sm font-medium text-slate-700"}>
        {label}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-rose-600">{error}</span>}
    </label>
  );
}

const INPUT_CLASS =
  "w-full rounded-xl border border-slate-200 bg-white text-slate-900 " +
  "placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 " +
  "focus:ring-indigo-100 disabled:bg-slate-50";

/** 입력 칸 크기: 기본(새 여행 만들기) / 작게(여행 상세 직접 추가) */
export const inputSizeClass = (compact = false) => (compact ? "px-3 py-2.5 text-sm" : "px-3.5 py-3 text-base");

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & { error?: string; compact?: boolean };

export function TextInput({ error, compact = false, ...props }: TextInputProps) {
  const errorClass = error
    ? "border-rose-400 focus:border-rose-500 focus:ring-rose-100"
    : "";
  return <input {...props} className={`${INPUT_CLASS} ${inputSizeClass(compact)} ${errorClass}`} />;
}

/**
 * 입력하면 후보 목록을 드롭다운으로 보여주는 자동완성 입력.
 * 목록에 없는 값도 그대로 입력할 수 있고, 포커스만으로는 목록이 열리지 않는다.
 * 목록 선택만 허용하려면 onBlur에서 확정되지 않은 값을 정리한다.
 * `search`는 모듈 상수 함수를 넘겨야 useMemo가 유효하다.
 */
type SuggestInputProps<T> = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "value" | "onChange" | "onBlur"
> & {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onPick: (item: T) => void;
  /** 입력어로 후보를 찾는 동기 검색 (모듈 상수 함수) */
  search?: (query: string) => T[];
  /** 비동기 검색 결과. 넘기면 search 대신 그대로 후보로 쓴다. */
  items?: T[];
  keyOf: (item: T) => string;
  renderLabel: (item: T) => ReactNode;
  renderHint: (item: T) => ReactNode;
  error?: string;
  onBlur?: () => void;
  /** 작은 입력 칸 */
  compact?: boolean;
};

export function SuggestInput<T>({
  id,
  value,
  onChange,
  onPick,
  search,
  items,
  keyOf,
  renderLabel,
  renderHint,
  error,
  onBlur,
  compact = false,
  ...inputProps
}: SuggestInputProps<T>) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  // items를 넘기면(비동기 검색 결과) search 대신 그대로 후보로 쓴다.
  const suggestions = useMemo(() => items ?? search?.(value) ?? [], [items, search, value]);
  const listId = `${id}-listbox`;

  const pick = (item: T) => {
    onPick(item);
    setOpen(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (suggestions.length === 0) return;
    if (!open) {
      // 포커스만으로는 열지 않으므로, ↓ 키로 명시적으로 열 수 있게 해준다.
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlight(0);
        setOpen(true);
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => (current - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter") {
      // 폼 제출(다음 단계)보다 목록 선택이 우선이다.
      event.preventDefault();
      pick(suggestions[Math.min(highlight, suggestions.length - 1)]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <TextInput
        {...inputProps}
        value={value}
        error={error}
        compact={compact}
        onChange={(event) => {
          onChange(event.target.value);
          setHighlight(0);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          setOpen(false);
          onBlur?.();
        }}
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
      />

      {open && suggestions.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
        >
          {suggestions.map((item, position) => (
            <li key={keyOf(item)} role="option" aria-selected={position === highlight}>
              <button
                type="button"
                // onBlur보다 먼저 실행되어 목록이 닫히는 것을 막는다.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(item)}
                onMouseEnter={() => setHighlight(position)}
                className={`flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-sm transition-colors ${
                  position === highlight ? "bg-indigo-50 text-indigo-700" : "text-slate-700"
                }`}
              >
                {/* 줄 수는 renderLabel이 정한다(항공사는 국문/영문 2줄). */}
                <span className="min-w-0 flex-1">{renderLabel(item)}</span>
                <span className="shrink-0 text-xs tabular-nums text-slate-400">
                  {renderHint(item)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
