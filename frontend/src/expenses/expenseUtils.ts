import type { ExpenseCategory } from "../types/api";

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
