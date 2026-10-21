import { useEffect, useMemo, useState, type FormEvent } from "react";
import { addExpense, getExpenseCurrencies, toErrorMessage, updateExpense } from "../api/client";
import { COMPACT_LABEL_CLASS, Field, TextInput } from "../components/formFields";
import { decimalsOf } from "../home/exchangeCalc";
import Drawer from "../trips/Drawer";
import type { Expense, ExpenseCategory, ExpenseCurrencies, Trip } from "../types/api";
import { todayISODate } from "../utils/date";
import { EXPENSE_CATEGORIES, formatAmountText, formatWon, rateLabel, sanitizeAmount } from "./expenseUtils";

interface ExpenseDrawerProps {
  trip: Trip;
  /** 있으면 수정, 없으면 새 지출 */
  expense?: Expense;
  onClose: () => void;
  onSaved: () => void;
}

type CurrenciesState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: ExpenseCurrencies };

/**
 * 지출 등록·수정. 현지 통화로 입력하면 원화 환산 금액을 미리 보여 주고, 저장할 때의 환율이 지출에 함께 저장된다.
 * 환율을 불러오지 못하면 원화로만 입력할 수 있다. 오늘이 여행 기간이면 오늘, 아니면 여행 첫날이 날짜 기본값이다.
 */
export default function ExpenseDrawer({ trip, expense, onClose, onSaved }: ExpenseDrawerProps) {
  const today = todayISODate();
  const [currencies, setCurrencies] = useState<CurrenciesState>({ status: "loading" });
  const [title, setTitle] = useState(expense?.title ?? "");
  const [currency, setCurrency] = useState(expense?.currency ?? "KRW");
  const [amountText, setAmountText] = useState(expense ? sanitizeAmount(expense.amount, decimalsOf(expense.currency)) : "");
  const [spentOn, setSpentOn] = useState(
    expense?.spent_on ?? (trip.start_date <= today && today <= trip.end_date ? today : trip.start_date),
  );
  const [category, setCategory] = useState<ExpenseCategory>(expense?.category ?? "food");
  const [memo, setMemo] = useState(expense?.memo ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getExpenseCurrencies(trip.id)
      .then((data) => !cancelled && setCurrencies({ status: "ready", data }))
      .catch((err: unknown) => !cancelled && setCurrencies({ status: "error", message: toErrorMessage(err) }));
    return () => {
      cancelled = true;
    };
  }, [trip.id]);

  const list = currencies.status === "ready" ? currencies.data : null;
  const current = list?.currencies.find((item) => item.currency === currency);
  const decimals = current?.decimals ?? decimalsOf(currency);
  const tripCurrencies = list?.currencies.filter((item) => list.trip_currencies.includes(item.currency)) ?? [];
  const otherCurrencies = list?.currencies.filter((item) => !list.trip_currencies.includes(item.currency)) ?? [];
  // 고친 지출의 통화가 지금 목록에 없어도(환율 서비스 오류 등) 그대로 보여 준다.
  const missingCurrent = currency !== "KRW" && !current;

  // 같은 통화의 지출을 고치면 처음 적용한 환율이 그대로 쓰이고, 그 밖에는 지금 환율로 환산한다.
  const keepsStoredRate = Boolean(expense && expense.currency === currency && expense.rate_per_krw);
  const rate = keepsStoredRate ? expense!.rate_per_krw : (current?.per_krw ?? null);
  const amountNumber = Number(amountText);
  const estimate = useMemo(
    () => (currency !== "KRW" && rate && amountNumber > 0 ? Math.round(amountNumber / Number(rate)) : null),
    [currency, rate, amountNumber],
  );

  const changeCurrency = (next: string) => {
    setCurrency(next);
    const nextDecimals = list?.currencies.find((item) => item.currency === next)?.decimals ?? decimalsOf(next);
    setAmountText((text) => sanitizeAmount(text, nextDecimals));
  };

  const valid = title.trim() !== "" && amountNumber > 0 && spentOn !== "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid || saving) return;
    setSaving(true);
    setError("");
    const payload = {
      title: title.trim(),
      amount: amountText.replace(/\.$/, ""),
      currency,
      spent_on: spentOn,
      category,
      memo: memo.trim(),
    };
    try {
      if (expense) await updateExpense(expense.id, payload);
      else await addExpense(trip.id, payload);
      onSaved();
    } catch (err) {
      setError(toErrorMessage(err));
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={expense ? "지출 수정" : "지출 추가"}
      onClose={onClose}
      footer={
        <button
          type="submit"
          form="expense-form"
          disabled={!valid || saving}
          className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {saving ? "저장 중…" : "저장"}
        </button>
      }
    >
      <form id="expense-form" onSubmit={submit} className="space-y-5">
        <Field label="지출명" compact>
          <TextInput
            compact
            value={title}
            maxLength={60}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="예) 이치란 라멘"
            autoFocus
          />
        </Field>

        <div>
          <span className={COMPACT_LABEL_CLASS}>금액</span>
          <div className="flex gap-2">
            <select
              aria-label="통화"
              value={currency}
              onChange={(event) => changeCurrency(event.target.value)}
              className="w-28 shrink-0 rounded-xl border border-slate-200 bg-white px-2.5 py-2.5 text-sm font-semibold text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            >
              <option value="KRW">₩ KRW</option>
              {missingCurrent && <option value={currency}>{currency}</option>}
              {tripCurrencies.length > 0 && (
                <optgroup label="여행지 통화">
                  {tripCurrencies.map((item) => (
                    <option key={item.currency} value={item.currency}>
                      {item.currency} {item.name}
                    </option>
                  ))}
                </optgroup>
              )}
              {otherCurrencies.length > 0 && (
                <optgroup label="다른 통화">
                  {otherCurrencies.map((item) => (
                    <option key={item.currency} value={item.currency}>
                      {item.currency} {item.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            <TextInput
              compact
              aria-label="금액"
              inputMode={decimals > 0 ? "decimal" : "numeric"}
              autoComplete="off"
              value={formatAmountText(amountText)}
              onChange={(event) => setAmountText(sanitizeAmount(event.target.value, decimals))}
              placeholder="0"
              className="min-w-0 flex-1 text-right font-semibold tabular-nums"
            />
          </div>
          {currency !== "KRW" && (
            <p className="mt-2 text-xs text-slate-500" aria-live="polite">
              {estimate !== null ? (
                <>
                  <span className="font-semibold text-slate-700">≈ {formatWon(estimate)}</span>
                  {rate && ` · ${rateLabel(currency, rate)}`}
                  <span className="text-slate-400">
                    {keepsStoredRate ? " (처음 적용한 환율)" : " (저장할 때의 환율로 기록돼요)"}
                  </span>
                </>
              ) : rate ? (
                `${rateLabel(currency, rate)} · 저장할 때의 환율로 원화 금액이 기록돼요.`
              ) : (
                "금액을 입력하면 저장할 때의 환율로 원화 금액이 기록돼요."
              )}
            </p>
          )}
          {currencies.status === "error" && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
              환율을 불러오지 못해 지금은 원화로만 새 지출을 입력할 수 있어요.
            </p>
          )}
        </div>

        <Field label="날짜" compact>
          <TextInput compact type="date" value={spentOn} onChange={(event) => setSpentOn(event.target.value)} />
        </Field>
        <div>
          <span className={COMPACT_LABEL_CLASS}>카테고리</span>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="카테고리">
            {EXPENSE_CATEGORIES.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setCategory(item.key)}
                aria-pressed={item.key === category}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                  item.key === category
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-200 text-slate-500 hover:border-slate-300"
                }`}
              >
                <i className={`${item.icon} text-xs`} aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <Field label="메모 (선택)" compact>
          <TextInput compact value={memo} maxLength={200} onChange={(event) => setMemo(event.target.value)} placeholder="메모" />
        </Field>
        {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>}
      </form>
    </Drawer>
  );
}
