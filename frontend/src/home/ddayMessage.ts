import { tripCities } from "../trips/tripUtils";
import type { Trip } from "../types/api";
import { diffDays } from "../utils/date";

/** 홈 화면 안내 문구. 두 줄로 나뉘어 보일 때 앞 문장은 윗줄에 남고 뒤 문장이 통째로 아랫줄로 내려가도록 문장별로 나눠 둔다. */
export interface DDayMessage {
  lead: string;
  tail: string;
}

/**
 * 출발까지 남은 일수(days, 오늘이면 0)에 맞는 홈 화면 안내 문구.
 * 특정 날짜가 아니라 구간별로 고르고, 구간 안에서는 실제 남은 일수를 문구에 넣는다.
 */
export function ddayMessage(days: number, destination: string): DDayMessage {
  if (days <= 0) return { lead: "드디어 여행 당일!", tail: "즐거운 여행 되세요 ✈️" };
  if (days === 1) return { lead: "여행이 하루 앞으로 다가왔어요!", tail: "두근두근, 내일이면 출발이에요 💕" };
  if (days === 2) return { lead: "여행이 딱 이틀 남았어요!", tail: "설레서 잠은 잘 오려나요? 💓" };
  if (days <= 6) {
    return { lead: `여행이 ${days}일 앞으로 다가왔어요!`, tail: "필요한 건 다 챙겼는지 다시 한번 확인해 볼까요?" };
  }
  if (days === 7) return { lead: "벌써 일주일 앞으로 다가왔어요!", tail: "눈 깜빡하면 공항이에요 ✈️" };
  if (days < 30) return { lead: `여행이 ${days}일 앞으로 다가왔어요!`, tail: "눈 깜빡하면 공항이에요 ✈️" };
  if (days < 60) return { lead: `여행이 ${days}일 남았어요!`, tail: `마음은 벌써 ${destination}에서 뛰어노는 중 🏃` };
  if (days < 100) return { lead: `여행까지 ${days}일 남았어요.`, tail: "슬슬 여행 계획을 세워볼까요?" };
  return { lead: `여행까지 ${days}일!`, tail: "벌써부터 설레기 시작하지 않나요?" };
}

/**
 * 오늘 이후 출발하는 여행 중 가장 가까운 여행의 안내 문구. 없으면 null(기본 문구를 쓴다).
 * 이미 출발해 여행 중이거나 끝난 여행은 대상이 아니다. 여행지가 여러 곳이면 첫 번째 도시를 대표로 쓴다.
 */
export function homeDDayMessage(trips: Trip[], today: string): DDayMessage | null {
  const trip = trips
    .filter((candidate) => candidate.start_date >= today)
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];
  if (!trip) return null;
  return ddayMessage(diffDays(today, trip.start_date), tripCities(trip)[0] ?? "여행지");
}
