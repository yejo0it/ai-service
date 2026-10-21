"""
여행 경비 관리 (1단계: 예산과 지출, 원화).

- 만든 회원과 일행이 같은 경비 내역을 보고 고친다. 그 밖의 회원에게는 여행이 없는 것(404)이다.
- GET  /trips/{id}/expenses/  예산·총지출·남은 예산·분류별 합계와 지출 목록
- POST /trips/{id}/expenses/  지출 등록
- PATCH/DELETE /expenses/{id}/  지출 수정·삭제
- PUT  /trips/{id}/budget/    총예산 설정·수정(null이면 예산을 지운다)
금액은 Decimal/정수로만 계산한다.
"""

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.nickname import nickname_of

from .models import Expense, Trip, TripBudget


class ExpenseSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
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
        # 1단계는 원화만 받는다. 통화·환율·환산 금액은 서버가 정한다.
        read_only_fields = ("id", "currency", "amount_krw", "rate_per_krw")

    def get_payer_name(self, expense):
        # 결제자가 있으면 지금 닉네임, 탈퇴했으면 남겨 둔 이름
        return nickname_of(expense.payer) if expense.payer else (expense.payer_name or "탈퇴한 사용자")

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("지출명을 입력해 주세요.")
        return value

    def validate_amount(self, value):
        if value != value.to_integral_value():
            raise serializers.ValidationError("원화는 원 단위로 입력해 주세요.")
        if value > Expense.MAX_AMOUNT_KRW:
            raise serializers.ValidationError("금액이 너무 커요.")
        return value

    def create(self, validated_data):
        validated_data["amount_krw"] = int(validated_data["amount"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "amount" in validated_data:
            validated_data["amount_krw"] = int(validated_data["amount"])
        return super().update(instance, validated_data)


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
