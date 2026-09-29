import { useCallback, useEffect, useState } from "react";
import { listTrips, toErrorMessage } from "../api/client";
import type { Trip } from "../types/api";

export type TripsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; trips: Trip[] };

/** 로그인한 회원의 여행 목록. 시작일 순으로 정렬해 돌려준다. */
export default function useTrips(): TripsState & { reload: () => void } {
  const [state, setState] = useState<TripsState>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    listTrips()
      .then((trips) => {
        if (cancelled) return;
        const sorted = [...trips].sort((a, b) => a.start_date.localeCompare(b.start_date));
        setState({ status: "ready", trips: sorted });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: "error", message: toErrorMessage(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  const reload = useCallback(() => setVersion((current) => current + 1), []);
  return { ...state, reload };
}
