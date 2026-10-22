import { Navigate, Route, Routes } from "react-router-dom";
import FindIdPage from "./auth/FindIdPage";
import LoginPage from "./auth/LoginPage";
import ResetPasswordPage, { ResetPasswordNewPage } from "./auth/ResetPasswordPage";
import SignupPage from "./auth/SignupPage";
import SocialCallback from "./auth/SocialCallback";
import GuestOnlyRoute from "./components/GuestOnlyRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./components/layout/AppLayout";
import HomePage from "./home/HomePage";
import MyPage from "./mypage/MyPage";
import PackingRedirect from "./packing/PackingRedirect";
import DevReservationsPage from "./reservations/DevReservationsPage";
import { ROUTES, type HomeLocationState } from "./routes";
import MyTripsPage from "./trips/MyTripsPage";
import InviteAcceptPage from "./trips/InviteAcceptPage";
import TripDetailPage from "./trips/TripDetailPage";

export default function App() {
  return (
    <Routes>
      {/* 로그인한 사용자는 원래 가려던 화면(또는 홈)으로 보낸다. */}
      <Route element={<GuestOnlyRoute />}>
        <Route path={ROUTES.LOGIN} element={<LoginPage />} />
        <Route path={ROUTES.SIGNUP} element={<SignupPage />} />
      </Route>

      <Route path={ROUTES.FIND_ID} element={<FindIdPage />} />
      <Route path={ROUTES.RESET_PASSWORD} element={<ResetPasswordPage />} />
      <Route path={ROUTES.RESET_PASSWORD_NEW} element={<ResetPasswordNewPage />} />
      <Route path={ROUTES.SOCIAL_CALLBACK} element={<SocialCallback />} />

      {/* 로그인해야 볼 수 있는 화면. 미로그인이면 로그인 화면으로 보내고 원래 경로를 기억한다.
          상단 내비게이션 바(AppLayout) 아래에 그린다. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path={ROUTES.HOME} element={<HomePage />} />
          {/* 새 여행 만들기는 홈의 모달로 연다. 예전 주소는 홈으로 보내 모달을 띄운다. */}
          <Route
            path={ROUTES.ONBOARDING}
            element={<Navigate to={ROUTES.HOME} replace state={{ newTrip: true } satisfies HomeLocationState} />}
          />
          <Route path={ROUTES.MY_TRIPS} element={<MyTripsPage />} />
          <Route path={ROUTES.TRIP_DETAIL} element={<TripDetailPage />} />
          <Route path={ROUTES.TRIP_INVITE} element={<InviteAcceptPage />} />
          {/* 여행 체크리스트는 여행 상세의 탭이다. 예전 주소는 그 여행의 체크리스트 탭으로 보낸다. */}
          <Route path={ROUTES.PACKING} element={<PackingRedirect />} />
          <Route path={ROUTES.MYPAGE} element={<MyPage />} />
          {/* 개발용 확인 화면: 개발 모드에서만 등록하므로 운영 빌드에서는 이 주소가 없다. */}
          {import.meta.env.DEV && <Route path={ROUTES.DEV_RESERVATIONS} element={<DevReservationsPage />} />}
        </Route>
      </Route>
    </Routes>
  );
}
