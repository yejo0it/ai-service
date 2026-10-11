import { useEffect, useState } from "react";
import { searchPlaces, toErrorMessage } from "../api/client";
import type { HotelSuggestion, PlaceKind, Trip } from "../types/api";

/** 여행 기간 중 그날 머무를 것 같은 여행지 (여행지를 순서대로 기간에 고르게 나눈다). 검색 위치 편향에만 쓴다. */
export const cityCodeFor = (trip: Trip, dayIndex: number, dayCount: number) => {
  const destinations = trip.destinations.filter((dest) => dest.city_code);
  if (destinations.length === 0) return undefined;
  return destinations[Math.min(destinations.length - 1, Math.floor((dayIndex * destinations.length) / dayCount))]
    .city_code;
};

interface PlaceSearchOptions {
  query: string;
  /** false면 검색하지 않는다(장소를 이미 골랐을 때 등) */
  enabled: boolean;
  sessionToken: string;
  cityCode?: string;
  kind: PlaceKind;
}

/**
 * 장소 자동완성: 입력어가 바뀌면 300ms 뒤 검색한다(2글자 이상).
 * 장소 직접 추가와 경로 카드 수정이 함께 쓴다.
 */
export default function usePlaceSearch({ query, enabled, sessionToken, cityCode, kind }: PlaceSearchOptions) {
  const [suggestions, setSuggestions] = useState<HotelSuggestion[]>([]);
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    const keyword = query.trim();
    if (!enabled || keyword.length < 2) {
      setSuggestions([]);
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      searchPlaces({ input: keyword, sessionToken, cityCode, kind })
        .then((result) => {
          if (cancelled) return;
          setSuggestions(result);
          setSearchError("");
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setSuggestions([]);
          setSearchError(toErrorMessage(err));
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, enabled, sessionToken, cityCode, kind]);

  return { suggestions, searchError };
}
