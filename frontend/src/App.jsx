import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import OnboardingWizard from "./onboarding/OnboardingWizard";

/** 온보딩 완료 후 도착 화면 (동선 최적화 화면이 붙기 전 임시 요약) */
function TripCreated() {
  const { state } = useLocation();
  const trip = state?.trip;

  if (!trip) return <Navigate to="/onboarding" replace />;

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
      <Route path="/" element={<Navigate to="/onboarding" replace />} />
      <Route
        path="/onboarding"
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
