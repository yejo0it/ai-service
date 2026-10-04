import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { applyAiPlan, proposeAiPlan, toErrorMessage } from "../api/client";
import type { AiProposeResponse, ChatTurn, ItineraryResponse, Trip } from "../types/api";
import { formatMonthDay } from "../utils/date";
import Drawer from "./Drawer";
import { KIND_STYLE } from "./TripItinerary";
import { dayLabel } from "./tripDays";

const EXAMPLES = [
  "스카이트리, 츠지한 니혼바시 본점, 오다이바 해변공원 꼭 가고 싶어",
  "첫째 날 19시에 도쿄타워 추가해줘",
  "전체 여행 계획 짜줘",
];

const STATUS_BADGE = {
  new: { label: "추가", className: "bg-emerald-50 text-emerald-700" },
  moved: { label: "이동", className: "bg-amber-50 text-amber-700" },
} as const;

/** 제안 미리보기: 바뀌는 날만, 그날의 순서대로. 새로 넣는 곳·옮기는 곳·빠지는 곳을 표시한다. */
function ProposalPreview({ result, dates }: { result: AiProposeResponse; dates: string[] }) {
  const changedDays = result.preview.filter((day) => day.items.some((item) => item.status !== "same"));
  const hasChanges = changedDays.length > 0 || result.removed.length > 0;

  return (
    <div className="mt-2 space-y-3 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-3">
      {!hasChanges && <p className="text-xs text-slate-500">일정에 바뀌는 내용은 없어요.</p>}
      {changedDays.map((day) => (
        <div key={day.day}>
          <p className="mb-1.5 text-xs font-semibold text-slate-600">
            {dayLabel(dates.indexOf(day.day))} · {formatMonthDay(day.day)}
          </p>
          <ol className="space-y-1">
            {day.items.map((item, index) => {
              const badge = item.status === "same" ? null : STATUS_BADGE[item.status];
              return (
                <li
                  key={`${item.id ?? "new"}-${index}`}
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs ${badge ? "bg-white shadow-sm" : "text-slate-400"}`}
                >
                  <i className={`${KIND_STYLE[item.kind].icon} w-3.5 text-center`} aria-hidden="true" />
                  <span className={`min-w-0 flex-1 truncate ${badge ? "font-medium text-slate-800" : ""}`}>{item.title}</span>
                  <span className="shrink-0 tabular-nums">{item.time || item.time_label}</span>
                  {badge && (
                    <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${badge.className}`}>
                      {badge.label}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
      {result.removed.length > 0 && (
        <p className="text-xs text-rose-600">
          <span className="font-semibold">빼는 일정</span> · {result.removed.map((item) => item.title).join(", ")}
        </p>
      )}
      {result.unresolved.length > 0 && (
        <p className="text-xs text-slate-500">
          <span className="font-semibold">찾지 못한 장소</span> · {result.unresolved.join(", ")} (이름을 더 정확히 알려주세요)
        </p>
      )}
    </div>
  );
}

interface Message extends ChatTurn {
  /** AI 답변에 딸린 제안 (적용 전) */
  result?: AiProposeResponse;
  applied?: boolean;
}

interface AiPlannerDrawerProps {
  trip: Trip;
  dates: string[];
  onClose: () => void;
  onApplied: (itinerary: ItineraryResponse) => void;
}

/**
 * AI와 함께 만들기: 대화로 일정 추가·수정·재배치를 요청한다.
 * AI가 장소·날짜·시간을 고르면 서버가 실제 장소를 찾고 거리 기준으로 자리를 정해 미리보기를 돌려준다.
 * [계획에 적용]을 눌러야 저장된다. 적용 후에도 카드에서 자유롭게 고치거나 지울 수 있다.
 */
export default function AiPlannerDrawer({ trip, dates, onClose, onApplied }: AiPlannerDrawerProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pending]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || pending) return;
    const history: Message[] = [...messages, { role: "user", content }];
    setMessages(history);
    setInput("");
    setPending(true);
    setError("");
    try {
      const result = await proposeAiPlan(
        trip.id,
        history.map(({ role, content: body }) => ({ role, content: body })),
      );
      setMessages([...history, { role: "assistant", content: result.reply, result }]);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const apply = async (index: number) => {
    const result = messages[index]?.result;
    if (!result) return;
    setApplying(true);
    setError("");
    try {
      const itinerary = await applyAiPlan(trip.id, result.proposal);
      setMessages((current) => current.map((message, i) => (i === index ? { ...message, applied: true } : message)));
      onApplied(itinerary);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setApplying(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    send(input);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send(input);
    }
  };

  // 가장 최근 제안만 적용할 수 있다 (이전 제안은 일정이 바뀌었을 수 있다).
  const lastResultIndex = messages.map((message) => Boolean(message.result)).lastIndexOf(true);

  return (
    <Drawer
      title="AI와 함께 만들기"
      onClose={onClose}
      footer={
        <form onSubmit={onSubmit} className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder="가고 싶은 곳이나 바꾸고 싶은 일정을 말해 주세요"
            aria-label="AI에게 보낼 메시지"
            className="min-w-0 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
          <button
            type="submit"
            disabled={!input.trim() || pending}
            aria-label="보내기"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
          >
            <i className="fas fa-paper-plane text-sm" aria-hidden="true" />
          </button>
        </form>
      }
    >
      <div className="space-y-4" aria-live="polite">
        {messages.length === 0 && (
          <div>
            <p className="text-sm text-slate-600">
              {trip.destination_label} 여행에 넣고 싶은 곳이나 바꾸고 싶은 일정을 편하게 말해 주세요. 가까운 곳끼리 묶어서
              배치해 드려요.
            </p>
            <p className="mt-3 text-xs font-semibold text-slate-400">이렇게 말해 보세요</p>
            <ul className="mt-1.5 space-y-1.5" aria-label="예시 문장">
              {EXAMPLES.map((example) => (
                <li key={example} className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-500">
                  {example}
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-indigo-600 px-3.5 py-2 text-sm text-white">
                {message.content}
              </p>
            </div>
          ) : (
            <div key={index}>
              <p className="max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2 text-sm text-slate-800">
                {message.content}
              </p>
              {message.result && (
                <>
                  <ProposalPreview result={message.result} dates={dates} />
                  {message.applied ? (
                    <p className="mt-2 text-xs font-semibold text-emerald-600">
                      <i className="fas fa-check mr-1" aria-hidden="true" />
                      계획에 적용했어요
                    </p>
                  ) : (
                    index === lastResultIndex &&
                    (message.result.proposal.additions.length > 0 ||
                      message.result.proposal.moves.length > 0 ||
                      message.result.proposal.remove_item_ids.length > 0) && (
                      <button
                        type="button"
                        onClick={() => apply(index)}
                        disabled={applying}
                        className="mt-2 w-full rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:bg-slate-300"
                      >
                        {applying ? "적용하는 중..." : "계획에 적용"}
                      </button>
                    )
                  )}
                </>
              )}
            </div>
          ),
        )}

        {pending && (
          <p className="inline-flex items-center gap-2 rounded-2xl bg-slate-100 px-3.5 py-2 text-sm text-slate-500">
            <i className="fas fa-spinner fa-spin" aria-hidden="true" />
            일정을 짜고 있어요...
          </p>
        )}
        {error && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>}
        <div ref={bottomRef} />
      </div>
    </Drawer>
  );
}
