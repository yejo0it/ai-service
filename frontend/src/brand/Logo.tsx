/**
 * PinRoute 로고 (디자인 핸드오프 1b "경로로 쓴 P").
 * 출발점에서 올라간 경로가 한 바퀴 돌아 P를 만들고, 오른쪽 아래 작은 점이 다음 목적지다.
 */

const MARK_PATH = "M22 50 L22 14 L33 14 A11 11 0 0 1 33 36 L22 36";

interface PinRouteMarkProps {
  size?: number;
  /** 경로·출발점 색 (색 배경 위 #FFFFFF, 흰 배경 위 #4F46E5) */
  color?: string;
  className?: string;
}

/** 마크만. color는 경로·출발점 색(색 배경 위 #FFFFFF, 흰 배경 위 #4F46E5). */
export function PinRouteMark({ size = 64, color = "#FFFFFF", className = "" }: PinRouteMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={MARK_PATH}
        fill="none"
        stroke={color}
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="22" cy="50" r="5" fill={color} />
      <circle cx="44" cy="50" r="3.5" fill="#A5B4FC" />
    </svg>
  );
}

/**
 * 타일 안의 마크. 112px 기준 radius 30px(≈26.8%).
 * inverse는 인디고 배경 위에 둘 때 쓰는 흰 타일 + 인디고 마크다.
 */
interface PinRouteAppIconProps {
  size?: number;
  inverse?: boolean;
  className?: string;
}

export function PinRouteAppIcon({ size = 112, inverse = false, className = "" }: PinRouteAppIconProps) {
  return (
    <span
      className={`inline-flex items-center justify-center ${
        inverse ? "bg-white" : "bg-indigo-600"
      } ${className}`}
      style={{ width: size, height: size, borderRadius: size * 0.268 }}
    >
      <PinRouteMark size={size * 0.75} color={inverse ? "#4F46E5" : "#FFFFFF"} />
    </span>
  );
}

/** 워드마크 "Pin" + "Route". tone="light"는 색 배경 위(흰색 + 인디고-200). */
interface PinRouteWordmarkProps {
  tone?: "dark" | "light";
  className?: string;
}

export function PinRouteWordmark({ tone = "dark", className = "" }: PinRouteWordmarkProps) {
  const [pin, route] =
    tone === "light" ? ["text-white", "text-indigo-200"] : ["text-slate-900", "text-indigo-600"];
  return (
    <span className={`font-brand font-extrabold tracking-[-0.03em] ${className}`}>
      <span className={pin}>Pin</span>
      <span className={route}>Route</span>
    </span>
  );
}
