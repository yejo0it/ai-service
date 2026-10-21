import { Navigate, useSearchParams } from "react-router-dom";
import { PAGE_CONTAINER_CLASS } from "../components/layout/pageContainer";
import { ROUTES, tripTabPath } from "../routes";
import { nextTrip } from "../trips/tripUtils";
import useTrips from "../trips/useTrips";
import { todayISODate } from "../utils/date";

/**
 * `/packing` 예전 여행 체크리스트 주소. 여행 체크리스트는 여행 상세의 탭이 되어,
 * `?trip=ID`의 여행(없으면 다가오는 여행)의 체크리스트 탭으로 보낸다. 여행이 없으면 내 여행으로 보낸다.
 */
export default function PackingRedirect() {
  const trips = useTrips();
  const [params] = useSearchParams();

  if (trips.status === "loading") {
    return (
      <div className={`${PAGE_CONTAINER_CLASS} py-8`}>
        <div className="h-64 animate-pulse rounded-2xl bg-slate-200/70" />
      </div>
    );
  }
  if (trips.status === "error") {
    return <p className={`${PAGE_CONTAINER_CLASS} py-8 text-sm text-rose-600`}>{trips.message}</p>;
  }

  const target =
    trips.trips.find((trip) => String(trip.id) === params.get("trip")) ??
    nextTrip(trips.trips, todayISODate()) ??
    trips.trips[trips.trips.length - 1];
  return <Navigate to={target ? tripTabPath(target.id, "checklist") : ROUTES.MY_TRIPS} replace />;
}
