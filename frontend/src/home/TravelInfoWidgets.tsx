import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getExchangeRates, getPackingItems, getWeather, toErrorMessage } from "../api/client";
import { tripTabPath } from "../routes";
import type { CityWeather, Destination, ExchangeRatesResponse, Trip } from "../types/api";
import { WEEKDAYS_KO, diffDays, parseISODate } from "../utils/date";
import {
  convertKrw,
  digitsOf,
  formatAmount,
  formatKrwInput,
  formatUpdatedAt,
  parseKrw,
  pickRate,
  rateLabel,
} from "./exchangeCalc";
import { formatTemp, weatherLook } from "./weatherCodes";

const CARD_CLASS = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

type Loadable<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: T };

/** key가 바뀔 때마다 load를 다시 호출한다(이전 요청 결과는 버린다). */
function useLoad<T>(key: string | null, load: () => Promise<T>): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  useEffect(() => {
    if (key === null) return undefined;
    let cancelled = false;
    setState({ status: "loading" });
    load()
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch((error: unknown) => !cancelled && setState({ status: "error", message: toErrorMessage(error) }));
    return () => {
      cancelled = true;
    };
    // load는 key로 결정되므로 key만 의존한다.
  }, [key]);
  return state;
}

function WidgetHeader({ title, aside }: { title: string; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
      {aside}
    </div>
  );
}

const Skeleton = ({ className }: { className: string }) => (
  <div className={`animate-pulse rounded-xl bg-slate-100 ${className}`} />
);

/* ------------------------------------------------------------------ *
 * 날씨
 * ------------------------------------------------------------------ */

/** 예보에서 보여줄 7일: 여행 날짜가 예보 범위 안이면 여행 첫날부터, 아니면 오늘부터 */
function forecastDays(weather: CityWeather, trip: Trip) {
  const startIndex = weather.daily.findIndex((day) => day.date === trip.start_date);
  const fromTrip = startIndex >= 0;
  const days = weather.daily.slice(fromTrip ? startIndex : 0, (fromTrip ? startIndex : 0) + 7);
  return { days, fromTrip };
}

interface WeatherWidgetProps {
  trip: Trip;
  today: string;
}

/** 여행지 날씨: 현재 날씨·기온·오늘 최고/최저 + 7일 예보. 도시가 여럿이면 도시를 고를 수 있다. */
export function WeatherWidget({ trip, today }: WeatherWidgetProps) {
  const cities = trip.destinations.filter((dest): dest is Destination => Boolean(dest.city_code));
  const [cityCode, setCityCode] = useState(cities[0]?.city_code ?? "");
  // 여행이 바뀌면 첫 도시로 되돌린다.
  useEffect(() => setCityCode(cities[0]?.city_code ?? ""), [trip.id]);
  const state = useLoad(cityCode || null, () => getWeather(cityCode));

  if (cities.length === 0) return null;
  const cityName = cities.find((dest) => dest.city_code === cityCode)?.city ?? cities[0].city;

  return (
    <section aria-label="여행지 날씨" className={`${CARD_CLASS} flex flex-col`}>
      <WidgetHeader
        title="여행지 날씨"
        aside={<span className="text-xs text-slate-400">Open-Meteo</span>}
      />
      {cities.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="날씨를 볼 도시">
          {cities.map((dest) => (
            <button
              key={dest.city_code}
              type="button"
              onClick={() => setCityCode(dest.city_code)}
              aria-pressed={dest.city_code === cityCode}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                dest.city_code === cityCode
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"
              }`}
            >
              {dest.city}
            </button>
          ))}
        </div>
      )}

      {state.status === "loading" && (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-14" />
          <Skeleton className="h-16" />
        </div>
      )}
      {state.status === "error" && <p className="mt-4 text-sm text-slate-500">{state.message}</p>}
      {state.status === "ready" &&
        (() => {
          const weather = state.data;
          const now = weatherLook(weather.current.weather_code);
          const todayForecast = weather.daily.find((day) => day.date === today) ?? weather.daily[0];
          const { days, fromTrip } = forecastDays(weather, trip);
          const daysUntilForecast = diffDays(today, trip.start_date) - (weather.daily.length - 1);
          return (
            <>
              {/* 현재 날씨: 크게 보여주고, 남는 높이는 현재 날씨가 가져가 예보가 카드 맨 아래에 놓인다. */}
              <div className="mt-4 flex flex-1 items-center gap-4 py-2">
                <span className="text-6xl leading-none" role="img" aria-label={now.label}>
                  {now.emoji}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-lg font-medium text-slate-700">
                    {cityName} · 지금 {now.label}
                  </p>
                  <p className="mt-1 text-base text-slate-500">
                    최고 {formatTemp(todayForecast?.max ?? null)} / 최저 {formatTemp(todayForecast?.min ?? null)}
                  </p>
                </div>
                <span className="text-5xl font-bold tabular-nums text-slate-900">
                  {formatTemp(weather.current.temperature)}
                </span>
              </div>

              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="text-xs font-medium text-slate-400">
                  {fromTrip ? "여행 기간 예보" : "이번 주 예보"}
                </p>
                <ol className="mt-2 grid grid-cols-7 gap-1 text-center">
                  {days.map((day) => {
                    const look = weatherLook(day.weather_code);
                    const date = parseISODate(day.date);
                    const inTrip = trip.start_date <= day.date && day.date <= trip.end_date;
                    return (
                      <li
                        key={day.date}
                        title={`${day.date} ${look.label}`}
                        className={`rounded-lg py-1.5 ${inTrip ? "bg-indigo-50" : ""}`}
                      >
                        <span
                          className={`block text-[11px] ${inTrip ? "font-semibold text-indigo-700" : "text-slate-400"}`}
                        >
                          {day.date === today ? "오늘" : WEEKDAYS_KO[date.getDay()]}
                        </span>
                        <span className="my-0.5 block text-lg leading-6" aria-hidden="true">
                          {look.emoji}
                        </span>
                        <span className="block text-[11px] font-semibold tabular-nums text-slate-700">
                          {formatTemp(day.max)}
                        </span>
                        <span className="block text-[11px] tabular-nums text-slate-400">{formatTemp(day.min)}</span>
                      </li>
                    );
                  })}
                </ol>
                {fromTrip && trip.end_date > days[days.length - 1].date && (
                  <p className="mt-2 text-[11px] text-slate-400">
                    나머지 여행 날짜는 예보 범위(16일) 밖이라 아직 볼 수 없어요.
                  </p>
                )}
                {!fromTrip && daysUntilForecast > 0 && (
                  <p className="mt-2 text-[11px] text-slate-400">
                    여행 날짜 예보는 {daysUntilForecast}일 뒤부터 볼 수 있어요.
                  </p>
                )}
              </div>
            </>
          );
        })()}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * 환율
 * ------------------------------------------------------------------ */

/** 국기 이모지(🇯🇵) -> 국가 코드("jp"). 지역 표시 문자 두 개를 알파벳으로 되돌린다. */
const countryCodeOf = (flag: string) =>
  [...flag].map((char) => String.fromCharCode((char.codePointAt(0) ?? 0) - 0x1f1e6 + 97)).join("");

/**
 * 국기. Windows는 국기 이모지를 글자("JP")로 그리므로 이미지로 보여주고,
 * 이미지를 불러오지 못하면 이모지로 대신한다.
 */
function Flag({ flag }: { flag: string }) {
  const [failed, setFailed] = useState(false);
  const code = countryCodeOf(flag);
  if (failed || !/^[a-z]{2}$/.test(code)) {
    return (
      <span className="text-base leading-none" aria-hidden="true">
        {flag}
      </span>
    );
  }
  return (
    <img
      src={`https://flagcdn.com/w40/${code}.png`}
      alt=""
      width={20}
      height={15}
      onError={() => setFailed(true)}
      className="h-[15px] w-5 shrink-0 rounded-[2px] object-cover ring-1 ring-slate-200"
    />
  );
}

const formatKrw = (value: number) =>
  value.toLocaleString("ko-KR", { maximumFractionDigits: value >= 100 ? 1 : 2 });

/**
 * 환율 계산기: 원화를 입력하면 여행 도시의 현지 통화로 바로 환산한다(버튼 없음).
 * 위젯이 이미 불러온 환율만 쓰며 입력할 때 요청하지 않는다. 환율이 없는 통화는 결과를 만들지 않는다.
 */
function ExchangeCalculator({ rates }: { rates: ExchangeRatesResponse["rates"] }) {
  const [digits, setDigits] = useState("");
  // 여행지가 여럿(통화가 둘 이상)이면 고른 여행지의 통화만 보여준다. 기본은 첫 여행지.
  const [selected, setSelected] = useState(rates[0]?.currency ?? "");
  const rate = pickRate(rates, selected);
  const krw = parseKrw(digits);
  const amount = krw === null || !rate ? null : convertKrw(krw, rate);
  if (!rate) return null;

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <label htmlFor="exchange-krw" className="text-xs font-semibold text-slate-500">
        원화 → 현지 통화 계산
      </label>
      {rates.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="환전할 여행지">
          {rates.map((item) => (
            <button
              key={item.currency}
              type="button"
              onClick={() => setSelected(item.currency)}
              aria-pressed={item.currency === rate.currency}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                item.currency === rate.currency
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"
              }`}
            >
              {rateLabel(item)}
            </button>
          ))}
        </div>
      )}
      <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100">
        <span className="shrink-0 text-sm font-semibold text-slate-400" aria-hidden="true">
          ₩
        </span>
        <input
          id="exchange-krw"
          inputMode="numeric"
          autoComplete="off"
          value={formatKrwInput(digits)}
          onChange={(event) => setDigits(digitsOf(event.target.value))}
          placeholder="환전할 원화 금액"
          className="min-w-0 flex-1 bg-transparent text-right text-sm font-semibold tabular-nums text-slate-900 placeholder:font-normal placeholder:text-slate-400 focus:outline-none"
        />
        <span className="shrink-0 text-xs text-slate-400">원</span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5" aria-live="polite">
        <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
          <Flag flag={rate.flag} />
          <span className="font-semibold text-slate-800">{rate.currency}</span>
        </span>
        <span className="shrink-0 text-sm font-bold tabular-nums text-slate-900">
          {amount === null ? <span className="font-normal text-slate-300">–</span> : `${formatAmount(amount, rate.currency)} ${rate.currency}`}
        </span>
      </div>
    </div>
  );
}

/** 여행 국가 통화 환율 (원화 기준)과 환율 계산기. 국내 여행이면 표시할 통화가 없다. */
export function ExchangeWidget({ trip }: { trip: Trip }) {
  const cityCodes = trip.destinations.map((dest) => dest.city_code).filter(Boolean);
  const state = useLoad<ExchangeRatesResponse>(cityCodes.join(",") || null, () => getExchangeRates(cityCodes));
  if (cityCodes.length === 0) return null;

  return (
    <section aria-label="환율" className={CARD_CLASS}>
      <WidgetHeader
        title="환율"
        aside={
          <a
            href="https://www.exchangerate-api.com"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            ExchangeRate-API
          </a>
        }
      />
      {state.status === "loading" && <Skeleton className="mt-4 h-10" />}
      {state.status === "error" && <p className="mt-4 text-sm text-slate-500">{state.message}</p>}
      {state.status === "ready" &&
        (state.data.rates.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">국내 여행이라 환율 정보가 없어요.</p>
        ) : (
          <>
            <ul className="mt-3 space-y-2">
              {state.data.rates.map((rate) => (
                <li key={rate.currency} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2.5">
                  <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
                    <Flag flag={rate.flag} />
                    <span className="font-semibold text-slate-800">{rate.currency}</span>
                    <span className="truncate">
                      {rate.unit.toLocaleString("ko-KR")}
                      {rate.name}
                    </span>
                  </span>
                  <span className="shrink-0 text-sm font-bold tabular-nums text-slate-900">
                    {formatKrw(rate.krw)}원
                  </span>
                </li>
              ))}
            </ul>
            <ExchangeCalculator rates={state.data.rates} />
            <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
              하루 한 번 갱신되는 기준 환율이에요.
              {formatUpdatedAt(state.data.updated_at) && ` 마지막 갱신 ${formatUpdatedAt(state.data.updated_at)}`}
              <br />
              실제 환전 금액은 환전소·카드사 수수료와 환율 우대 등에 따라 달라질 수 있어요.
            </p>
          </>
        ))}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * 여행 준비 현황
 * ------------------------------------------------------------------ */

/**
 * 여행 준비 현황 묶음. 지금은 체크리스트 카드 하나이며, 나중에 경비 사용 현황 같은 카드를
 * 자식으로 더하면 2열로 나란히 놓인다(카드가 하나일 때는 가로로 꽉 채운다).
 */
export function PrepStatus({ trip }: { trip: Trip }) {
  return (
    <section aria-label="여행 준비 현황" className="grid gap-4 md:grid-cols-2 md:[&>:only-child]:col-span-2">
      <PackingWidget trip={trip} />
    </section>
  );
}

/** 여행 체크리스트(준비물·해야 할 일) 완료율과 남은 항목. 홈에 올 때마다 새로 불러와 체크한 결과를 보여준다. */
export function PackingWidget({ trip }: { trip: Trip }) {
  const state = useLoad(String(trip.id), () => getPackingItems(trip.id));
  const items = state.status === "ready" ? state.data : [];
  const doneCount = items.filter((item) => item.done).length;
  const percent = items.length === 0 ? 0 : Math.round((doneCount / items.length) * 100);

  return (
    <Link
      to={tripTabPath(trip.id, "checklist")}
      aria-label="여행 체크리스트 바로가기"
      className={`${CARD_CLASS} block transition-colors hover:border-slate-300`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <i className="fas fa-clipboard-list text-slate-500" aria-hidden="true" />
          여행 체크리스트
        </span>
        <span className="flex items-center gap-1 text-xs font-medium text-indigo-600">
          바로가기
          <i className="fas fa-arrow-right text-[10px]" aria-hidden="true" />
        </span>
      </div>
      {state.status === "loading" ? (
        <Skeleton className="mt-4 h-16" />
      ) : state.status === "error" ? (
        <p className="mt-3 text-sm text-rose-600">{state.message}</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">아직 체크리스트가 비어 있어요. 준비물과 할 일을 추가해 보세요.</p>
      ) : (
        <>
          <p className="mt-3 text-2xl font-extrabold tabular-nums text-slate-900">
            {doneCount} <span className="text-slate-400">/ {items.length}</span>
          </p>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label="체크리스트 완료율"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="h-full rounded-full bg-indigo-500 transition-all duration-300" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {items.length === doneCount ? "모두 준비했어요!" : `${items.length - doneCount}개 남았어요`}
          </p>
        </>
      )}
    </Link>
  );
}
