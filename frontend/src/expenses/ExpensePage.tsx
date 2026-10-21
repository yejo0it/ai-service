import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { deleteExpense, getExpenses, setBudget, toErrorMessage } from "../api/client";
import { digitsOf, formatKrwInput } from "../home/exchangeCalc";
import type { Expense, ExpenseCategory, ExpensesResponse, Trip } from "../types/api";
import { formatMonthDay } from "../utils/date";
import ExpenseDrawer from "./ExpenseDrawer";
import { EXPENSE_CATEGORIES, categoryOf, formatWon, spentPercent } from "./expenseUtils";

const CARD_CLASS = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";
const PRIMARY_BUTTON =
  "inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700";

type Drawer = { expense?: Expense } | null;

/** 총예산 · 총지출 · 남은 예산, 예산 대비 지출 비율. 예산은 이 자리에서 바로 설정·수정한다. */
function BudgetSummary({ trip, data, onChanged }: { trip: Trip; data: ExpensesResponse; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [digits, setDigits] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const percent = spentPercent(data.total_krw, data.budget_krw);
  const over = data.remaining_krw !== null && data.remaining_krw < 0;

  const open = () => {
    setDigits(data.budget_krw === null ? "" : String(data.budget_krw));
    setError("");
    setEditing(true);
  };

  const save = async (value: number | null) => {
    setSaving(true);
    setError("");
    try {
      await setBudget(trip.id, value);
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (digits !== "" && !saving) save(Number(digits));
  };

  return (
    <section aria-label="예산 요약" className={CARD_CLASS}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-slate-900">예산</h2>
        {!editing && (
          <button type="button" onClick={open} className="text-sm font-medium text-indigo-600 hover:underline">
            {data.budget_krw === null ? "예산 설정" : "예산 수정"}
          </button>
        )}
      </div>

      {editing && (
        <form onSubmit={submit} className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor="expense-budget" className="sr-only">
            총예산 (원)
          </label>
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100">
            <span className="shrink-0 text-sm font-semibold text-slate-400" aria-hidden="true">
              ₩
            </span>
            <input
              id="expense-budget"
              inputMode="numeric"
              autoComplete="off"
              autoFocus
              value={formatKrwInput(digits)}
              onChange={(event) => setDigits(digitsOf(event.target.value))}
              placeholder="총예산"
              className="min-w-0 flex-1 bg-transparent text-right text-sm font-semibold tabular-nums text-slate-900 placeholder:font-normal placeholder:text-slate-400 focus:outline-none"
            />
            <span className="shrink-0 text-xs text-slate-400">원</span>
          </div>
          <button
            type="submit"
            disabled={digits === "" || saving}
            className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
          >
            저장
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            disabled={saving}
            className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            취소
          </button>
          {data.budget_krw !== null && (
            <button
              type="button"
              onClick={() => save(null)}
              disabled={saving}
              className="rounded-xl px-2 py-2.5 text-sm font-medium text-slate-400 hover:text-rose-500"
            >
              예산 지우기
            </button>
          )}
        </form>
      )}
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}

      <dl className="mt-4 grid grid-cols-3 gap-3">
        <div>
          <dt className="text-xs text-slate-400">총예산</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-slate-900 sm:text-lg">
            {data.budget_krw === null ? <span className="text-slate-300">–</span> : formatWon(data.budget_krw)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">총지출</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-slate-900 sm:text-lg">{formatWon(data.total_krw)}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">남은 예산</dt>
          <dd className={`mt-1 text-base font-bold tabular-nums sm:text-lg ${over ? "text-rose-600" : "text-slate-900"}`}>
            {data.remaining_krw === null ? <span className="text-slate-300">–</span> : formatWon(data.remaining_krw)}
          </dd>
        </div>
      </dl>

      {data.budget_krw === null ? (
        <p className="mt-4 text-sm text-slate-500">예산을 설정하면 남은 금액과 사용 비율을 볼 수 있어요.</p>
      ) : (
        <div className="mt-4">
          <div
            className="h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="예산 대비 지출"
            aria-valuenow={Math.min(percent ?? 100, 100)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className={`h-full rounded-full transition-all duration-300 ${over ? "bg-rose-500" : "bg-indigo-500"}`}
              style={{ width: `${Math.min(percent ?? 100, 100)}%` }}
            />
          </div>
          <p className={`mt-2 text-xs ${over ? "text-rose-600" : "text-slate-500"}`}>
            {over
              ? `예산을 ${formatWon(-(data.remaining_krw ?? 0))} 초과했어요.`
              : percent === null
                ? ""
                : `예산의 ${percent}%를 썼어요.`}
          </p>
        </div>
      )}
    </section>
  );
}

function ExpenseRow({
  expense,
  onEdit,
  onDeleted,
}: {
  expense: Expense;
  onEdit: (expense: Expense) => void;
  onDeleted: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const category = categoryOf(expense.category);

  const remove = async () => {
    setDeleting(true);
    setError("");
    try {
      await deleteExpense(expense.id);
      onDeleted();
    } catch (err) {
      setError(toErrorMessage(err));
      setDeleting(false);
    }
  };

  return (
    <li className="py-3">
      <div className="flex items-center gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"
          title={category.label}
        >
          <i className={category.icon} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-900">{expense.title}</p>
          <p className="mt-0.5 truncate text-xs text-slate-500">
            {category.label} · {expense.payer_name} 결제{expense.memo && ` · ${expense.memo}`}
          </p>
        </div>
        <span className="shrink-0 text-sm font-bold tabular-nums text-slate-900">{formatWon(expense.amount_krw)}</span>
        {confirming ? (
          <div className="flex shrink-0 items-center gap-1.5" role="group" aria-label="삭제 확인">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={deleting}
              className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              취소
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={deleting}
              className="rounded-lg bg-rose-500 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
            >
              {deleting ? "삭제 중" : "삭제"}
            </button>
          </div>
        ) : (
          <div className="flex shrink-0 items-center">
            <button
              type="button"
              onClick={() => onEdit(expense)}
              aria-label={`${expense.title} 수정`}
              title="수정"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              <i className="fas fa-pen text-xs" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              aria-label={`${expense.title} 삭제`}
              title="삭제"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-300 transition-colors hover:bg-rose-50 hover:text-rose-500"
            >
              <i className="far fa-trash-alt text-xs" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
    </li>
  );
}

/** 여행 상세 `경비 관리` 탭: 예산 요약 · 분류별 합계 · 날짜별 지출 내역. */
export default function ExpensePage({ trip }: { trip: Trip }) {
  const [data, setData] = useState<ExpensesResponse | null>(null);
  const [error, setError] = useState("");
  const [category, setCategory] = useState<ExpenseCategory | null>(null);
  const [date, setDate] = useState("");
  const [drawer, setDrawer] = useState<Drawer>(null);

  // 화면을 깜박이지 않도록 다시 불러올 때는 이전 내용을 그대로 두고 바꿔 끼운다.
  const load = useCallback(() => {
    let cancelled = false;
    getExpenses(trip.id)
      .then((next) => !cancelled && (setData(next), setError("")))
      .catch((err: unknown) => !cancelled && setError(toErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [trip.id]);
  useEffect(() => load(), [load]);

  const closeDrawer = useCallback(() => setDrawer(null), []);

  const dates = useMemo(
    () => [...new Set((data?.expenses ?? []).map((expense) => expense.spent_on))].sort().reverse(),
    [data],
  );
  // 지출이 없어진 날짜 필터는 풀어 준다.
  useEffect(() => {
    if (date && !dates.includes(date)) setDate("");
  }, [date, dates]);

  const groups = useMemo(() => {
    const visible = (data?.expenses ?? []).filter(
      (expense) => (!category || expense.category === category) && (!date || expense.spent_on === date),
    );
    const byDate = new Map<string, Expense[]>();
    for (const expense of visible) byDate.set(expense.spent_on, [...(byDate.get(expense.spent_on) ?? []), expense]);
    return [...byDate.entries()].sort(([a], [b]) => (a < b ? 1 : -1));
  }, [data, category, date]);

  if (!data) {
    return error ? (
      <div role="alert" className="rounded-2xl border border-rose-100 bg-rose-50 p-6 text-center">
        <p className="text-sm text-rose-700">{error}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
        >
          다시 불러오기
        </button>
      </div>
    ) : (
      <div className="space-y-4">
        <div className="h-40 animate-pulse rounded-2xl bg-slate-200/70" />
        <div className="h-56 animate-pulse rounded-2xl bg-slate-200/70" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <BudgetSummary trip={trip} data={data} onChanged={load} />

      <section aria-label="지출 내역" className={CARD_CLASS}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-bold text-slate-900">지출 내역</h2>
          <button type="button" onClick={() => setDrawer({})} className={PRIMARY_BUTTON}>
            <i className="fas fa-plus text-xs" aria-hidden="true" />
            지출 추가
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5" role="group" aria-label="카테고리별 보기">
          <button
            type="button"
            onClick={() => setCategory(null)}
            aria-pressed={category === null}
            className={`rounded-xl border px-3 py-2 text-left transition-colors ${
              category === null ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <span className="block text-xs text-slate-500">전체</span>
            <span className="block text-sm font-bold tabular-nums text-slate-900">{formatWon(data.total_krw)}</span>
          </button>
          {EXPENSE_CATEGORIES.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setCategory(category === item.key ? null : item.key)}
              aria-pressed={category === item.key}
              className={`rounded-xl border px-3 py-2 text-left transition-colors ${
                category === item.key ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <span className="flex items-center gap-1.5 text-xs text-slate-500">
                <i className={`${item.icon} text-[10px]`} aria-hidden="true" />
                {item.label}
              </span>
              <span className="block text-sm font-bold tabular-nums text-slate-900">
                {formatWon(data.by_category[item.key] ?? 0)}
              </span>
            </button>
          ))}
        </div>

        {dates.length > 1 && (
          <div className="mt-3">
            <label htmlFor="expense-date" className="sr-only">
              날짜별 보기
            </label>
            <select
              id="expense-date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            >
              <option value="">전체 날짜</option>
              {dates.map((value) => (
                <option key={value} value={value}>
                  {formatMonthDay(value)}
                </option>
              ))}
            </select>
          </div>
        )}

        {data.expenses.length === 0 ? (
          <div className="mt-6 rounded-xl bg-slate-50 px-4 py-10 text-center">
            <p className="font-semibold text-slate-800">아직 지출 내역이 없어요</p>
            <p className="mt-1 text-sm text-slate-500">쓴 돈을 기록하고 예산과 비교해 보세요.</p>
          </div>
        ) : groups.length === 0 ? (
          <p className="mt-6 rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            조건에 맞는 지출이 없어요.
          </p>
        ) : (
          <div className="mt-4 space-y-5">
            {groups.map(([day, expenses]) => (
              <div key={day}>
                <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 pb-2">
                  <h3 className="text-sm font-semibold text-slate-700">{formatMonthDay(day)}</h3>
                  <span className="text-xs tabular-nums text-slate-400">
                    {formatWon(expenses.reduce((sum, expense) => sum + expense.amount_krw, 0))}
                  </span>
                </div>
                <ul className="divide-y divide-slate-100">
                  {expenses.map((expense) => (
                    <ExpenseRow
                      key={expense.id}
                      expense={expense}
                      onEdit={(target) => setDrawer({ expense: target })}
                      onDeleted={load}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {drawer && (
        <ExpenseDrawer
          trip={trip}
          expense={drawer.expense}
          onClose={closeDrawer}
          onSaved={() => {
            setDrawer(null);
            load();
          }}
        />
      )}
    </div>
  );
}
