"""
여행 경비 관리 (1단계: 예산과 지출, 원화).

- 만든 회원과 일행이 같은 경비 내역을 보고 고친다. 그 밖의 회원에게는 여행이 없는 것(404)이다.
- GET  /trips/{id}/expenses/  예산·총지출·남은 예산·분류별 합계와 지출 목록
- POST /trips/{id}/expenses/  지출 등록
- PATCH/DELETE /expenses/{id}/  지출 수정·삭제
- PUT  /trips/{id}/budget/    총예산 설정·수정(null이면 예산을 지운다)
- GET  /trips/{id}/expense-currencies/  지출 입력에서 고를 통화와 지금 환율
- GET  /trips/{id}/settlement/  결제자·분담 인원 기준의 사용자별 정산과 송금 안내
지출마다 결제자와 비용을 나눌 인원(여행에 함께하는 사람)을 정하고, 선택한 인원끼리 균등 분할하거나
사람마다 금액을 직접 입력해 나눈다(직접 입력의 합계는 지출 금액과 같아야 한다).
지출은 현지 통화로 입력할 수 있고, 등록할 때의 환율과 원화 환산 금액을 함께 저장한다
(환율 서비스가 멈춰도 저장된 내역은 그대로 조회된다). 금액은 Decimal/정수로만 계산한다.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.nickname import nickname_of

from . import expense_currency, settlement, travel_info
from .models import Expense, ExpenseShare, Trip, TripBudget, TripMember

User = get_user_model()
MAX_PARTICIPANTS = TripMember.MAX_PER_TRIP + 1  # 일행 + 만든 회원


class ParticipantAmountSerializer(serializers.Serializer):
    """직접 입력 분담: 사람 한 명과 그 사람이 부담하는 금액(지출 통화 기준)."""

    id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))


class ExchangeRateUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "환율을 불러오지 못했어요. 원화로 입력하거나 잠시 후 다시 시도해 주세요."
    default_code = "exchange_rate_unavailable"


class ExpenseSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False, default=expense_currency.KRW)
    # 지출 당시 적용한 환율(1원당 현지 통화 금액). 원화 지출은 null
    rate_per_krw = serializers.SerializerMethodField()
    # 결제자(회원 번호). 쓰면 여행에 함께하는 사람이어야 하고, 안 쓰면 등록한 사람이다.
    payer_id = serializers.IntegerField(required=False, min_value=1)
    payer_name = serializers.SerializerMethodField()
    # 비용을 나눌 인원(회원 번호 목록). 쓰지 않으면 나누지 않는 지출이다.
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, write_only=True, allow_empty=False,
        max_length=MAX_PARTICIPANTS,
    )
    participants = serializers.SerializerMethodField()
    # 분담 방식: equal(균등, 기본) / custom(직접 입력). 직접 입력은 participant_amounts로 사람마다 금액을 보낸다.
    split_method = serializers.ChoiceField(choices=Expense.SplitMethod.choices, required=False)
    participant_amounts = ParticipantAmountSerializer(many=True, required=False, write_only=True, allow_empty=False)

    class Meta:
        model = Expense
        fields = (
            "id",
            "title",
            "amount",
            "currency",
            "amount_krw",
            "rate_per_krw",
            "spent_on",
            "category",
            "memo",
            "payer_id",
            "payer_name",
            "participant_ids",
            "participant_amounts",
            "participants",
            "split_method",
        )
        # 환율과 원화 환산 금액은 서버가 정한다.
        read_only_fields = ("id", "amount_krw")

    def get_rate_per_krw(self, expense):
        return None if expense.rate_per_krw is None else format(expense.rate_per_krw.normalize(), "f")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["payer_id"] = instance.payer_ref  # 탈퇴한 결제자도 같은 번호로 보인다.
        return data

    def get_payer_name(self, expense):
        return name_of(expense.payer, expense.payer_name)

    def get_participants(self, expense):
        """분담 인원과 각자의 부담액(균등 분할, 나머지는 1원씩)."""
        shares = list(expense.shares.all())
        if not shares:
            return []
        amounts = share_amounts(expense, shares)
        custom = expense.split_method == Expense.SplitMethod.CUSTOM
        return [
            {
                "id": share.user_ref,
                "name": name_of(share.user, share.user_name),
                "share_krw": amounts[share.user_ref],
                # 직접 입력일 때 사람이 입력한 금액(지출 통화 기준)
                "amount": str(share.custom_amount) if custom and share.custom_amount is not None else None,
            }
            for share in shares
        ]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("지출명을 입력해 주세요.")
        return value

    def validate_currency(self, value):
        value = value.strip().upper()
        if not expense_currency.is_supported(value):
            raise serializers.ValidationError("지원하지 않는 통화예요.")
        return value

    def validate(self, attrs):
        # 통화에 맞는 소수 자릿수만 받는다(원화·엔은 정수, 그 밖은 소수 둘째 자리까지).
        instance = self.instance
        currency = attrs.get("currency", instance.currency if instance else expense_currency.KRW)
        amount = attrs.get("amount", instance.amount if instance else None)
        if amount is not None:
            if amount > Expense.MAX_AMOUNT_KRW:
                raise serializers.ValidationError({"amount": "금액이 너무 커요."})
            if expense_currency.decimal_places(currency) == 0 and amount != amount.to_integral_value():
                raise serializers.ValidationError({"amount": "이 통화는 소수점 없이 입력해 주세요."})
        self._check_split(attrs, currency, amount)
        self._check_people(attrs)
        return attrs

    def _check_split(self, attrs, currency, amount):
        """분담 방식을 정리한다. 직접 입력은 합계가 지출 금액과 정확히 같아야 한다."""
        instance = self.instance
        method = attrs.get("split_method")
        amounts = attrs.get("participant_amounts")
        Method = Expense.SplitMethod
        if amounts is not None:
            if method not in (None, Method.CUSTOM) or "participant_ids" in attrs:
                raise serializers.ValidationError({"participant_amounts": "직접 입력은 분담 금액만 보내 주세요."})
            ids = [item["id"] for item in amounts]
            if len(set(ids)) != len(ids) or len(ids) > MAX_PARTICIPANTS:
                raise serializers.ValidationError({"participant_amounts": "분담 인원이 올바르지 않아요."})
            places = expense_currency.decimal_places(currency)
            if places == 0 and any(item["amount"] != item["amount"].to_integral_value() for item in amounts):
                raise serializers.ValidationError({"participant_amounts": "이 통화는 소수점 없이 입력해 주세요."})
            if sum(item["amount"] for item in amounts) != amount:
                raise serializers.ValidationError({"participant_amounts": "분담 금액의 합계가 지출 금액과 같아야 해요."})
            attrs["split_method"] = Method.CUSTOM
            attrs["participant_ids"] = ids
        elif method == Method.CUSTOM:
            unchanged = instance and instance.split_method == Method.CUSTOM and not ({"amount", "currency"} & set(attrs))
            if not unchanged:
                raise serializers.ValidationError({"participant_amounts": "분담 금액을 입력해 주세요."})
        elif instance and instance.split_method == Method.CUSTOM and "participant_ids" not in attrs and method is None:
            if {"amount", "currency"} & set(attrs):
                raise serializers.ValidationError(
                    {"participant_amounts": "금액이나 통화를 바꾸면 분담 금액도 다시 입력해 주세요."}
                )
        else:
            # 인원만 보내거나 균등을 고르면 균등 분할이다.
            if method == Method.EQUAL or "participant_ids" in attrs:
                attrs["split_method"] = Method.EQUAL

    def _people(self):
        """결제자·분담 인원으로 고를 수 있는 사람: 만든 회원과 일행."""
        trip = self.context["trip"]
        ids = [trip.owner_id, *trip.members.values_list("user_id", flat=True)]
        return {user.id: user for user in User.objects.filter(pk__in=[i for i in ids if i]).select_related("profile")}

    def _check_people(self, attrs):
        """고른 결제자·분담 인원이 지금 여행에 함께하는 사람인지 확인한다. 이 지출에 이미 있던 사람(나간 일행)은 그대로 둘 수 있다."""
        instance = self.instance
        allowed = set(self._people())
        if instance is not None:
            allowed |= {share.user_ref for share in instance.shares.all()}
            if instance.payer_ref:
                allowed.add(instance.payer_ref)
        if "payer_id" in attrs and attrs["payer_id"] not in allowed:
            raise serializers.ValidationError({"payer_id": "여행에 함께하는 사람만 결제자로 고를 수 있어요."})
        ids = attrs.get("participant_ids")
        if ids is not None and not set(ids) <= allowed:
            raise serializers.ValidationError({"participant_ids": "여행에 함께하는 사람만 분담 인원으로 고를 수 있어요."})

    def _save_people(self, expense, data):
        """결제자와 분담 인원을 저장한다. 결제자는 회원 번호·이름을 함께 남긴다."""
        people = self._people()
        payer_id = data.pop("payer_id", None)
        participant_ids = data.pop("participant_ids", None)
        amounts = data.pop("participant_amounts", None)
        custom = {item["id"]: item["amount"] for item in amounts} if amounts is not None else None
        return payer_id, participant_ids, custom, people

    def _with_krw(self, data, instance=None):
        """등록·수정할 때 적용 환율과 원화 환산 금액을 정한다. 금액·통화가 바뀌지 않으면 저장된 값을 그대로 둔다."""
        if not ("amount" in data or "currency" in data):
            return data
        currency = data.get("currency", instance.currency if instance else expense_currency.KRW)
        amount = data.get("amount", instance.amount if instance else None)
        if currency == expense_currency.KRW:
            rate, amount_krw = None, int(amount)
        else:
            if instance and instance.currency == currency and instance.rate_per_krw:
                rate = instance.rate_per_krw  # 같은 통화의 금액만 고치면 처음 적용한 환율을 쓴다.
            else:
                try:
                    rate = expense_currency.rate_per_krw(currency)
                except travel_info.TravelInfoError as exc:
                    raise ExchangeRateUnavailable() from exc
            amount_krw = expense_currency.to_krw(amount, rate)
        if amount_krw > Expense.MAX_AMOUNT_KRW:
            raise serializers.ValidationError({"amount": "금액이 너무 커요."})
        return {**data, "rate_per_krw": rate, "amount_krw": amount_krw}

    def _apply_people(self, expense, payer_id, participant_ids, custom, people):
        if payer_id is not None:
            payer = people.get(payer_id)
            if payer is not None:  # 나간 일행을 그대로 두는 경우(payer가 people에 없음)는 건드리지 않는다.
                expense.payer, expense.payer_ref = payer, payer.id
                expense.payer_name = name_of(payer, "")[:30]
                expense.save(update_fields=["payer", "payer_ref", "payer_name"])
        if participant_ids is not None:
            existing = {share.user_ref: share for share in expense.shares.all()}
            wanted = list(dict.fromkeys(participant_ids))
            expense.shares.exclude(user_ref__in=wanted).delete()
            for ref in wanted:
                user = people.get(ref)
                amount = custom.get(ref) if custom is not None else None
                if ref in existing and user is None:
                    # 나간 일행은 처음 남긴 이름·번호를 그대로 두고 금액만 바꾼다.
                    ExpenseShare.objects.filter(pk=existing[ref].pk).update(custom_amount=amount)
                    continue
                ExpenseShare.objects.update_or_create(
                    expense=expense,
                    user_ref=ref,
                    defaults={
                        "user": user,
                        "user_name": name_of(user, "")[:30] if user else "",
                        "custom_amount": amount,
                    },
                )
        if expense.split_method == Expense.SplitMethod.EQUAL:
            expense.shares.exclude(custom_amount=None).update(custom_amount=None)  # 균등 분할로 바꾸면 금액을 지운다.
        # 미리 불러 둔 분담 인원(prefetch)이 남아 있으면 응답에 이전 인원이 나오므로 버린다.
        getattr(expense, "_prefetched_objects_cache", {}).pop("shares", None)

    @transaction.atomic
    def create(self, validated_data):
        payer_id, participant_ids, custom, people = self._save_people(None, validated_data)
        request_user = self.context["request"].user
        if payer_id is None:
            payer_id = request_user.id
            people.setdefault(request_user.id, request_user)
        expense = super().create(self._with_krw(validated_data))
        self._apply_people(expense, payer_id, participant_ids, custom, people)
        return expense

    @transaction.atomic
    def update(self, instance, validated_data):
        payer_id, participant_ids, custom, people = self._save_people(instance, validated_data)
        expense = super().update(instance, self._with_krw(validated_data, instance))
        self._apply_people(expense, payer_id, participant_ids, custom, people)
        return expense


def share_amounts(expense, shares):
    """분담 인원별 원화 부담액 {회원 번호: 원}. 균등 분할 또는 직접 입력 금액의 비율. 합계는 지출 원화 금액과 같다."""
    refs = [share.user_ref for share in shares]
    custom = expense.split_method == Expense.SplitMethod.CUSTOM
    if custom and all(share.custom_amount is not None for share in shares) and sum(share.custom_amount for share in shares) > 0:
        weights = {share.user_ref: share.custom_amount for share in shares}
        return settlement.split_by_weights(expense.amount_krw, weights, expense.payer_ref)
    return settlement.split_equally(expense.amount_krw, refs, expense.payer_ref)


def name_of(user, snapshot):
    """지금 닉네임. 탈퇴한 회원은 남겨 둔 이름."""
    if user is None:
        return snapshot or "탈퇴한 사용자"
    profile = getattr(user, "profile", None)  # 프로필이 없으면 AttributeError라서 getattr 기본값으로 걸러진다.
    return profile.nickname if profile and profile.nickname else nickname_of(user)


def accessible_trip(request, pk):
    return get_object_or_404(Trip.objects.accessible_to(request.user), pk=pk)


def summary(trip):
    """총예산·총지출·남은 예산(예산이 없으면 null)과 분류별 지출 합계."""
    totals = dict(trip.expenses.values_list("category").annotate(total=Sum("amount_krw")).order_by())
    by_category = {key: totals.get(key, 0) for key in Expense.Category.values}
    total = sum(by_category.values())
    budget = TripBudget.objects.filter(trip=trip).first()
    budget_krw = budget.amount_krw if budget else None
    return {
        "budget_krw": budget_krw,
        "total_krw": total,
        "remaining_krw": None if budget_krw is None else budget_krw - total,
        "by_category": by_category,
    }


class ExpenseListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trip = accessible_trip(request, pk)
        expenses = trip.expenses.select_related("payer__profile").prefetch_related("shares__user__profile")
        data = ExpenseSerializer(expenses, many=True, context={"request": request, "trip": trip}).data
        return Response({**summary(trip), "expenses": data})

    def post(self, request, pk):
        trip = accessible_trip(request, pk)
        serializer = ExpenseSerializer(data=request.data, context={"request": request, "trip": trip})
        serializer.is_valid(raise_exception=True)
        if trip.expenses.count() >= Expense.MAX_PER_TRIP:
            return Response(
                {"detail": f"지출은 {Expense.MAX_PER_TRIP}개까지 등록할 수 있어요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expense = serializer.save(trip=trip)
        return Response(
            ExpenseSerializer(expense, context={"request": request, "trip": trip}).data, status=status.HTTP_201_CREATED
        )


class ExpenseView(APIView):
    permission_classes = [IsAuthenticated]

    def get_expense(self, request, expense_id):
        return get_object_or_404(
            Expense.objects.select_related("payer__profile", "trip").prefetch_related("shares__user__profile"),
            pk=expense_id,
            trip__in=Trip.objects.accessible_to(request.user),
        )

    def patch(self, request, expense_id):
        expense = self.get_expense(request, expense_id)
        serializer = ExpenseSerializer(
            expense, data=request.data, partial=True, context={"request": request, "trip": expense.trip}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, expense_id):
        self.get_expense(request, expense_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BudgetView(APIView):
    """`PUT /trips/{id}/budget/` `{"amount_krw": 1000000}` 또는 `{"amount_krw": null}`(예산 지우기)."""

    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        trip = accessible_trip(request, pk)
        if "amount_krw" not in request.data:
            return Response({"detail": "예산 금액을 보내 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        value = request.data["amount_krw"]
        if value is None:
            TripBudget.objects.filter(trip=trip).delete()
            return Response({"budget_krw": None})
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= TripBudget.MAX_AMOUNT_KRW:
            return Response(
                {"detail": "예산은 0원 이상의 원 단위 금액으로 입력해 주세요."}, status=status.HTTP_400_BAD_REQUEST
            )
        budget, _ = TripBudget.objects.update_or_create(trip=trip, defaults={"amount_krw": value})
        return Response({"budget_krw": budget.amount_krw})


class ExpenseCurrenciesView(APIView):
    """`GET /trips/{id}/expense-currencies/` — 지출에 쓸 수 있는 통화와 지금 환율(1원당). 환율 서비스 오류는 502."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trip = accessible_trip(request, pk)
        city_codes = [entry.get("city_code") for entry in trip.destinations if isinstance(entry, dict)]
        try:
            return Response(expense_currency.overview([code for code in city_codes if code]))
        except travel_info.TravelInfoError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)


class SettlementView(APIView):
    """
    `GET /trips/{id}/settlement/` — 결제자·분담 인원을 정한 지출을 기준으로 한 사용자별 정산과 송금 안내.
    분담 인원이 없는 지출은 정산에서 빼고 건수만 알려 준다. 계산은 읽을 때마다 하므로 지출·일행이 바뀌면 바로 반영된다.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trip = accessible_trip(request, pk)
        expenses = trip.expenses.select_related("payer__profile").prefetch_related("shares__user__profile")
        shared, excluded = [], 0
        names = {}
        for expense in expenses:
            shares = list(expense.shares.all())
            if not shares or expense.payer_ref is None:
                excluded += 1
                continue
            shared.append((expense.amount_krw, expense.payer_ref, share_amounts(expense, shares)))
            names.setdefault(expense.payer_ref, name_of(expense.payer, expense.payer_name))
            for share in shares:
                names.setdefault(share.user_ref, name_of(share.user, share.user_name))

        current = [trip.owner_id, *trip.members.values_list("user_id", flat=True)]
        current = [ref for ref in current if ref]
        users = {user.id: user for user in User.objects.filter(pk__in=current).select_related("profile")}
        for ref in current:
            names[ref] = name_of(users.get(ref), "")  # 지금 함께하는 사람은 지금 닉네임
        balances, transfers = settlement.settle(shared, current)
        return Response(
            {
                "balances": [
                    {
                        "id": b["ref"],
                        "name": names.get(b["ref"], "탈퇴한 사용자"),
                        "paid_krw": b["paid"],
                        "share_krw": b["share"],
                        "net_krw": b["net"],
                        "active": b["ref"] in users,
                    }
                    for b in balances
                ],
                "transfers": [
                    {
                        "from_id": t["from"],
                        "from_name": names.get(t["from"], "탈퇴한 사용자"),
                        "to_id": t["to"],
                        "to_name": names.get(t["to"], "탈퇴한 사용자"),
                        "amount_krw": t["amount"],
                    }
                    for t in transfers
                ],
                "settled_krw": sum(amount for amount, _, _ in shared),
                "excluded_count": excluded,
            }
        )
