"""
여행 경비 관리 (1단계: 예산과 지출, 원화).

- 만든 회원과 일행이 같은 경비 내역을 보고 고친다. 그 밖의 회원에게는 여행이 없는 것(404)이다.
- GET  /trips/{id}/expenses/  예산·총지출·남은 예산·분류별 합계와 지출 목록
- POST /trips/{id}/expenses/  지출 등록
- PATCH/DELETE /expenses/{id}/  지출 수정·삭제
- PUT  /trips/{id}/budget/    총예산 설정·수정(null이면 예산을 지운다)
- GET  /trips/{id}/expense-currencies/  지출 입력에서 고를 통화와 지금 환율
지출은 현지 통화로 입력할 수 있고, 등록할 때의 환율과 원화 환산 금액을 함께 저장한다
(환율 서비스가 멈춰도 저장된 내역은 그대로 조회된다). 금액은 Decimal/정수로만 계산한다.
"""

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.nickname import nickname_of

from . import expense_currency, travel_info
from .models import Expense, Trip, TripBudget


class ExchangeRateUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "환율을 불러오지 못했어요. 원화로 입력하거나 잠시 후 다시 시도해 주세요."
    default_code = "exchange_rate_unavailable"


class ExpenseSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False, default=expense_currency.KRW)
    # 지출 당시 적용한 환율(1원당 현지 통화 금액). 원화 지출은 null
    rate_per_krw = serializers.SerializerMethodField()
    payer_id = serializers.IntegerField(read_only=True)
    payer_name = serializers.SerializerMethodField()

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
        )
        # 환율과 원화 환산 금액은 서버가 정한다.
        read_only_fields = ("id", "amount_krw")

    def get_rate_per_krw(self, expense):
        return None if expense.rate_per_krw is None else format(expense.rate_per_krw.normalize(), "f")

    def get_payer_name(self, expense):
        # 결제자가 있으면 지금 닉네임, 탈퇴했으면 남겨 둔 이름
        return nickname_of(expense.payer) if expense.payer else (expense.payer_name or "탈퇴한 사용자")

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
        return attrs

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

    def create(self, validated_data):
        return super().create(self._with_krw(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._with_krw(validated_data, instance))


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
        expenses = trip.expenses.select_related("payer")
        return Response({**summary(trip), "expenses": ExpenseSerializer(expenses, many=True).data})

    def post(self, request, pk):
        trip = accessible_trip(request, pk)
        serializer = ExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if trip.expenses.count() >= Expense.MAX_PER_TRIP:
            return Response(
                {"detail": f"지출은 {Expense.MAX_PER_TRIP}개까지 등록할 수 있어요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expense = serializer.save(trip=trip, payer=request.user, payer_name=nickname_of(request.user)[:30])
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)


class ExpenseView(APIView):
    permission_classes = [IsAuthenticated]

    def get_expense(self, request, expense_id):
        return get_object_or_404(
            Expense.objects.select_related("payer"),
            pk=expense_id,
            trip__in=Trip.objects.accessible_to(request.user),
        )

    def patch(self, request, expense_id):
        expense = self.get_expense(request, expense_id)
        serializer = ExpenseSerializer(expense, data=request.data, partial=True)
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
