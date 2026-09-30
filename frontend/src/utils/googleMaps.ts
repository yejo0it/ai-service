/**
 * Google Maps JavaScript API를 한 번만 불러온다.
 * 키는 브라우저용(VITE_GOOGLE_MAPS_API_KEY)이며, 없으면 지도 대신 안내를 보여준다.
 */
const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "";
const CALLBACK = "__pinrouteMapsReady";

let loading: Promise<typeof google.maps> | null = null;

export const hasMapsKey = () => Boolean(API_KEY);

export function loadGoogleMaps(): Promise<typeof google.maps> {
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    if (!API_KEY) {
      reject(new Error("지도 키가 설정되지 않았어요."));
      return;
    }
    const callbacks = window as unknown as Record<string, () => void>;
    callbacks[CALLBACK] = () => resolve(google.maps);
    // 키가 잘못됐거나 리퍼러가 허용되지 않으면 Google이 이 함수를 부른다(스크립트 로드는 성공한 뒤).
    callbacks.gm_authFailure = () => window.dispatchEvent(new Event("pinroute:maps-auth-failure"));
    const params = new URLSearchParams({ key: API_KEY, callback: CALLBACK, language: "ko", region: "KR", v: "weekly" });
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
    script.async = true;
    script.onerror = () => {
      loading = null;
      reject(new Error("지도를 불러오지 못했어요."));
    };
    document.head.appendChild(script);
  });
  return loading;
}
