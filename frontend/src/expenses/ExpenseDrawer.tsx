import { useEffect, useMemo, useState, type FormEvent } from "react";
import { addExpense, getExpenseCurrencies, getTripMembers, toErrorMessage, updateExpense } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { COMPACT_LABEL_CLASS, Field, TextInput } from "../components/formFields";
import { decimalsOf } from "../home/exchangeCalc";
import Drawer from "../trips/Drawer";
import type { Expense, ExpenseCategory, ExpenseCurrencies, SplitMethod, Trip } from "../types/api";
import { todayISODate } from "../utils/date";
import {
  EXPENSE_CATEGORIES,
  equalMinor,
  formatAmountText,
  formatWon,
  fromMinor,
  rateLabel,
  sanitizeAmount,
  toMinor,
} from "./expenseUtils";

interface ExpenseDrawerProps {
  trip: Trip;
  /** 있으면 수정, 없으면 새 지출 */
  expense?: Expense;
  onClose: () => void;
  onSaved: () => void;
}

/** 결제자·분담 인원으로 고를 수 있는 사람. active=false는 이 지출에 이미 있던 나간 일행이다. */
interface Person {
  id: number;
  name: string;
  active: boolean;
}

type MembersState = { status: "loading" } | { status: "error" } | { status: "ready"; people: Person[] };

type CurrenciesState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: ExpenseCurrencies };

/**
 * 지출 등록·수정. 현지 통화로 입력하면 원화 환산 금액을 미리 보여 주고, 저장할 때의 환율이 지출에 함께 저장된다.
 * 환율을 불러오지 못하면 원화로만 입력할 수 있다. 오늘이 여행 기간이면 오늘, 아니면 여행 첫날이 날짜 기본값이다.
 * 결제자와 분담 인원(기본은 여행에 함께하는 모두)을 고르면 선택한 인원끼리 균등하게 나누거나,
 * 사람마다 금액을 직접 입력해 나눈다(직접 입력의 합계는 지출 금액과 같아야 저장된다).
 */
export default function ExpenseDrawer({ trip, expense, onClose, onSaved }: ExpenseDrawerProps) {
  const today = todayISODate();
  const { user } = useAuth();
  const [members, setMembers] = useState<MembersState>({ status: "loading" });
  const [payerId, setPayerId] = useState<number | null>(expense?.payer_id ?? user?.id ?? null);
  // null이면 아직 고르지 않은 것(기본: 함께하는 모두). 분담 인원을 정하지 않은 예전 지출도 기본은 모두다.
  const [pickedIds, setPickedIds] = useState<number[] | null>(
    expense && expense.participants.length > 0 ? expense.participants.map((person) => person.id) : null,
  );
  const [splitMethod, setSplitMethod] = useState<SplitMethod>(expense?.split_method ?? "equal");
  // 직접 입력 금액(회원 번호 -> 입력 중인 금액 문자열). 지출 통화 기준이다.
  const [customTexts, setCustomTexts] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      (expense?.participants ?? [])
        .filter((person) => person.amount !== null)
        .map((person) => [person.id, sanitizeAmount(person.amount ?? "", decimalsOf(expense?.currency ?? "KRW"))]),
    ),
  );
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

  useEffect(() => {
    let cancelled = false;
    getTripMembers(trip.id)
      .then((data) => {
        if (cancelled) return;
        const current: Person[] = [...(data.owner ? [data.owner] : []), ...data.members].map((person) => ({
          id: person.id,
          name: person.name,
          active: true,
        }));
        // 이 지출에 이미 있던 사람이 지금은 함께하지 않아도(나간 일행) 그대로 보여 준다.
        const known = new Set(current.map((person) => person.id));
        const former: Person[] = [
          ...(expense?.participants ?? []),
          ...(expense?.payer_id ? [{ id: expense.payer_id, name: expense.payer_name }] : []),
        ]
          .filter((person, index, all) => !known.has(person.id) && all.findIndex((other) => other.id === person.id) === index)
          .map((person) => ({ id: person.id, name: person.name, active: false }));
        setMembers({ status: "ready", people: [...current, ...former] });
      })
      .catch(() => !cancelled && setMembers({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [trip.id, expense]);

  const people = members.status === "ready" ? members.people : [];
  const selectedIds = pickedIds ?? people.filter((person) => person.active).map((person) => person.id);
  const togglePerson = (id: number) =>
    setPickedIds(selectedIds.includes(id) ? selectedIds.filter((other) => other !== id) : [...selectedIds, id]);
  const showPeople = members.status === "ready" && people.length > 1;

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

  // 인당 금액 안내: 원화 환산 금액(원화 입력이면 입력 금액)을 선택한 인원으로 나눈 값
  const krwAmount = currency === "KRW" ? amountNumber : estimate;
  const perPerson = krwAmount && selectedIds.length > 0 ? Math.round(krwAmount / selectedIds.length) : null;

  // 직접 입력: 선택한 사람들의 금액 합계가 지출 금액과 같아야 한다(오차 없이 최소 단위 정수로 비교).
  const custom = showPeople && splitMethod === "custom";
  const totalMinor = toMinor(amountText, decimals);
  const customMinor = selectedIds.reduce((sum, id) => sum + toMinor(customTexts[id] ?? "", decimals), 0);
  const customDiff = totalMinor - customMinor;
  const fillEqually = () => {
    const parts = equalMinor(totalMinor, selectedIds.length);
    setCustomTexts(Object.fromEntries(selectedIds.map((id, index) => [id, fromMinor(parts[index], decimals)])));
  };

  // 일행 정보를 불러오는 동안에는 저장하지 않는다(결제자·분담 인원이 빠진 채 저장되지 않게).
  const valid =
    title.trim() !== "" &&
    amountNumber > 0 &&
    spentOn !== "" &&
    members.status !== "loading" &&
    (members.status !== "ready" || selectedIds.length > 0) &&
    (!custom || customDiff === 0);

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
      ...(members.status === "ready" && payerId !== null
        ? custom
          ? {
              payer_id: payerId,
              split_method: "custom" as const,
              participant_amounts: selectedIds.map((id) => ({
                id,
                amount: (customTexts[id] ?? "").replace(/\.$/, "") || "0",
              })),
            }
          : { payer_id: payerId, split_method: "equal" as const, participant_ids: selectedIds }
        : {}),
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

        {showPeople && (
          <>
            <Field label="결제자" compact>
              <select
                value={payerId ?? ""}
                onChange={(event) => setPayerId(Number(event.target.value))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
              >
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                    {!person.active && " (나간 일행)"}
                  </option>
                ))}
              </select>
            </Field>
            <div>
              <span className={COMPACT_LABEL_CLASS}>분담 인원</span>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="분담 인원">
                {people.map((person) => {
                  const on = selectedIds.includes(person.id);
                  return (
                    <button
                      key={person.id}
                      type="button"
                      onClick={() => togglePerson(person.id)}
                      aria-pressed={on}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                        on
                          ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 text-slate-500 hover:border-slate-300"
                      }`}
                    >
                      {on && <i className="fas fa-check text-[10px]" aria-hidden="true" />}
                      {person.name}
                      {!person.active && <span className="text-xs text-slate-400">(나간 일행)</span>}
                    </button>
                  );
                })}
              </div>
              <div className="mt-3 inline-flex rounded-xl bg-slate-100 p-0.5" role="group" aria-label="분담 방식">
                {(
                  [
                    ["equal", "균등 분할"],
                    ["custom", "직접 입력"],
                  ] as const
                ).map(([method, label]) => (
                  <button
                    key={method}
                    type="button"
                    onClick={() => setSplitMethod(method)}
                    aria-pressed={splitMethod === method}
                    className={`rounded-[10px] px-3 py-1.5 text-xs font-semibold transition-colors ${
                      splitMethod === method ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {custom ? (
                <div className="mt-3 space-y-2">
                  {people
                    .filter((person) => selectedIds.includes(person.id))
                    .map((person) => (
                      <div key={person.id} className="flex items-center gap-2">
                        <label htmlFor={`share-${person.id}`} className="min-w-0 flex-1 truncate text-sm text-slate-700">
                          {person.name}
                          {!person.active && <span className="ml-1 text-xs text-slate-400">(나간 일행)</span>}
                        </label>
                        <TextInput
                          compact
                          id={`share-${person.id}`}
                          inputMode={decimals > 0 ? "decimal" : "numeric"}
                          autoComplete="off"
                          value={formatAmountText(customTexts[person.id] ?? "")}
                          onChange={(event) =>
                            setCustomTexts((texts) => ({ ...texts, [person.id]: sanitizeAmount(event.target.value, decimals) }))
                          }
                          placeholder="0"
                          className="w-36 text-right font-semibold tabular-nums"
                        />
                        <span className="w-9 shrink-0 text-xs text-slate-400">{currency}</span>
                      </div>
                    ))}
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <p
                      className={`text-xs ${customDiff === 0 && totalMinor > 0 ? "text-emerald-600" : "text-rose-600"}`}
                      aria-live="polite"
                    >
                      {totalMinor === 0
                        ? "금액을 먼저 입력해 주세요."
                        : customDiff === 0
                          ? "합계가 지출 금액과 같아요."
                          : customDiff > 0
                            ? `${formatAmountText(fromMinor(customDiff, decimals))} ${currency} 더 나눠야 해요.`
                            : `${formatAmountText(fromMinor(-customDiff, decimals))} ${currency} 초과했어요.`}
                    </p>
                    <button
                      type="button"
                      onClick={fillEqually}
                      disabled={totalMinor === 0 || selectedIds.length === 0}
                      className="shrink-0 text-xs font-medium text-indigo-600 hover:underline disabled:text-slate-300 disabled:no-underline"
                    >
                      균등하게 채우기
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-500" aria-live="polite">
                  {selectedIds.length === 0
                    ? "분담 인원을 한 명 이상 골라 주세요."
                    : `${selectedIds.length}명이 균등하게 나눠요.${perPerson !== null ? ` 인당 약 ${formatWon(perPerson)}` : ""}`}
                </p>
              )}
              {custom && selectedIds.length === 0 && <p className="mt-2 text-xs text-rose-600">분담 인원을 한 명 이상 골라 주세요.</p>}
              {expense && expense.participants.length === 0 && (
                <p className="mt-1 text-xs text-slate-400">분담 인원을 정하지 않은 지출이에요. 저장하면 정산에 포함돼요.</p>
              )}
            </div>
          </>
        )}
        {members.status === "error" && !expense && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
            일행 정보를 불러오지 못해 결제자·분담 인원을 정하지 않고 저장돼요. 나중에 지출을 수정해 정할 수 있어요.
          </p>
        )}
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
