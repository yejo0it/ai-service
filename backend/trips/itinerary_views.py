"""
여행 상세 일정 API.

- GET/POST   /trips/{id}/itinerary/          일정 조회 / 장소 직접 추가(배치 로직으로 자리 결정)
- POST       /trips/{id}/itinerary/init/     처음 열 때 항공편·숙소 카드 저장(한 번만)
- POST       /trips/{id}/itinerary/reorder/  하루 안의 순서 저장
- PATCH/DEL  /itinerary-items/{id}/          메모·시간 수정 / 삭제
- POST       /itinerary-items/{id}/checklist/, PATCH/DEL /checklist-items/{id}/
- GET        /trips/{id}/packing-note/       짐싸기 노트 '일정 연동 항목'
- POST       /trips/{id}/ai/propose/, /trips/{id}/ai/apply/   AI와 함께 만들기 (제안 미리보기 / 적용)
- GET        /places/search/                 일정 장소 자동완성
"""

import json
import re
from datetime import date, time as dtime

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import ai_planner, places, registration
from .itinerary_planner import CITY_CENTERS, day_anchor, place_cards, trip_days
from .models import ChecklistItem, ItineraryItem, Trip
from .packing import belongs_to_packing_note
from .serializers import TripSerializer

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ------------------------------------------------------------------ #
# 직렬화
# ------------------------------------------------------------------ #


class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistItem
        fields = ("id", "text", "done", "in_packing_note")


class ItineraryItemSerializer(serializers.ModelSerializer):
    time = serializers.TimeField(format="%H:%M", allow_null=True, required=False)
    checklist = ChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = ItineraryItem
        fields = (
            "id", "day", "order", "kind", "source", "title", "time", "time_label", "subtitle",
            "stops", "place_id", "address", "phone", "opening_hours", "memo", "checklist",
        )
        read_only_fields = ("id", "order", "source", "checklist")


class StopSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=12)
    caption = serializers.CharField(max_length=20, allow_blank=True)
    label = serializers.CharField(max_length=255)
    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)


class CardSerializer(serializers.Serializer):
    """프론트에서 만든 항공편·숙소 카드, 또는 AI 제안의 장소 카드"""

    day = serializers.DateField(required=False, allow_null=True)
    kind = serializers.ChoiceField(choices=ItineraryItem.Kind.choices)
    title = serializers.CharField(max_length=150)
    time = serializers.RegexField(TIME_PATTERN, required=False, allow_blank=True, default="")
    time_label = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    subtitle = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    stops = StopSerializer(many=True, required=False, default=list)
    place_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    opening_hours = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    checklist = serializers.ListField(child=serializers.CharField(max_length=200), required=False, default=list)


def itinerary_response(trip):
    items = trip.itinerary_items.prefetch_related("checklist")
    return Response(
        {"initialized": trip.itinerary_initialized, "items": ItineraryItemSerializer(items, many=True).data}
    )


# ------------------------------------------------------------------ #
# 날짜별 카드 <-> DB
# ------------------------------------------------------------------ #


def days_map(trip):
    """{date: [card]} - 여행 기간의 모든 날짜를 키로 갖는다."""
    days = {day: [] for day in trip_days(trip)}
    for item in trip.itinerary_items.all():
        days.setdefault(item.day, []).append(
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "time": item.time.strftime("%H:%M") if item.time else "",
                "time_label": item.time_label,
                "stops": item.stops,
            }
        )
    return days


def _model_fields(card, source):
    return {
        "kind": card["kind"],
        "source": card.get("source") or source,
        "title": card["title"][:150],
        "time": dtime.fromisoformat(card["time"]) if card.get("time") else None,
        "time_label": card.get("time_label", ""),
        "subtitle": card.get("subtitle", ""),
        "stops": card.get("stops", []),
        "place_id": card.get("place_id", ""),
        "address": card.get("address", "")[:255],
        "phone": card.get("phone", "")[:40],
        "opening_hours": card.get("opening_hours", []),
    }


def save_days(trip, days, source):
    """카드의 날짜·순서를 저장하고, id가 없는 카드는 새로 만든다(체크리스트 포함)."""
    for day, cards in days.items():
        for order, card in enumerate(cards):
            if card.get("id"):
                fields = {"day": day, "order": order}
                if card.get("time_changed"):
                    fields["time"] = dtime.fromisoformat(card["time"]) if card.get("time") else None
                ItineraryItem.objects.filter(pk=card["id"], trip=trip).update(**fields)
                continue
            item = ItineraryItem.objects.create(trip=trip, day=day, order=order, **_model_fields(card, source))
            card["id"] = item.id
            ChecklistItem.objects.bulk_create(
                [
                    ChecklistItem(item=item, text=text[:200], in_packing_note=belongs_to_packing_note(text))
                    for text in card.get("checklist", [])
                    if text.strip()
                ]
            )


def place_card(detail, kind, time="", checklist=()):
    """Places 상세 -> 장소 카드"""
    stop_kind = kind if kind in ("hotel", "airport") else "place"
    return {
        "kind": kind,
        "title": detail["name"],
        "time": time or "",
        "time_label": "",
        "subtitle": "",
        "stops": [
            {
                "kind": stop_kind,
                "caption": "주소",
                "label": detail.get("address") or detail["name"],
                "lat": detail.get("latitude"),
                "lng": detail.get("longitude"),
            }
        ],
        "place_id": detail.get("place_id", ""),
        "address": detail.get("address", ""),
        "phone": detail.get("phone", ""),
        "opening_hours": detail.get("opening_hours", []),
        "checklist": list(checklist),
    }


def owned_trip(request, pk):
    return get_object_or_404(Trip, pk=pk, owner=request.user)


# ------------------------------------------------------------------ #
# 일정
# ------------------------------------------------------------------ #


class AddPlaceSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[k for k in ItineraryItem.Kind.choices if k[0] != "flight"])
    day = serializers.DateField()
    time = serializers.RegexField(TIME_PATTERN, required=False, allow_blank=True, default="")
    place_id = serializers.CharField(max_length=255)
    session_token = serializers.CharField(required=False, allow_blank=True, default="")


class FlightAirportSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=4, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=100)
    lat = serializers.FloatField(required=False, allow_null=True, default=None)
    lng = serializers.FloatField(required=False, allow_null=True, default=None)


class AddFlightSerializer(serializers.Serializer):
    """공항(항공편) 직접 추가: 단일 노선 한 편"""

    kind = serializers.ChoiceField(choices=["flight"])
    day = serializers.DateField()
    time = serializers.RegexField(TIME_PATTERN, required=False, allow_blank=True, default="")
    airline = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    flight_number = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    departure_airport = FlightAirportSerializer()
    arrival_airport = FlightAirportSerializer()


def flight_card(data):
    """항공편 입력 -> 항공편 카드 (출발 공항 -> 도착 공항)"""
    title = " · ".join(part for part in (data["airline"], data["flight_number"]) if part) or "항공편"

    def stop(airport, caption):
        return {"kind": "airport", "caption": caption, "label": airport["name"],
                "lat": airport["lat"], "lng": airport["lng"]}

    return {
        "kind": ItineraryItem.Kind.FLIGHT,
        "title": title,
        "time": data["time"],
        "time_label": "",
        "subtitle": "",
        "stops": [stop(data["departure_airport"], "출발"), stop(data["arrival_airport"], "도착")],
        "checklist": [],
    }


class ItineraryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return itinerary_response(owned_trip(request, pk))

    @transaction.atomic
    def post(self, request, pk):
        trip = owned_trip(request, pk)
        is_flight = request.data.get("kind") == "flight"
        serializer = (AddFlightSerializer if is_flight else AddPlaceSerializer)(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not trip.start_date <= data["day"] <= trip.end_date:
            return Response({"day": ["여행 기간 안의 날짜를 선택해 주세요."]}, status=status.HTTP_400_BAD_REQUEST)
        if is_flight:
            card = flight_card(data)
        else:
            try:
                detail = places.place_details(data["place_id"], data["session_token"])
            except places.PlacesError as exc:
                return Response({"detail": str(exc)}, status=exc.status_code)
            card = place_card(detail, data["kind"], data["time"])

        days = days_map(trip)
        card["day"] = data["day"]
        place_cards(trip, days, [card])
        save_days(trip, days, ItineraryItem.Source.MANUAL)
        return itinerary_response(trip)


class ItineraryInitView(APIView):
    """처음 열 때 프론트가 만든 항공편·숙소 카드를 저장한다. 이미 저장했으면 그대로 돌려준다."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        trip = Trip.objects.select_for_update().get(pk=owned_trip(request, pk).pk)
        if not trip.itinerary_initialized:
            serializer = CardSerializer(data=request.data.get("items", []), many=True)
            serializer.is_valid(raise_exception=True)
            days = {day: [] for day in trip_days(trip)}
            for card in serializer.validated_data:
                if card.get("day") in days:
                    days[card["day"]].append(card)
            save_days(trip, days, ItineraryItem.Source.AUTO)
            trip.itinerary_initialized = True
            trip.save(update_fields=["itinerary_initialized"])
        return itinerary_response(trip)


class ReorderSerializer(serializers.Serializer):
    day = serializers.DateField()
    ids = serializers.ListField(child=serializers.IntegerField())


class ItineraryReorderView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        trip = owned_trip(request, pk)
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        day, ids = serializer.validated_data["day"], serializer.validated_data["ids"]
        current = set(trip.itinerary_items.filter(day=day).values_list("id", flat=True))
        if set(ids) != current:
            return Response({"detail": "그날의 일정과 맞지 않아요. 새로고침해 주세요."}, status=status.HTTP_409_CONFLICT)
        for order, item_id in enumerate(ids):
            ItineraryItem.objects.filter(pk=item_id, trip=trip).update(order=order)
        return itinerary_response(trip)


class ItineraryItemView(APIView):
    """일정 카드 메모·시간 수정, 삭제"""

    permission_classes = [IsAuthenticated]

    def get_item(self, request, item_id):
        return get_object_or_404(ItineraryItem, pk=item_id, trip__owner=request.user)

    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        serializer = ItineraryItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        allowed = {key: value for key, value in serializer.validated_data.items() if key in ("memo", "time")}
        for key, value in allowed.items():
            setattr(item, key, value)
        item.save(update_fields=[*allowed.keys(), "updated_at"])
        return Response(ItineraryItemSerializer(item).data)

    @transaction.atomic
    def delete(self, request, item_id):
        """
        카드를 지운다. 여행 등록 정보에서 만든 항공·숙소 카드면 등록 정보(요약 카드)도 맞추고,
        바뀐 여행과 함께 지운 다른 카드 id를 돌려준다(200). 그 밖에는 204.
        (숙소 체크인·체크아웃 카드는 그 숙소의 다른 카드까지 지우므로 화면에서 먼저 확인받는다.)
        """
        item = self.get_item(request, item_id)
        trip = item.trip
        changed, other_ids = registration.sync_after_card_delete(trip, item)
        trip.itinerary_items.filter(id__in=other_ids).delete()
        item.delete()
        if not changed:
            return Response(status=status.HTTP_204_NO_CONTENT)
        trip_data = TripSerializer(Trip.objects.get(pk=trip.pk), context={"request": request}).data
        return Response({"trip": trip_data, "removed_ids": [item_id, *other_ids]})


class ChecklistCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        item = get_object_or_404(ItineraryItem, pk=item_id, trip__owner=request.user)
        serializer = ChecklistItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["text"].strip()
        checklist = ChecklistItem.objects.create(
            item=item,
            text=text,
            # 명시하지 않으면 예약·티켓·준비물 낱말로 자동 분류한다.
            in_packing_note=request.data.get("in_packing_note", belongs_to_packing_note(text)),
        )
        return Response(ChecklistItemSerializer(checklist).data, status=status.HTTP_201_CREATED)


class ChecklistItemView(APIView):
    permission_classes = [IsAuthenticated]

    def get_check(self, request, check_id):
        return get_object_or_404(ChecklistItem, pk=check_id, item__trip__owner=request.user)

    def patch(self, request, check_id):
        check = self.get_check(request, check_id)
        serializer = ChecklistItemSerializer(check, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, check_id):
        self.get_check(request, check_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PackingNoteView(APIView):
    """짐싸기 노트: 일정 체크리스트 중 짐싸기 노트에 표시한 항목 (일정 연동 항목)"""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trip = owned_trip(request, pk)
        checks = (
            ChecklistItem.objects.filter(item__trip=trip, in_packing_note=True)
            .select_related("item")
            .order_by("item__day", "item__order", "id")
        )
        return Response(
            {
                "linked": [
                    {
                        **ChecklistItemSerializer(check).data,
                        "item_id": check.item_id,
                        "item_title": check.item.title,
                        "day": check.item.day,
                    }
                    for check in checks
                ]
            }
        )


class PlaceSearchView(APIView):
    """`/places/search/?input=&session_token=&city_code=&kind=` 일정 장소 자동완성"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("input", "").strip()
        session_token = request.query_params.get("session_token", "")
        if len(query) < 2 or not session_token:
            return Response([])
        try:
            results = places.autocomplete_places(
                query,
                session_token,
                city_code=request.query_params.get("city_code", "").strip(),
                kind=request.query_params.get("kind", "").strip(),
            )
        except places.PlacesError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return Response(results)


# ------------------------------------------------------------------ #
# AI와 함께 만들기
# ------------------------------------------------------------------ #


class ConversationSerializer(serializers.Serializer):
    class Turn(serializers.Serializer):
        role = serializers.ChoiceField(choices=["user", "assistant"])
        content = serializers.CharField(max_length=4000)

    messages = Turn(many=True, allow_empty=False)

    def validate_messages(self, value):
        if value[-1]["role"] != "user":
            raise serializers.ValidationError("마지막 메시지는 사용자 메시지여야 해요.")
        return value[-20:]


def _day_of(days, index):
    ordered = sorted(days)
    return ordered[index] if index is not None and 0 <= index < len(ordered) else None


def apply_changes(trip, days, additions, remove_ids, moves):
    """days에 삭제·이동·추가를 반영한다(미리보기와 적용이 같은 계산을 쓴다)."""
    # 새로 넣은 카드(자동 항공·숙소 카드 등)는 아직 id가 없다.
    owned_ids = {card.get("id") for cards in days.values() for card in cards} - {None}
    for day in days:
        days[day] = [card for card in days[day] if card.get("id") not in set(remove_ids) & owned_ids]

    moved_cards = []
    for move in moves:
        for day, cards in days.items():
            card = next((c for c in cards if c.get("id") == move["item_id"]), None)
            if card:
                cards.remove(card)
                card["day"] = move["day"]
                if move.get("time") is not None:
                    card["time"] = move["time"] or ""
                    card["time_changed"] = True
                card["moved"] = True
                moved_cards.append(card)
                break
    place_cards(trip, days, moved_cards + additions)


class AiProposeView(APIView):
    """대화 -> 일정 변경 제안. 장소를 실제 장소로 확정하고, 적용했을 때의 일정을 미리 계산해 돌려준다."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        trip = owned_trip(request, pk)
        serializer = ConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        days = days_map(trip)
        ordered_days = sorted(days)
        draft = _validated_draft(request.data.get("draft"))
        try:
            plan = ai_planner.propose(trip, ordered_days, days, serializer.validated_data["messages"], draft)
        except ai_planner.PlannerError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        additions, unresolved = [], []
        for addition in plan.additions:
            day = _day_of(days, addition.day_index)
            anchor = day_anchor(trip, day, days[day]) if day else _trip_center(trip)
            try:
                detail = places.search_place(addition.search_query, *(anchor or (None, None)))
            except places.PlacesError:
                detail = None
            if not detail or detail.get("latitude") is None:
                unresolved.append(addition.name)
                continue
            time = addition.time if addition.time and TIME_PATTERN.match(addition.time) else ""
            card = place_card(detail, addition.kind, time, addition.checklist)
            card["day"] = day
            card["reason"] = addition.reason
            additions.append(card)

        known_ids = {card["id"] for cards in days.values() for card in cards}
        remove_ids = [item_id for item_id in plan.remove_item_ids if item_id in known_ids]
        moves = [
            {"item_id": m.item_id, "day": _day_of(days, m.day_index), "time": m.time}
            for m in plan.moves
            if m.item_id in known_ids and _day_of(days, m.day_index)
        ]

        proposal = {
            "additions": [dict(card) for card in additions],
            "remove_item_ids": remove_ids,
            "moves": moves,
            "flight_changed": False,
            "flight_info": None,
            "hotels": None,
        }
        reply, choices = plan.reply, []
        flight_change, hotel_change = plan.flight, plan.hotel_change
        if plan.confirm and registration.is_registered(trip, plan.confirm, draft):
            # 이미 등록된 항공·숙소: 어떻게 바꿀지 먼저 묻는다(이번 답변에서는 바꾸지 않는다).
            reply, choices = registration.confirm_text(plan.confirm), registration.CONFIRM_CHOICES[plan.confirm]
            flight_change = None if plan.confirm == "flight" else flight_change
            hotel_change = None if plan.confirm == "hotel" else hotel_change
        elif plan.form:
            reply = registration.FORMS[plan.form]

        # 같은 대화의 적용 전 제안(draft)에 이어서 고친다. 이번에 바꾸지 않은 쪽도 제안에 그대로 이어 간다
        # (가장 최근 제안만 적용하므로, 앞선 변경이 사라지지 않게).
        removed_hotels, hotel_preview = [], None
        if flight_change:
            proposal["flight_changed"] = True
            proposal["flight_info"] = registration.build_flight_info(trip, flight_change, draft.get("flight_info"))
        elif draft.get("flight_info"):
            proposal["flight_changed"] = True
            proposal["flight_info"] = draft["flight_info"]
        hotels = None
        if hotel_change:
            hotels, missing = registration.build_hotels(trip, hotel_change, draft.get("hotels"))
            unresolved += missing
        elif draft.get("hotels") is not None:
            hotels, _ = registration.build_hotels(trip, ai_planner.HotelChange(mode="update", hotels=[]), draft["hotels"])
        if hotels:
            proposal["hotels"] = [_hotel_json(hotel) for hotel in hotels]
            hotel_preview = proposal["hotels"]
            removed_hotels = registration.removed_hotels(trip, hotels)
        apply_changes(trip, days, additions, remove_ids, moves)
        preview = [
            {
                "day": day,
                "items": [
                    {
                        "id": card.get("id"),
                        "title": card["title"],
                        "kind": card["kind"],
                        "time": card.get("time", ""),
                        "time_label": card.get("time_label", ""),
                        "status": "new" if not card.get("id") else ("moved" if card.get("moved") else "same"),
                    }
                    for card in days[day]
                ],
            }
            for day in ordered_days
        ]
        return Response(
            {
                "reply": reply,
                "choices": choices,
                "proposal": proposal,
                "preview": preview,
                "registration": {
                    "flight": proposal["flight_info"] if proposal["flight_changed"] else None,
                    "hotels": hotel_preview,
                    "removed_hotels": removed_hotels,
                },
                "removed": [
                    {"id": item.id, "title": item.title}
                    for item in trip.itinerary_items.filter(id__in=remove_ids)
                ],
                "unresolved": unresolved,
            }
        )


def _validated_draft(raw):
    """같은 대화의 적용 전 항공·숙소 제안 {"flight_info", "hotels"} (형식이 맞지 않는 쪽은 무시)"""
    if not isinstance(raw, dict):
        return {}
    draft = {}
    if raw.get("flight_info"):
        serializer = AiFlightInfoSerializer(data=raw["flight_info"])
        if serializer.is_valid():
            draft["flight_info"] = json.loads(json.dumps(serializer.validated_data))
    if raw.get("hotels"):
        serializer = HotelProposalSerializer(data=raw["hotels"], many=True)
        if serializer.is_valid():
            draft["hotels"] = [dict(hotel) for hotel in serializer.validated_data]
    return draft


def _hotel_json(hotel):
    """제안에 담는 숙소 (날짜는 문자열)"""
    return {
        **hotel,
        "check_in": hotel["check_in"].isoformat(),
        "check_out": hotel["check_out"].isoformat() if hotel["check_out"] else None,
    }


def _trip_center(trip):
    for dest in trip.destinations or []:
        center = CITY_CENTERS.get((dest.get("city_code") or "").upper())
        if center:
            return center
    return None


STAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}(T([01]\d|2[0-3]):[0-5]\d)?$")


class AiFlightInfoSerializer(serializers.Serializer):
    """AI로 등록한 항공 정보 (말하지 않은 항목은 비어 있을 수 있다)"""

    class Airport(serializers.Serializer):
        code = serializers.CharField(max_length=3, allow_blank=True, default="")
        name = serializers.CharField(max_length=60)

    airline = serializers.CharField(max_length=60, required=False, allow_blank=True)
    flight_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    departure_at = serializers.RegexField(STAMP_PATTERN, required=False)
    arrival_at = serializers.RegexField(STAMP_PATTERN, required=False, allow_null=True)
    departure_airport = Airport(required=False, allow_null=True)
    arrival_airport = Airport(required=False, allow_null=True)
    return_departure_airport = Airport(required=False, allow_null=True)
    return_arrival_airport = Airport(required=False, allow_null=True)
    return_airline = serializers.CharField(max_length=60, required=False, allow_blank=True)
    return_flight_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    return_departure_at = serializers.RegexField(STAMP_PATTERN, required=False, allow_null=True)
    return_arrival_at = serializers.RegexField(STAMP_PATTERN, required=False, allow_null=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class HotelProposalSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=150)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    place_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    latitude = serializers.FloatField(required=False, allow_null=True, default=None)
    longitude = serializers.FloatField(required=False, allow_null=True, default=None)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    city_code = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    check_in = serializers.DateField()
    check_out = serializers.DateField(required=False, allow_null=True, default=None)
    # 미리보기 표시용 (적용할 때는 쓰지 않는다)
    status = serializers.ChoiceField(choices=["new", "updated", "same"], required=False, default="same")


class ProposalSerializer(serializers.Serializer):
    class Move(serializers.Serializer):
        item_id = serializers.IntegerField()
        day = serializers.DateField()
        time = serializers.RegexField(TIME_PATTERN, required=False, allow_null=True, allow_blank=True)

    additions = CardSerializer(many=True, default=list)
    remove_item_ids = serializers.ListField(child=serializers.IntegerField(), default=list)
    moves = Move(many=True, default=list)
    # 항공·숙소 등록 (hotels가 null이면 숙소는 그대로)
    flight_changed = serializers.BooleanField(default=False)
    flight_info = AiFlightInfoSerializer(required=False, allow_null=True, default=None)
    hotels = HotelProposalSerializer(many=True, required=False, allow_null=True, default=None)
    # 바뀐 항공·숙소로 프론트가 다시 만든 경로의 자동 항공·숙소 카드
    auto_cards = CardSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        for hotel in attrs.get("hotels") or []:
            if hotel["check_out"] and hotel["check_out"] < hotel["check_in"]:
                raise serializers.ValidationError({"hotels": "체크아웃은 체크인 이후여야 해요."})
        return attrs


class AiApplyView(APIView):
    """미리 본 제안을 현재 일정에 적용한다(현재 상태 기준으로 자리를 다시 계산)."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        trip = owned_trip(request, pk)
        serializer = ProposalSerializer(data=request.data.get("proposal", {}))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        registration_changed = data["flight_changed"] or data["hotels"] is not None
        if data["flight_changed"]:
            trip.flight_info = data["flight_info"] or None
            trip.save(update_fields=["flight_info", "updated_at"])
        if data["hotels"] is not None:
            registration.save_hotels(trip, data["hotels"])

        days = days_map(trip)
        removed_ids = set(data["remove_item_ids"])
        if registration_changed:
            removed_ids |= registration.replace_auto_cards(trip, days, [dict(card) for card in data["auto_cards"]])
        additions = [dict(card) for card in data["additions"]]
        for card in additions:
            if card.get("day") not in days:
                card["day"] = None
        moves = [m for m in data["moves"] if m["day"] in days]
        apply_changes(trip, days, additions, data["remove_item_ids"], moves)
        trip.itinerary_items.filter(id__in=removed_ids).delete()
        save_days(trip, days, ItineraryItem.Source.AI)
        response = itinerary_response(trip)
        response.data["trip"] = TripSerializer(Trip.objects.get(pk=trip.pk), context={"request": request}).data
        return response
