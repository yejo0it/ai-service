import { useEffect, useRef, type ReactNode } from "react";

interface DrawerProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** 하단 고정 영역 (버튼·입력창) */
  footer?: ReactNode;
}

/** 오른쪽(좁은 화면은 아래)에서 열리는 패널. Esc·바깥 클릭으로 닫는다. */
export default function Drawer({ title, onClose, children, footer }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-slate-900/30 sm:items-stretch" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-[90vh] w-full flex-col rounded-t-3xl bg-white shadow-xl outline-none sm:max-h-none sm:max-w-md sm:rounded-none sm:rounded-l-3xl"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <i className="fas fa-times" aria-hidden="true" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="border-t border-slate-100 px-5 py-4">{footer}</div>}
      </div>
    </div>
  );
}
