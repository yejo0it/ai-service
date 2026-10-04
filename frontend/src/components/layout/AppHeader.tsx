import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import LogoutButton from "../../auth/LogoutButton";
import { PinRouteAppIcon, PinRouteWordmark } from "../../brand/Logo";
import { ROUTES } from "../../routes";
import type { AuthUser } from "../../types/api";
import Avatar from "./Avatar";

interface NavItem {
  label: string;
  /** Font Awesome 클래스 */
  icon: string;
  to?: string;
  /** "/"처럼 하위 경로에서 활성으로 보이면 안 되는 메뉴 */
  end?: boolean;
}

/** 경로가 없는 메뉴는 "준비 중"으로 표시한다. */
const NAV_ITEMS: NavItem[] = [
  { label: "홈", icon: "fas fa-home", to: ROUTES.HOME, end: true },
  { label: "새 여행 만들기", icon: "fas fa-plus", to: ROUTES.ONBOARDING },
  { label: "내 여행", icon: "fas fa-suitcase", to: ROUTES.MY_TRIPS },
  { label: "짐싸기 노트", icon: "fas fa-clipboard-list", to: ROUTES.PACKING },
];

/** 화면에 부를 이름: 이름 → 이메일 아이디 → "여행자" */
export const nicknameOf = (user: AuthUser | null) =>
  user?.name?.trim() || user?.email?.split("@")[0] || "여행자";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:bg-slate-50 hover:text-slate-800"
  }`;

/** 상단 내비게이션 바: 로고 · 메뉴 / 닉네임 · 프로필 · 로그아웃 */
export default function AppHeader() {
  const { user } = useAuth();
  const nickname = nicknameOf(user);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-2 px-4 sm:gap-6 sm:px-6">
        <Link to={ROUTES.HOME} className="flex shrink-0 items-center gap-2" aria-label="PinRoute 홈">
          <PinRouteAppIcon size={30} />
          <PinRouteWordmark className="hidden text-[22px] sm:inline" />
        </Link>

        <nav aria-label="주 메뉴" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {NAV_ITEMS.map((item) =>
            item.to ? (
              <NavLink key={item.label} to={item.to} end={item.end} className={navClass} title={item.label}>
                <i className={`${item.icon} w-4 text-center`} aria-hidden="true" />
                <span className="hidden whitespace-nowrap md:inline">{item.label}</span>
                <span className="sr-only md:hidden">{item.label}</span>
              </NavLink>
            ) : (
              <span
                key={item.label}
                aria-disabled="true"
                title={`${item.label} · 준비 중`}
                className="flex cursor-not-allowed items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-300"
              >
                <i className={`${item.icon} w-4 text-center`} aria-hidden="true" />
                <span className="hidden whitespace-nowrap md:inline">{item.label}</span>
                <span className="sr-only md:hidden">{item.label} (준비 중)</span>
                <span className="hidden rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 lg:inline">
                  준비 중
                </span>
              </span>
            ),
          )}
        </nav>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <Avatar name={nickname} />
          <span className="hidden max-w-[10rem] truncate text-sm font-medium text-slate-700 sm:inline">
            {nickname} 님
          </span>
          <LogoutButton className="border border-slate-200 bg-white hover:border-slate-300" />
        </div>
      </div>
    </header>
  );
}
