import { useEffect, useRef, useState, type Dispatch, type FormEvent, type KeyboardEvent, type SetStateAction } from "react";
import { applyAiPlan, proposeAiPlan, toErrorMessage } from "../api/client";
import { formatMeridiemTime } from "../components/pickers";
import type {
  AiProposal,
  AiProposeResponse,
  AiRegistrationDraft,
  ChatTurn,
  FlightInfo,
  Hotel,
  ItineraryResponse,
  Trip,
} from "../types/api";
import { formatMonthDay } from "../utils/date";
import Drawer from "./Drawer";
import { KIND_STYLE } from "./TripItinerary";
import { dayLabel, initialCards } from "./tripDays";

const EXAMPLES = [
  "스카이트리, 츠지한 니혼바시 본점, 오다이바 해변공원 꼭 가고 싶어",
  "첫째 날 19시에 도쿄타워 추가해줘",
  "전체 여행 계획 짜줘",
];

const STATUS_BADGE = {
  new: { label: "추가", className: "bg-emerald-50 text-emerald-700" },
  moved: { label: "이동", className: "bg-amber-50 text-amber-700" },
} as const;

const EMPTY = "미입력";

/** "2026-11-10T09:00" -> "오전 9:00", 날짜만 있거나 비어 있으면 "" */
const stampTime = (value?: string | null) => (value && value.length > 10 ? formatMeridiemTime(value.slice(11, 16)) : "");

/** 등록할 항공편 한 편: 빈 항목은 '미입력'으로 보여준다. */
function FlightLegPreview({ label, flight, prefix }: { label: string; flight: FlightInfo; prefix: "" | "return_" }) {
  const from = flight[`${prefix}departure_airport`]?.name;
  const to = flight[`${prefix}arrival_airport`]?.name;
  const airline = prefix ? flight.return_airline : flight.airline;
  const number = prefix ? flight.return_flight_number : flight.flight_number;
  const departure = stampTime(prefix ? flight.return_departure_at : flight.departure_at);
  const arrival = stampTime(prefix ? flight.return_arrival_at : flight.arrival_at);
  const detail = (name: string, value?: string) => (
    <span className={value ? "text-slate-600" : "text-slate-300"}>
      {name} {value || EMPTY}
    </span>
  );
  return (
    <li className="rounded-lg bg-white px-2.5 py-2 text-xs shadow-sm">
      <p className="font-semibold text-indigo-600">{label}</p>
      <p className="mt-0.5 font-medium text-slate-800">
        {from || "출발 공항 미입력"} → {to || "도착 공항 미입력"}
      </p>
      <p className="mt-0.5 flex flex-wrap gap-x-2">
        {detail("항공사", airline)}
        {detail("편명", number)}
        {detail("출발", departure)}
        {detail("도착", arrival)}
      </p>
    </li>
  );
}

/** 항공·숙소 등록 미리보기 */
function RegistrationPreview({ registration }: { registration: AiProposeResponse["registration"] }) {
  const { flight, hotels, removed_hotels: removedHotels } = registration;
  const hasReturn = Boolean(
    flight &&
      (flight.return_departure_airport ||
        flight.return_arrival_airport ||
        flight.return_airline ||
        flight.return_flight_number ||
        flight.return_departure_at),
  );
  return (
    <>
      {flight && (
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slate-600">항공</p>
          <ul className="space-y-1">
            <FlightLegPreview label="가는 편" flight={flight} prefix="" />
            {hasReturn && <FlightLegPreview label="오는 편" flight={flight} prefix="return_" />}
          </ul>
        </div>
      )}
      {hotels && hotels.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slate-600">숙소</p>
          <ul className="space-y-1">
            {hotels.map((hotel, index) => (
              <li
                key={hotel.id ?? `new-${index}`}
                className={`rounded-lg px-2.5 py-2 text-xs ${hotel.status === "same" ? "text-slate-400" : "bg-white shadow-sm"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`truncate ${hotel.status === "same" ? "" : "font-medium text-slate-800"}`}>{hotel.name}</span>
                  {hotel.status !== "same" && (
                    <span
                      className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                        hotel.status === "new" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
                      }`}
                    >
                      {hotel.status === "new" ? "추가" : "수정"}
                    </span>
                  )}
                </div>
                <p className="mt-0.5">
                  {formatMonthDay(hotel.check_in)}
                  {hotel.check_out ? ` ~ ${formatMonthDay(hotel.check_out)}` : ""}
                  {hotel.nights ? ` · ${hotel.nights}박` : ""}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {removedHotels.length > 0 && (
        <p className="text-xs text-rose-600">
          <span className="font-semibold">빼는 숙소</span> · {removedHotels.map((hotel) => hotel.title).join(", ")}
        </p>
      )}
    </>
  );
}

/** 제안에 적용할 내용이 있는지 (일정·항공·숙소) */
const hasProposalChanges = (proposal: AiProposal) =>
  proposal.additions.length > 0 ||
  proposal.moves.length > 0 ||
  proposal.remove_item_ids.length > 0 ||
  proposal.flight_changed ||
  proposal.hotels !== null;

/** 제안 미리보기: 바뀌는 날만, 그날의 순서대로. 새로 넣는 곳·옮기는 곳·빠지는 곳, 등록할 항공·숙소를 표시한다. */
function ProposalPreview({ result, dates }: { result: AiProposeResponse; dates: string[] }) {
  const changedDays = result.preview.filter((day) => day.items.some((item) => item.status !== "same"));

  return (
    <div className="mt-2 space-y-3 rounded-2xl border border-indigo-100 bg-indigo-50/40 p-3">
      <RegistrationPreview registration={result.registration} />
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

export interface Message extends ChatTurn {
  /** AI 답변에 딸린 제안 (적용 전) */
  result?: AiProposeResponse;
  applied?: boolean;
}

interface AiPlannerDrawerProps {
  trip: Trip;
  dates: string[];
  /** 대화 (창을 닫았다 열어도 이어지도록 상세 화면이 들고 있다) */
  messages: Message[];
  setMessages: Dispatch<SetStateAction<Message[]>>;
  onClose: () => void;
  onApplied: (itinerary: ItineraryResponse, trip: Trip) => void;
}

/**
 * AI와 함께 만들기: 대화로 일정 추가·수정·재배치를 요청한다.
 * AI가 장소·날짜·시간을 고르면 서버가 실제 장소를 찾고 거리 기준으로 자리를 정해 미리보기를 돌려준다.
 * [계획에 적용]을 눌러야 저장된다. 적용 후에도 카드에서 자유롭게 고치거나 지울 수 있다.
 * 항공·숙소: 미등록이면 양식을 안내하고, 등록돼 있으면 수정/덮어쓰기를 먼저 묻는다(선택 버튼 또는 입력).
 * 바뀐 항공·숙소로 경로의 자동 항공·숙소 카드를 다시 만들어 함께 보낸다.
 * 아직 적용하지 않은 항공·숙소 제안은 다음 메시지와 함께 보내, 이어지는 수정이 그 위에 쌓이게 한다.
 */
export default function AiPlannerDrawer({ trip, dates, messages, setMessages, onClose, onApplied }: AiPlannerDrawerProps) {
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pending]);

  /** 가장 최근 제안이 아직 적용 전이면 그 항공·숙소 (다음 제안의 바탕) */
  const pendingDraft = (): AiRegistrationDraft | undefined => {
    // 바뀌는 내용이 없는 답변(거절·단순 안내)은 건너뛰고, 가장 최근 제안을 본다.
    const last = [...messages].reverse().find((message) => message.result && hasProposalChanges(message.result.proposal));
    const proposal = last?.result?.proposal;
    if (!proposal || last.applied || (!proposal.flight_changed && proposal.hotels === null)) return undefined;
    return { flight_info: proposal.flight_changed ? proposal.flight_info : null, hotels: proposal.hotels };
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || pending) return;
    const draft = pendingDraft();
    const history: Message[] = [...messages, { role: "user", content }];
    setMessages(history);
    setInput("");
    setPending(true);
    setError("");
    try {
      const result = await proposeAiPlan(
        trip.id,
        history.map(({ role, content: body }) => ({ role, content: body })),
        draft,
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
      const { proposal } = result;
      let autoCards = proposal.auto_cards;
      if (proposal.flight_changed || proposal.hotels !== null) {
        const nextTrip: Trip = {
          ...trip,
          flight_info: proposal.flight_changed ? proposal.flight_info : trip.flight_info,
          hotels: proposal.hotels ? proposal.hotels.map((hotel): Hotel => ({ ...hotel, id: hotel.id ?? 0 })) : trip.hotels,
        };
        autoCards = initialCards(nextTrip);
      }
      const { trip: updatedTrip, ...itinerary } = await applyAiPlan(trip.id, { ...proposal, auto_cards: autoCards });
      setMessages((current) => current.map((message, i) => (i === index ? { ...message, applied: true } : message)));
      onApplied(itinerary, updatedTrip);
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
  // 바뀌는 내용이 없는 답변(거절·단순 안내)은 앞선 제안을 가리지 않는다.
  const lastResultIndex = messages
    .map((message) => Boolean(message.result && hasProposalChanges(message.result.proposal)))
    .lastIndexOf(true);

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
              {/* 수정/덮어쓰기 확인: 가장 최근 답변에만 선택 버튼 (직접 입력해도 된다) */}
              {index === messages.length - 1 && (message.result?.choices.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5" aria-label="답변 선택">
                  {message.result?.choices.map((choice) => (
                    <button
                      key={choice}
                      type="button"
                      onClick={() => send(choice)}
                      disabled={pending}
                      className="rounded-full border border-indigo-200 bg-white px-3 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                    >
                      {choice}
                    </button>
                  ))}
                </div>
              )}
              {message.result && (hasProposalChanges(message.result.proposal) || message.result.unresolved.length > 0) && (
                <>
                  <ProposalPreview result={message.result} dates={dates} />
                  {message.applied ? (
                    <p className="mt-2 text-xs font-semibold text-emerald-600">
                      <i className="fas fa-check mr-1" aria-hidden="true" />
                      계획에 적용했어요
                    </p>
                  ) : (
                    index === lastResultIndex &&
                    hasProposalChanges(message.result.proposal) && (
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
