import { useState } from "react";
import { getSession } from "./session";
import useLogout from "./useLogout";

/** 로그인한 경우에만 보이는 로그아웃 버튼. 어느 화면에 두어도 같은 흐름(useLogout)을 탄다. */
interface LogoutButtonProps {
  className?: string;
}

export default function LogoutButton({ className = "" }: LogoutButtonProps) {
  const logout = useLogout();
  const [pending, setPending] = useState(false);
  const session = getSession();
  if (!session) return null;

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        setPending(true);
        logout();
      }}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50 ${className}`}
    >
      <i className="fas fa-sign-out-alt" aria-hidden="true" />
      로그아웃
    </button>
  );
}
