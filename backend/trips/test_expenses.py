"""
여행 경비 관리 1단계(예산·지출, 원화)

- 만든 회원과 일행이 같은 경비 내역을 보고 고친다. 그 밖의 회원에게는 여행이 없는 것(404)이다.
- 총지출·남은 예산·분류별 합계는 서버가 정수 원으로 계산한다.
- 결제자는 지출을 등록한 회원이고, 탈퇴해도 내역과 이름이 남는다.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile

from .models import Expense, Trip, TripBudget, TripMember

User = get_user_model()


class ExpenseTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.guest = User.objects.create_user(username="guest@example.com", email="guest@example.com")
        self.stranger = User.objects.create_user(username="stranger@example.com", email="stranger@example.com")
        Profile.objects.create(user=self.owner, nickname="만든이")
        Profile.objects.create(user=self.guest, nickname="일행")
        self.trip = Trip.objects.create(
            owner=self.owner,
            destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date="2026-11-10",
            end_date="2026-11-12",
            itinerary_initialized=True,
        )
        TripMember.objects.create(trip=self.trip, user=self.guest)
        self.client.force_authenticate(self.owner)

    @property
    def list_url(self):
        return f"/api/v1/trips/{self.trip.id}/expenses/"

    @property
    def budget_url(self):
        return f"/api/v1/trips/{self.trip.id}/budget/"

    def add(self, **body):
        data = {"title": "라멘", "amount": 12000, "spent_on": "2026-11-10", "category": "food", **body}
        return self.client.post(self.list_url, data, format="json")


class ExpenseCrudTests(ExpenseTestBase):
    def test_create_list_update_delete(self):
        created = self.add(memo="이치란")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["amount_krw"], 12000)
        self.assertEqual(created.data["currency"], "KRW")
        self.assertIsNone(created.data["rate_per_krw"])
        self.assertEqual((created.data["payer_id"], created.data["payer_name"]), (self.owner.id, "만든이"))

        listed = self.client.get(self.list_url)
        self.assertEqual([e["title"] for e in listed.data["expenses"]], ["라멘"])

        url = f"/api/v1/expenses/{created.data['id']}/"
        updated = self.client.patch(url, {"amount": 15000, "title": "라멘 세트", "category": "food"}, format="json")
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual((updated.data["title"], updated.data["amount_krw"]), ("라멘 세트", 15000))  # 환산 금액도 다시 계산
        self.assertEqual(self.client.get(self.list_url).data["total_krw"], 15000)

        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(self.list_url).data["expenses"], [])
        self.assertEqual(self.client.get(self.list_url).data["total_krw"], 0)

    def test_list_is_ordered_by_date_newest_first(self):
        self.add(title="첫날", spent_on="2026-11-10")
        self.add(title="마지막 날", spent_on="2026-11-12")
        self.add(title="둘째 날", spent_on="2026-11-11")
        titles = [e["title"] for e in self.client.get(self.list_url).data["expenses"]]
        self.assertEqual(titles, ["마지막 날", "둘째 날", "첫날"])

    def test_validation(self):
        for body in (
            {"title": "  "},  # 공백 지출명
            {"amount": 0},
            {"amount": -100},
            {"amount": "12000.5"},  # 원화는 원 단위
            {"amount": 100_000_000_000},  # 한도 초과
            {"category": "luxury"},
            {"spent_on": "2026-13-40"},
        ):
            self.assertEqual(self.add(**body).status_code, status.HTTP_400_BAD_REQUEST, body)
        self.assertEqual(Expense.objects.count(), 0)

    def test_currency_and_won_amount_are_decided_by_the_server(self):
        created = self.add(currency="JPY", amount_krw=1, rate_per_krw="0.1")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual((created.data["currency"], created.data["amount_krw"], created.data["rate_per_krw"]), ("KRW", 12000, None))

    def test_limit_per_trip(self):
        with mock.patch.object(Expense, "MAX_PER_TRIP", 2):
            self.assertEqual(self.add().status_code, status.HTTP_201_CREATED)
            self.assertEqual(self.add().status_code, status.HTTP_201_CREATED)
            self.assertEqual(self.add().status_code, status.HTTP_400_BAD_REQUEST)

    def test_amounts_are_exact_integers(self):
        for amount in (33333, 33333, 33334):
            self.add(amount=amount)
        data = self.client.get(self.list_url).data
        self.assertEqual(data["total_krw"], 100000)
        self.assertTrue(all(isinstance(e["amount_krw"], int) for e in data["expenses"]))


class BudgetSummaryTests(ExpenseTestBase):
    def test_no_budget_means_null(self):
        data = self.client.get(self.list_url).data
        self.assertEqual((data["budget_krw"], data["remaining_krw"], data["total_krw"]), (None, None, 0))
        self.assertEqual(set(data["by_category"]), {"transport", "lodging", "food", "sightseeing", "shopping", "etc"})

    def test_set_update_and_clear_budget(self):
        self.assertEqual(self.client.put(self.budget_url, {"amount_krw": 1000000}, format="json").data, {"budget_krw": 1000000})
        self.client.put(self.budget_url, {"amount_krw": 800000}, format="json")
        self.assertEqual(TripBudget.objects.filter(trip=self.trip).count(), 1)  # 하나만 둔다
        self.assertEqual(self.client.get(self.list_url).data["budget_krw"], 800000)
        self.assertEqual(self.client.put(self.budget_url, {"amount_krw": None}, format="json").data, {"budget_krw": None})
        self.assertFalse(TripBudget.objects.filter(trip=self.trip).exists())

    def test_invalid_budget(self):
        for body in ({}, {"amount_krw": -1}, {"amount_krw": "100"}, {"amount_krw": 1.5}, {"amount_krw": True},
                     {"amount_krw": 100_000_000_000}):
            self.assertEqual(self.client.put(self.budget_url, body, format="json").status_code, status.HTTP_400_BAD_REQUEST, body)

    def test_totals_remaining_and_category_sums(self):
        self.client.put(self.budget_url, {"amount_krw": 100000}, format="json")
        self.add(amount=30000, category="food")
        self.add(amount=20000, category="food")
        self.add(amount=50000, category="transport")
        data = self.client.get(self.list_url).data
        self.assertEqual((data["total_krw"], data["remaining_krw"]), (100000, 0))
        self.assertEqual((data["by_category"]["food"], data["by_category"]["transport"], data["by_category"]["etc"]), (50000, 50000, 0))
        self.add(amount=1000, category="shopping")
        self.assertEqual(self.client.get(self.list_url).data["remaining_krw"], -1000)  # 초과하면 음수

    def test_summary_follows_edits_and_deletes(self):
        first = self.add(amount=10000, category="food").data["id"]
        self.client.patch(f"/api/v1/expenses/{first}/", {"category": "shopping", "amount": 7000}, format="json")
        data = self.client.get(self.list_url).data
        self.assertEqual((data["by_category"]["food"], data["by_category"]["shopping"], data["total_krw"]), (0, 7000, 7000))
        self.client.delete(f"/api/v1/expenses/{first}/")
        self.assertEqual(self.client.get(self.list_url).data["total_krw"], 0)


class ExpenseAccessTests(ExpenseTestBase):
    def test_member_shares_the_same_expenses(self):
        expense_id = self.add(title="택시").data["id"]
        self.client.force_authenticate(self.guest)
        self.assertEqual([e["title"] for e in self.client.get(self.list_url).data["expenses"]], ["택시"])
        mine = self.add(title="간식")
        self.assertEqual(mine.data["payer_name"], "일행")
        self.assertEqual(self.client.patch(f"/api/v1/expenses/{expense_id}/", {"title": "공항 택시"}, format="json").status_code, 200)
        self.assertEqual(self.client.put(self.budget_url, {"amount_krw": 500000}, format="json").status_code, 200)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.list_url).data["budget_krw"], 500000)
        self.assertEqual(len(self.client.get(self.list_url).data["expenses"]), 2)

    def test_stranger_cannot_see_or_change_anything(self):
        expense_id = self.add().data["id"]
        self.client.force_authenticate(self.stranger)
        item_url = f"/api/v1/expenses/{expense_id}/"
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.add().status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.put(self.budget_url, {"amount_krw": 1}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(item_url, {"title": "x"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(item_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Expense.objects.get(pk=expense_id).title, "라멘")

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.list_url).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_removed_member_loses_access_but_expenses_stay(self):
        self.client.force_authenticate(self.guest)
        self.add(title="간식")
        TripMember.objects.filter(trip=self.trip, user=self.guest).delete()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.owner)
        data = self.client.get(self.list_url).data
        self.assertEqual([(e["title"], e["payer_name"]) for e in data["expenses"]], [("간식", "일행")])  # 내역과 결제자는 남는다

    def test_withdrawn_payer_keeps_the_record(self):
        self.client.force_authenticate(self.guest)
        self.add(title="간식")
        self.guest.delete()
        self.client.force_authenticate(self.owner)
        (expense,) = self.client.get(self.list_url).data["expenses"]
        self.assertEqual((expense["title"], expense["payer_id"], expense["payer_name"]), ("간식", None, "일행"))

    def test_deleting_trip_removes_its_expenses_and_budget_only(self):
        other = Trip.objects.create(owner=self.owner, start_date="2026-12-01", end_date="2026-12-02")
        self.add()
        self.client.put(self.budget_url, {"amount_krw": 1000}, format="json")
        Expense.objects.create(trip=other, title="다른 여행", amount=1, amount_krw=1, spent_on="2026-12-01")
        self.trip.delete()
        self.assertEqual(list(Expense.objects.values_list("title", flat=True)), ["다른 여행"])
        self.assertFalse(TripBudget.objects.exists())
