import { useEffect, useRef, useState } from "react";
import { hasMapsKey, loadGoogleMaps } from "../utils/googleMaps";
import type { RoutePoint, StopKind } from "./tripDays";

/** 핀 색 (지도 마커는 CSS 클래스를 못 쓰므로 hex, 일정 카드의 번호는 같은 색의 Tailwind 클래스) */
export const PIN_STYLE: Record<StopKind, { hex: string; badge: string; label: string }> = {
  airport: { hex: "#6366f1", badge: "bg-indigo-500", label: "공항" },
  hotel: { hex: "#f59e0b", badge: "bg-amber-500", label: "숙소" },
  place: { hex: "#10b981", badge: "bg-emerald-500", label: "장소" },
  city: { hex: "#64748b", badge: "bg-slate-500", label: "여행지" },
};

interface TripMapProps {
  /** 이동 순서대로 번호가 매겨진 지점 (일정 카드 순서) */
  points: RoutePoint[];
  /** 지도 높이 등 바깥 크기 */
  className?: string;
}

/**
 * 여행 지도: 이동 순서 번호가 적힌 핀과 순서대로 잇는 점선.
 * 번호와 위치 설명은 일정 카드에 함께 표시하므로 지도 아래 목록은 두지 않는다.
 * 지도 키가 없거나 불러오지 못하면 지도 자리에 안내를 보여준다.
 */
export default function TripMap({ points, className = "h-72 sm:h-96" }: TripMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(
    hasMapsKey() ? "" : "지도 키(GOOGLE_MAPS_API_KEY)를 설정하면 지도가 표시돼요.",
  );

  useEffect(() => {
    if (!hasMapsKey() || points.length === 0) return undefined;
    let cancelled = false;
    const overlays: { setMap: (map: google.maps.Map | null) => void }[] = [];
    const onAuthFailure = () => setError("지도 키가 올바르지 않거나 이 주소에서 허용되지 않았어요.");
    window.addEventListener("pinroute:maps-auth-failure", onAuthFailure);

    loadGoogleMaps()
      .then((maps) => {
        if (cancelled || !mapRef.current) return;
        const map = new maps.Map(mapRef.current, {
          disableDefaultUI: true,
          zoomControl: true,
          clickableIcons: false,
          gestureHandling: "cooperative",
        });
        const bounds = new maps.LatLngBounds();
        points.forEach((point) => {
          const position = { lat: point.lat, lng: point.lng };
          bounds.extend(position);
          overlays.push(
            new maps.Marker({
              map,
              position,
              title: `${point.order}. ${point.label}`,
              zIndex: point.order,
              label: { text: String(point.order), color: "#ffffff", fontSize: "12px", fontWeight: "700" },
              icon: {
                path: maps.SymbolPath.CIRCLE,
                scale: 13,
                fillColor: PIN_STYLE[point.kind].hex,
                fillOpacity: 1,
                strokeColor: "#ffffff",
                strokeWeight: 2,
              },
            }),
          );
        });
        if (points.length > 1) {
          // 이동 순서를 점선으로 잇는다.
          overlays.push(
            new maps.Polyline({
              map,
              path: points.map((point) => ({ lat: point.lat, lng: point.lng })),
              geodesic: true,
              strokeOpacity: 0,
              icons: [
                {
                  icon: { path: "M 0,-1 0,1", strokeOpacity: 0.7, strokeColor: "#6366f1", scale: 3 },
                  offset: "0",
                  repeat: "14px",
                },
              ],
            }),
          );
          map.fitBounds(bounds, 48);
        } else {
          map.setCenter(bounds.getCenter());
          map.setZoom(11);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "지도를 불러오지 못했어요.");
      });

    return () => {
      cancelled = true;
      window.removeEventListener("pinroute:maps-auth-failure", onAuthFailure);
      overlays.forEach((overlay) => overlay.setMap(null));
    };
  }, [points]);

  return (
    <div className={`relative overflow-hidden rounded-xl bg-slate-100 ${className}`}>
      <div ref={mapRef} className="h-full w-full" />
      {(error || points.length === 0) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-50 px-6 text-center">
          <i className="fas fa-map-marked-alt text-2xl text-slate-300" aria-hidden="true" />
          <p className="text-sm text-slate-500">
            {points.length === 0 ? "지도에 표시할 위치가 없어요." : error}
          </p>
        </div>
      )}
    </div>
  );
}
