import { Outlet } from "react-router-dom";
import AppHeader from "./AppHeader";

/** 로그인 후 화면 공통 틀: 상단 내비게이션 바 + 본문 */
export default function AppLayout() {
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main>
        <Outlet />
      </main>
    </div>
  );
}
