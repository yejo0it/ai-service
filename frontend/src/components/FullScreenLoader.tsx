interface FullScreenLoaderProps {
  message?: string;
}

/** 인증 확인·소셜 로그인 처리 중에 화면 전체를 대신하는 로딩 표시 */
export default function FullScreenLoader({ message }: FullScreenLoaderProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-screen flex-col items-center justify-center gap-3 bg-white"
    >
      <i className="fas fa-circle-notch fa-spin text-2xl text-indigo-500" aria-hidden="true" />
      {message ? (
        <p className="text-sm text-slate-500">{message}</p>
      ) : (
        <span className="sr-only">불러오는 중</span>
      )}
    </div>
  );
}
