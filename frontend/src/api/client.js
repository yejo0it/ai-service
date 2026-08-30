import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env?.VITE_API_URL ?? "http://localhost:8003/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 10000,
});

/** 온보딩 Step 1~3을 한 번에 저장 (hotels 포함 가능) */
export const createTrip = (payload) =>
  api.post("/trips/", payload).then((res) => res.data);

/** 단계별 저장이 필요할 때: Step 3만 따로 저장 */
export const createHotel = (tripId, payload) =>
  api.post(`/trips/${tripId}/hotels/`, payload).then((res) => res.data);

/** DRF의 필드 에러({field: [msg]})를 사람이 읽을 수 있는 문자열로 변환 */
export function toErrorMessage(error) {
  const data = error?.response?.data;
  if (!data) return "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  if (typeof data === "string") return data;

  const flatten = (value) => {
    if (Array.isArray(value)) return value.map(flatten).join(" ");
    if (value && typeof value === "object")
      return Object.values(value).map(flatten).join(" ");
    return String(value);
  };
  return flatten(data) || "요청을 처리하지 못했습니다.";
}

export default api;
