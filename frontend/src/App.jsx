import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import FindIdPage from "./auth/FindIdPage";
import LoginPage from "./auth/LoginPage";
import ResetPasswordPage, { ResetPasswordNewPage } from "./auth/ResetPasswordPage";
import SignupPage from "./auth/SignupPage";
import SocialCallback from "./auth/SocialCallback";
import OnboardingWizard from "./onboarding/OnboardingWizard";
import { ROUTES } from "./routes";

/** 온보딩 완료 후 도착 화면 (동선 최적화 화면이 붙기 전 임시 요약) */
function TripCreated() {
  const { state } = useLocation();
  const trip = state?.trip;

  if (!trip) return <Navigate to={ROUTES.HOME} replace />;

  return (
    <div className="flex min-h-screen justify-center bg-slate-50 px-4 py-8 sm:items-center">
      <div className="w-full max-w-md rounded-2xl bg-white p-7 shadow-sm ring-1 ring-slate-100">
        <h1 className="text-xl font-bold text-slate-900">
          {trip.destination_label} 여행이 만들어졌어요
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          {trip.start_date} ~ {trip.end_date} · {trip.nights}박
        </p>
        <ul className="mt-5 space-y-2 text-sm text-slate-700">
          <li>항공권 {trip.has_flight ? "등록됨" : "미등록"}</li>
          <li>
            숙소 {trip.hotels?.length ? `${trip.hotels.length}곳 등록됨` : "미등록"}
          </li>
        </ul>
      </div>
    </div>
  );
}

export default function App() {
  const navigate = useNavigate();

  return (
    <Routes>
      {/* TODO 홈 화면이 생기면 <Route path="/" element={<HomePage />} /> 로 바꾸기 */}
      <Route path="/" element={<Navigate to={ROUTES.LOGIN} replace />} />
      <Route path={ROUTES.LOGIN} element={<LoginPage />} />
      <Route path={ROUTES.SIGNUP} element={<SignupPage />} />
      <Route path={ROUTES.FIND_ID} element={<FindIdPage />} />
      <Route path={ROUTES.RESET_PASSWORD} element={<ResetPasswordPage />} />
      <Route path={ROUTES.RESET_PASSWORD_NEW} element={<ResetPasswordNewPage />} />
      <Route path={ROUTES.SOCIAL_CALLBACK} element={<SocialCallback />} />
      <Route
        path={ROUTES.HOME}
        element={
          <OnboardingWizard
            onComplete={(trip) =>
              navigate(`/trips/${trip.id}`, { state: { trip }, replace: true })
            }
          />
        }
      />
      <Route path="/trips/:tripId" element={<TripCreated />} />
    </Routes>
  );
}
