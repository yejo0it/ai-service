/** WMO 날씨 코드(Open-Meteo weather_code) -> 아이콘·한글 설명 */
export interface WeatherLook {
  emoji: string;
  label: string;
}

const LOOKS: [codes: number[], look: WeatherLook][] = [
  [[0], { emoji: "☀️", label: "맑음" }],
  [[1], { emoji: "🌤️", label: "대체로 맑음" }],
  [[2], { emoji: "⛅", label: "구름 조금" }],
  [[3], { emoji: "☁️", label: "흐림" }],
  [[45, 48], { emoji: "🌫️", label: "안개" }],
  [[51, 53, 55, 56, 57], { emoji: "🌦️", label: "이슬비" }],
  [[61, 63, 65, 66, 67, 80, 81, 82], { emoji: "🌧️", label: "비" }],
  [[71, 73, 75, 77, 85, 86], { emoji: "❄️", label: "눈" }],
  [[95, 96, 99], { emoji: "⛈️", label: "뇌우" }],
];

export function weatherLook(code: number | null): WeatherLook {
  if (code === null) return { emoji: "🌡️", label: "정보 없음" };
  return LOOKS.find(([codes]) => codes.includes(code))?.[1] ?? { emoji: "🌡️", label: "알 수 없음" };
}

/** 21.6 -> "22°" */
export const formatTemp = (value: number | null) => (value === null ? "-" : `${Math.round(value)}°`);
