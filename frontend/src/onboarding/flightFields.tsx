import { useState } from "react";
import { Field, SuggestInput, TextInput } from "../components/formFields";
import type { AirlineSelection, AirportDraft } from "../types/onboarding";
import { findAirlineByName, searchAirlines, type AirlineOption } from "./airlines";
import { findAirportByName, searchAirports, type AirportOption } from "./airports";

/**
 * 항공편 입력 부품: 항공사 + 편명, 공항 자동완성.
 * 새 여행 만들기의 항공권 등록과 여행 상세의 공항(항공편) 직접 추가가 함께 쓴다.
 */

export const EMPTY_AIRPORT: AirportDraft = { text: "", airport: null };

/* 공항: 목록에서 고른 공항만 확정한다(직접 입력 불가). */

const airportKey = (item: AirportOption) => item.id;
const airportHint = (item: AirportOption) => item.code;
const airportLabel = (item: AirportOption) => (
  <span className="block">
    <span className="block truncate">{item.name}</span>
    <span className="block truncate text-xs text-slate-400">{item.city}</span>
  </span>
);

interface AirportInputProps {
  id: string;
  label: string;
  /** 가는 편·오는 편 칸을 구분하는 스크린 리더용 이름 */
  ariaLabel: string;
  value: AirportDraft;
  error?: string;
  onChange: (value: AirportDraft) => void;
  /** 작은 라벨·입력 칸 (여행 상세 직접 추가) */
  compact?: boolean;
}

/**
 * 공항 검색 자동완성. 목록에서 골라야 확정되고, 고르지 않고 포커스를 떠나면
 * 공항명이 정확히 일치할 때만 확정하고 아니면 입력을 비우고 안내한다.
 */
export function AirportInput({ id, label, ariaLabel, value, error, onChange, compact = false }: AirportInputProps) {
  const [rejected, setRejected] = useState("");

  const confirm = () => {
    const typed = value.text.trim();
    if (value.airport || !typed) return;
    const found = findAirportByName(typed);
    onChange(found ? { text: found.name, airport: found } : EMPTY_AIRPORT);
    setRejected(found ? "" : typed);
  };

  const message = rejected ? `'${rejected}'은(는) 목록에 없는 공항이에요.` : error;
  return (
    <Field label={label} compact={compact} error={message}>
      <SuggestInput
        id={id}
        compact={compact}
        value={value.text}
        error={message}
        search={searchAirports}
        keyOf={airportKey}
        renderLabel={airportLabel}
        renderHint={airportHint}
        onChange={(text) => {
          onChange({ text, airport: null });
          setRejected("");
        }}
        onPick={(item) => {
          onChange({ text: item.name, airport: item });
          setRejected("");
        }}
        onBlur={confirm}
        placeholder="예) 인천"
        aria-label={ariaLabel}
      />
    </Field>
  );
}

const airlineKey = (airline: AirlineOption) => airline.code;
const airlineHint = (airline: AirlineOption) => airline.code;

// 항공사 칸이 절반 너비라 국문/영문을 두 줄로 나눠 잘리지 않게 한다.
const airlineLabel = (airline: AirlineOption) => (
  <span className="block">
    <span className="block truncate">{airline.name}</span>
    {airline.name_en && (
      <span className="block truncate text-xs text-slate-400">{airline.name_en}</span>
    )}
  </span>
);

/** 항공사 자동완성 + IATA 코드가 앞에 붙는 편명 입력 한 쌍. */
interface AirlineFlightFieldsProps {
  id: string;
  airlineLabelText: string;
  flightLabelText: string;
  airline: string;
  airlineCode: string;
  /** IATA 코드를 뺀 편명 숫자 */
  flightNumber: string;
  /** '귀국 항공사 동일'이면 항공사 칸을 읽기 전용으로 둔다. */
  disabled?: boolean;
  airlineError?: string;
  flightError?: string;
  onAirlineChange: (airline: AirlineSelection) => void;
  onFlightNumberChange: (value: string) => void;
  /** 작은 라벨·입력 칸 (여행 상세 직접 추가) */
  compact?: boolean;
}

export function AirlineFlightFields({
  id,
  airlineLabelText,
  flightLabelText,
  airline,
  airlineCode,
  flightNumber,
  disabled = false,
  airlineError,
  flightError,
  onAirlineChange,
  onFlightNumberChange,
  compact = false,
}: AirlineFlightFieldsProps) {
  const sizeClass = compact ? "py-2.5 text-sm" : "py-3 text-base";
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label={airlineLabelText} compact={compact} error={airlineError}>
        {disabled ? (
          // '귀국 항공사 동일'이면 출국 값이 그대로 채워진 읽기 전용 입력.
          <TextInput value={airline} disabled readOnly compact={compact} aria-label={airlineLabelText} />
        ) : (
          <SuggestInput
            id={id}
            value={airline}
            error={airlineError}
            compact={compact}
            search={searchAirlines}
            keyOf={airlineKey}
            renderLabel={airlineLabel}
            renderHint={airlineHint}
            // 목록에 없는 항공사도 입력할 수 있다. 이름이 맞으면 IATA 코드를 채워준다.
            onChange={(value) =>
              onAirlineChange({
                name: value,
                code: findAirlineByName(value)?.code ?? "",
              })
            }
            onPick={(item) => onAirlineChange({ name: item.name, code: item.code })}
            placeholder="예) 대한항공"
            aria-label={airlineLabelText}
          />
        )}
      </Field>

      <Field label={flightLabelText} compact={compact} error={flightError}>
        <div
          className={`flex items-center rounded-xl border focus-within:ring-2 focus-within:ring-indigo-100 ${
            flightError
              ? "border-rose-400 focus-within:border-rose-500"
              : "border-slate-200 focus-within:border-indigo-500"
          }`}
        >
          <span
            className={`w-11 shrink-0 rounded-l-xl border-r text-center font-semibold tabular-nums ${sizeClass} ${
              airlineCode
                ? "border-slate-200 text-slate-600"
                : "border-slate-100 text-slate-300"
            } ${disabled ? "bg-slate-50" : "bg-white"}`}
            aria-hidden="true"
          >
            {airlineCode || "--"}
          </span>
          <input
            value={flightNumber}
            onChange={(event) =>
              onFlightNumberChange(event.target.value.replace(/\D/g, "").slice(0, 4))
            }
            inputMode="numeric"
            placeholder="001"
            aria-label={flightLabelText}
            className={`w-full min-w-0 rounded-r-xl bg-transparent px-3 tabular-nums text-slate-900 placeholder:text-slate-400 focus:outline-none ${sizeClass}`}
          />
        </div>
      </Field>
    </div>
  );
}
