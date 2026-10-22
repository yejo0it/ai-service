import { useEffect, useRef, useState, type ReactNode } from "react";
import { getPlacePhoto } from "../api/client";
import type { ItineraryItem, PlacePhotoInfo } from "../types/api";

/**
 * 여행 경로 장소의 Google Places 대표 사진.
 * - 사진은 화면에 보일 때만 요청한다(지연 로딩). 같은 장소가 여러 카드에 있어도 한 번만 묻는다(이 화면을 보는 동안 메모리에만 둔다).
 * - 사진이 없거나 불러오지 못하면 기존 종류 아이콘을 그대로 보여 일정 표시에 영향이 없다.
 * - 사진은 모든 카드에서 같은 크기의 정사각형이며, 가운데 위쪽을 기준으로 맞춰 자른다(건물·탑의 윗부분이 잘리지 않게).
 * - Google 정책에 따라 카드 오른쪽 아래에 작성자와 Google Maps 출처를 한 줄로 표시한다.
 */

/** 사진을 보여 줄 카드: 장소가 Google 장소와 연결된 카드(항공편 제외) */
export const hasPlacePhoto = (item: Pick<ItineraryItem, "kind" | "place_id">) =>
  Boolean(item.place_id) && item.kind !== "flight";

// 장소 번호 -> 응답. 새로고침하면 사라지고 서버·저장소에 남기지 않는다.
const requests = new Map<string, Promise<PlacePhotoInfo | null>>();

function fetchPhoto(placeId: string): Promise<PlacePhotoInfo | null> {
  let request = requests.get(placeId);
  if (!request) {
    request = getPlacePhoto(placeId).catch(() => null);
    requests.set(placeId, request);
    // 일시적인 오류·상한 응답은 오래 붙들지 않도록 실패하면 다음에 다시 시도할 수 있게 지운다.
    request.then((info) => {
      if (!info || info.status === "error") requests.delete(placeId);
    });
  }
  return request;
}

type PhotoState = { status: "idle" } | { status: "loading" } | { status: "none" } | { status: "ready"; info: PlacePhotoInfo };

/** 카드가 화면에 들어오면 사진 정보를 한 번 받는다. 반환한 ref를 카드 요소에 단다. */
export function usePlacePhoto(placeId: string, enabled: boolean) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);
  const [state, setState] = useState<PhotoState>({ status: "idle" });

  useEffect(() => {
    if (!enabled || visible) return undefined;
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [enabled, visible]);

  useEffect(() => {
    if (!enabled || !visible) return undefined;
    let cancelled = false;
    setState({ status: "loading" });
    fetchPhoto(placeId).then((info) => {
      if (cancelled) return;
      setState(info && info.status === "ok" && info.photo_uri ? { status: "ready", info } : { status: "none" });
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, visible, placeId]);

  return { ref, state };
}

/** 모든 카드에서 같은 크기의 정사각형(모바일 96px, 넓은 화면 112px) */
const PHOTO_BOX = "h-24 w-24 sm:h-28 sm:w-28";

interface PlaceThumbProps {
  state: PhotoState;
  title: string;
  /** 사진이 없을 때 보여 줄 종류 아이콘 */
  fallback: ReactNode;
}

/** 일정 카드 왼쪽 썸네일(정사각). 로딩 중에는 스켈레톤, 사진이 없거나 실패하면 종류 아이콘 */
export function PlaceThumb({ state, title, fallback }: PlaceThumbProps) {
  const [failed, setFailed] = useState(false);
  if (state.status === "ready" && !failed) {
    return (
      <img
        src={state.info.photo_uri ?? ""}
        alt={`${title} 사진`}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={`${PHOTO_BOX} shrink-0 self-start rounded-xl bg-slate-100 object-cover object-top`}
      />
    );
  }
  if (state.status === "loading") {
    return <span className={`${PHOTO_BOX} shrink-0 animate-pulse self-start rounded-xl bg-slate-100`} aria-hidden="true" />;
  }
  return <>{fallback}</>;
}

/** 카드가 사진 출처를 보일 때(불러오는 중이거나 사진이 있을 때) 아래쪽에 비워 둘 여백 */
export const hasCreditRow = (state: PhotoState) => state.status === "loading" || state.status === "ready";

/**
 * 사진 출처 한 줄: "사진: 작성자 · Google Maps" (작성자·Google Maps는 원본으로 연결).
 * 카드(relative) 안 오른쪽 아래에 놓는다.
 */
export function PlaceCredit({ state }: { state: PhotoState }) {
  if (state.status !== "ready") return null;
  const { attributions, maps_uri: mapsUri } = state.info;
  const author = attributions[0];
  const link = "underline-offset-2 hover:text-slate-600 hover:underline";
  return (
    <p className="absolute bottom-2 right-4 max-w-[70%] truncate text-[10px] leading-tight text-slate-400">
      사진:{" "}
      {author &&
        (author.uri ? (
          <a href={author.uri} target="_blank" rel="noopener noreferrer" className={link}>
            {author.name}
          </a>
        ) : (
          author.name
        ))}
      {author && " · "}
      {mapsUri ? (
        <a href={mapsUri} target="_blank" rel="noopener noreferrer" className={link}>
          Google Maps
        </a>
      ) : (
        "Google Maps"
      )}
    </p>
  );
}
