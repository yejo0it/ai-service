import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { acceptTripInvitation, toErrorMessage } from "../api/client";
import FullScreenLoader from "../components/FullScreenLoader";
import { PAGE_CONTAINER_CLASS } from "../components/layout/pageContainer";
import { ROUTES, tripDetailPath } from "../routes";

/**
 * `/trips/invite/:token` 초대 링크.
 * 로그인해야 들어올 수 있어(ProtectedRoute), 로그인하지 않았으면 이 주소를 기억한 채 로그인·회원가입으로 가고
 * 마치면 다시 여기로 와서 일행으로 들어간 뒤 여행 상세로 이동한다.
 */
export default function InviteAcceptPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const requested = useRef(false);

  useEffect(() => {
    // StrictMode에서 effect가 두 번 돌아도 한 번만 요청한다.
    if (requested.current) return;
    requested.current = true;
    acceptTripInvitation(token)
      .then(({ trip_id }) => navigate(tripDetailPath(trip_id), { replace: true }))
      .catch((err: unknown) => setError(toErrorMessage(err)));
  }, [token, navigate]);

  if (!error) return <FullScreenLoader message="초대받은 여행에 들어가는 중이에요..." />;

  return (
    <div className={`${PAGE_CONTAINER_CLASS} py-20`}>
      <div className="mx-auto flex max-w-md flex-col items-center text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
          <i className="fas fa-unlink" aria-hidden="true" />
        </span>
        <h1 className="mt-4 text-lg font-bold text-slate-900">초대 링크를 열 수 없어요</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{error}</p>
        <Link
          to={ROUTES.HOME}
          className="mt-6 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          홈으로 가기
        </Link>
      </div>
    </div>
  );
}
