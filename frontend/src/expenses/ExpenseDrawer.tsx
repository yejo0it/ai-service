import { useState, type FormEvent } from "react";
import { addExpense, toErrorMessage, updateExpense } from "../api/client";
import { COMPACT_LABEL_CLASS, Field, TextInput } from "../components/formFields";
import Drawer from "../trips/Drawer";
import type { Expense, ExpenseCategory, Trip } from "../types/api";
import { todayISODate } from "../utils/date";
import { digitsOf, formatKrwInput } from "../home/exchangeCalc";
import { EXPENSE_CATEGORIES } from "./expenseUtils";

interface ExpenseDrawerProps {
  trip: Trip;
  /** 있으면 수정, 없으면 새 지출 */
  expense?: Expense;
  onClose: () => void;
  onSaved: () => void;
}

/** 지출 등록·수정. 오늘이 여행 기간이면 오늘, 아니면 여행 첫날을 날짜 기본값으로 쓴다. */
export default function ExpenseDrawer({ trip, expense, onClose, onSaved }: ExpenseDrawerProps) {
  const today = todayISODate();
  const [title, setTitle] = useState(expense?.title ?? "");
  const [digits, setDigits] = useState(expense ? String(expense.amount_krw) : "");
  const [spentOn, setSpentOn] = useState(
    expense?.spent_on ?? (trip.start_date <= today && today <= trip.end_date ? today : trip.start_date),
  );
  const [category, setCategory] = useState<ExpenseCategory>(expense?.category ?? "food");
  const [memo, setMemo] = useState(expense?.memo ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const amount = Number(digits);
  const valid = title.trim() !== "" && amount > 0 && spentOn !== "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid || saving) return;
    setSaving(true);
    setError("");
    const payload = { title: title.trim(), amount, spent_on: spentOn, category, memo: memo.trim() };
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
        <Field label="금액 (원)" compact>
          <TextInput
            compact
            inputMode="numeric"
            autoComplete="off"
            value={formatKrwInput(digits)}
            onChange={(event) => setDigits(digitsOf(event.target.value))}
            placeholder="0"
            className="text-right font-semibold tabular-nums"
          />
        </Field>
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
