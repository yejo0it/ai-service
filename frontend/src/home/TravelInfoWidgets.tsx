import { useEffect, useState, type ReactNode } from "react";
import { getExchangeRates, getWeather, toErrorMessage } from "../api/client";
import type { CityWeather, Destination, ExchangeRatesResponse, Trip } from "../types/api";
import { WEEKDAYS_KO, diffDays, parseISODate } from "../utils/date";
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
    <section aria-label="여행지 날씨" className={CARD_CLASS}>
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
              <div className="mt-4 flex items-center gap-3">
                <span className="text-4xl leading-none" role="img" aria-label={now.label}>
                  {now.emoji}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-slate-500">
                    {cityName} · 지금 {now.label}
                  </p>
                  <p className="text-sm text-slate-500">
                    최고 {formatTemp(todayForecast?.max ?? null)} / 최저 {formatTemp(todayForecast?.min ?? null)}
                  </p>
                </div>
                <span className="text-3xl font-bold tabular-nums text-slate-900">
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

/** 여행 국가 통화 환율 (원화 기준). 국내 여행이면 표시할 통화가 없다. */
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
            <p className="mt-2 text-[11px] text-slate-400">하루 한 번 갱신되는 기준 환율이에요.</p>
          </>
        ))}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * 짐싸기 진행률 (짐싸기 노트 준비 중)
 * ------------------------------------------------------------------ */

const PACKING_STEPS = 5;

/** 짐싸기 체크리스트 진행률 자리. 짐싸기 노트가 생기면 실제 진행률을 붙인다. */
export function PackingWidget() {
  return (
    <section aria-label="짐싸기 진행률" className={CARD_CLASS}>
      <WidgetHeader
        title="짐싸기 진행률"
        aside={
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-400">
            준비 중
          </span>
        }
      />
      <div className="mt-4 flex items-center gap-3" aria-hidden="true">
        <div className="flex flex-1 gap-1">
          {Array.from({ length: PACKING_STEPS }, (_, index) => (
            <span key={index} className="h-2.5 flex-1 rounded-sm bg-slate-100" />
          ))}
        </div>
        <span className="text-sm font-semibold tabular-nums text-slate-300">0%</span>
      </div>
      <p className="mt-3 text-xs text-slate-400">짐싸기 노트가 열리면 준비물 챙김 현황을 여기서 볼 수 있어요.</p>
    </section>
  );
}
