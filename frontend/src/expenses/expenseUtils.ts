import { formatAmount } from "../home/exchangeCalc";
import type { Expense, ExpenseCategory } from "../types/api";

/** 지출 분류. 화면에도 이 순서대로 나온다. */
export const EXPENSE_CATEGORIES: { key: ExpenseCategory; label: string; icon: string }[] = [
  { key: "transport", label: "교통", icon: "fas fa-bus" },
  { key: "lodging", label: "숙박", icon: "fas fa-bed" },
  { key: "food", label: "식비", icon: "fas fa-utensils" },
  { key: "sightseeing", label: "관광", icon: "fas fa-camera" },
  { key: "shopping", label: "쇼핑", icon: "fas fa-shopping-bag" },
  { key: "etc", label: "기타", icon: "fas fa-ellipsis-h" },
];

export const categoryOf = (key: ExpenseCategory) =>
  EXPENSE_CATEGORIES.find((category) => category.key === key) ?? EXPENSE_CATEGORIES[EXPENSE_CATEGORIES.length - 1];

/** 12,000원 */
export const formatWon = (value: number) => `${value.toLocaleString("ko-KR")}원`;

/** ₩540,000 */
export const formatWonSign = (value: number) => `₩${value.toLocaleString("ko-KR")}`;

/** 예산을 짧게: 1,000,000 -> "100만 원", 만 단위로 떨어지지 않으면 "1,234,567원" */
export const compactWon = (value: number) =>
  value >= 10000 && value % 10000 === 0 ? `${(value / 10000).toLocaleString("ko-KR")}만 원` : formatWon(value);

/** 예산 대비 지출 비율(%). 예산이 없거나 0원이면 null. 100을 넘을 수 있다. */
export const spentPercent = (total: number, budget: number | null) =>
  budget === null || budget <= 0 ? null : Math.round((total / budget) * 100);

/** 적용 환율(1원당 현지 통화 금액) -> "1 JPY = 9.09원" 표시. 환율이 비정상이면 빈 문자열. */
export function rateLabel(currency: string, perKrw: string | null): string {
  const rate = Number(perKrw);
  if (!perKrw || !(rate > 0)) return "";
  const won = 1 / rate;
  const digits = won >= 100 ? 0 : won >= 1 ? 2 : 4;
  return `1 ${currency} = ${won.toLocaleString("ko-KR", { maximumFractionDigits: digits })}원`;
}

/** 입력 중인 금액 문자열 정리: 숫자와 소수점 하나만 남기고 소수 자릿수를 맞춘다(0이면 정수만). */
export function sanitizeAmount(text: string, decimals: number): string {
  const [whole, ...rest] = text.replace(/[^\d.]/g, "").split(".");
  const integer = whole.slice(0, 11);
  if (decimals === 0 || rest.length === 0) return integer;
  return `${integer}.${rest.join("").slice(0, decimals)}`;
}

/** 정리된 금액 문자열을 쉼표로 보기 좋게: "1200.5" -> "1,200.5" (소수점 입력 중인 "12."도 그대로 보인다) */
export function formatAmountText(text: string): string {
  if (!text) return "";
  const [whole, fraction] = text.split(".");
  const integer = whole === "" ? "0" : Number(whole).toLocaleString("ko-KR");
  return fraction === undefined ? integer : `${integer}.${fraction}`;
}

/** 입력한 통화 금액 표기: "1,200 JPY", "14.50 USD" */
export const formatOriginal = (expense: Pick<Expense, "amount" | "currency">) =>
  `${formatAmount(Number(expense.amount), expense.currency)} ${expense.currency}`;
