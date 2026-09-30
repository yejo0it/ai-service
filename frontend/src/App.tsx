import { Route, Routes, useNavigate } from "react-router-dom";
import FindIdPage from "./auth/FindIdPage";
import LoginPage from "./auth/LoginPage";
import ResetPasswordPage, { ResetPasswordNewPage } from "./auth/ResetPasswordPage";
import SignupPage from "./auth/SignupPage";
import SocialCallback from "./auth/SocialCallback";
import GuestOnlyRoute from "./components/GuestOnlyRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./components/layout/AppLayout";
import HomePage from "./home/HomePage";
import OnboardingWizard from "./onboarding/OnboardingWizard";
import { ROUTES, tripDetailPath } from "./routes";
import MyTripsPage from "./trips/MyTripsPage";
import TripDetailPage, { type TripDetailState } from "./trips/TripDetailPage";

export default function App() {
  const navigate = useNavigate();

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
          <Route
            path={ROUTES.ONBOARDING}
            element={
              <OnboardingWizard
                onComplete={(trip) => {
                  const state: TripDetailState = { trip, created: true };
                  navigate(tripDetailPath(trip.id), { state, replace: true });
                }}
              />
            }
          />
          <Route path={ROUTES.MY_TRIPS} element={<MyTripsPage />} />
          <Route path={ROUTES.TRIP_DETAIL} element={<TripDetailPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
