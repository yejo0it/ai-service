import type { ReactNode } from "react";
import { TextInput } from "../components/formFields";
import { fieldState, getByPath, type FieldState } from "./reservationUtils";

/** 칸 옆에 보여 주는 상태 표시: 추출한 값과 확인하지 못한 값을 구분한다. */
const STATE_BADGE: Record<FieldState, { label: string; className: string }> = {
  missing: { label: "확인 필요", className: "bg-amber-50 text-amber-700" },
  extracted: { label: "추출됨", className: "bg-slate-100 text-slate-500" },
  edited: { label: "수정함", className: "bg-indigo-50 text-indigo-600" },
  entered: { label: "직접 입력", className: "bg-indigo-50 text-indigo-600" },
};

interface ReviewInputProps {
  id: string;
  label: string;
  /** 객체 안의 경로(검증 오류의 path와 같다) */
  path: string;
  /** 분석 직후 값(추출됨·수정함을 가리는 기준) */
  original: unknown;
  /** 지금 편집 중인 값 */
  current: unknown;
  error?: string;
  warning?: string;
  /** 칸이 선택 항목이면 비어 있어도 '확인 필요'로 표시하지 않는다 */
  optional?: boolean;
  type?: "text" | "date" | "time";
  placeholder?: string;
  maxLength?: number;
  /** 입력 값을 저장하기 전에 바꾼다(예: 공항 코드 대문자) */
  format?: (value: string) => string;
  onChange: (path: string, value: string | null) => void;
  /** 입력 칸 아래에 붙는 설명(공항 이름 등) */
  hint?: ReactNode;
  className?: string;
}

/** 라벨 + 입력 + 상태 표시 + 오류·경고. 예약 확인 화면의 모든 입력 칸이 공통으로 쓴다. */
export default function ReviewInput({
  id,
  label,
  path,
  original,
  current,
  error,
  warning,
  optional = false,
  type = "text",
  placeholder,
  maxLength,
  format,
  onChange,
  hint,
  className = "",
}: ReviewInputProps) {
  const value = getByPath(current, path);
  const state = fieldState(getByPath(original, path), value);
  const badge = state === "missing" && optional ? null : STATE_BADGE[state];
  const text = typeof value === "string" ? value : "";

  return (
    <div className={className}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-semibold text-slate-500">
          {label}
        </label>
        {badge && <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>{badge.label}</span>}
      </div>
      <TextInput
        compact
        id={id}
        type={type}
        value={text}
        maxLength={maxLength}
        placeholder={placeholder}
        error={error}
        aria-invalid={Boolean(error)}
        onChange={(event) => {
          const next = format ? format(event.target.value) : event.target.value;
          onChange(path, next.trim() === "" ? null : next);
        }}
        className={!error && state === "missing" && !optional ? "border-amber-300 bg-amber-50/40" : ""}
      />
      {hint}
      {error ? (
        <p className="mt-1 text-xs text-rose-600">{error}</p>
      ) : warning ? (
        <p className="mt-1 text-xs text-amber-600">{warning}</p>
      ) : null}
    </div>
  );
}
