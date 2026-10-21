/**
 * 환율 계산기 계산·표시 도우미(원화 -> 현지 통화). 서버가 이미 내려준 환율만 쓰고 추가 요청은 하지 않는다.
 */

import type { ExchangeRate } from "../types/api";

/** 입력할 수 있는 원화 최대 자릿수(천억 원 미만). 너무 큰 값은 계산 결과가 의미 없다. */
export const MAX_KRW_DIGITS = 11;

/** 입력 문자열에서 숫자만 남긴다. 쉼표·공백·문자는 버린다. */
export const digitsOf = (text: string) => text.replace(/\D/g, "").slice(0, MAX_KRW_DIGITS);

/** 숫자만 남긴 문자열 -> 원화 금액. 비었거나 0이면 null(결과를 보이지 않는다). */
export function parseKrw(digits: string): number | null {
  const value = Number(digits);
  return digits && Number.isFinite(value) && value > 0 ? value : null;
}

/** 입력칸에 보여줄 천 단위 쉼표 표기 */
export const formatKrwInput = (digits: string) => (digits ? Number(digits).toLocaleString("ko-KR") : "");

/**
 * 통화별 소수점 자릿수. 표준(Intl)을 따르되, 실제로 소수점 단위를 쓰지 않는 통화는 0자리로 맞춘다.
 * (엔·동·원 0자리 / 달러·유로·바트 2자리)
 */
const NO_DECIMAL_CURRENCIES = new Set(["IDR", "KHR", "LAK", "MMK", "UZS", "KZT", "MNT", "HUF", "ISK", "CLP", "COP"]);

export function decimalsOf(currency: string): number {
  if (NO_DECIMAL_CURRENCIES.has(currency)) return 0;
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    return 2;
  }
}

/**
 * 원화 금액을 현지 통화로 환산한다. rate.krw는 rate.unit 만큼의 원화 금액이다.
 * 환율이 없거나 0 이하면 계산하지 않는다(null).
 */
export function convertKrw(krw: number, rate: Pick<ExchangeRate, "unit" | "krw" | "per_krw">): number | null {
  // 반올림 없는 1원당 금액이 있으면 그것으로, 없으면 표시용 환율(unit당 원화)로 계산한다.
  if (rate.per_krw !== undefined && rate.per_krw > 0) return krw * rate.per_krw;
  if (!(rate.krw > 0) || !(rate.unit > 0)) return null;
  return (krw / rate.krw) * rate.unit;
}

/** 통화 자릿수에 맞춘 금액 표기: 10,870 / 1,234.56 */
export function formatAmount(value: number, currency: string): string {
  const digits = decimalsOf(currency);
  return value.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** 환율 기준 시각(UTC 문자열, 예: "Tue, 21 Oct 2026 00:02:31 +0000")을 한국 시간 "10월 21일 09:02"로. 해석할 수 없으면 null. */
export function formatUpdatedAt(value: string): string | null {
  const time = Date.parse(value);
  if (!value || Number.isNaN(time)) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(time));
}

/** 여행지 선택 칩의 이름: 그 통화를 쓰는 여행 도시("도쿄·오사카"). 도시 정보가 없으면 통화 코드. */
export const rateLabel = (rate: Pick<ExchangeRate, "currency" | "cities">) =>
  rate.cities && rate.cities.length > 0 ? rate.cities.join("·") : rate.currency;

/** 선택한 통화의 환율. 선택한 통화가 목록에 없으면(여행이 바뀐 경우 등) 첫 번째 통화. */
export const pickRate = <T extends Pick<ExchangeRate, "currency">>(rates: T[], selected: string): T | undefined =>
  rates.find((rate) => rate.currency === selected) ?? rates[0];
