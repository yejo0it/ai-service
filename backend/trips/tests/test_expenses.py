"""
여행 경비 관리: 1단계(예산·지출, 원화)와 2단계(다중 통화·환율)

- 만든 회원과 일행이 같은 경비 내역을 보고 고친다. 그 밖의 회원에게는 여행이 없는 것(404)이다.
- 총지출·남은 예산·분류별 합계는 서버가 정수 원으로 계산한다.
- 결제자는 지출을 등록한 회원이고, 탈퇴해도 내역과 이름이 남는다.
- 현지 통화 지출은 등록할 때의 환율과 원화 환산 금액을 저장하고, 환율 서비스가 멈춰도 저장된 내역은 조회된다.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile

from .. import travel_info
from ..models import Expense, Trip, TripBudget, TripMember

User = get_user_model()


# 환율 서비스 응답(1원당 현지 통화 금액): 1엔 = 약 9.09원, 1달러 = 1,400원
ER_API = {
    "result": "success",
    "time_last_update_utc": "Wed, 21 Oct 2026 00:02:31 +0000",
    "rates": {"KRW": 1, "JPY": 0.11, "USD": 0.000714285714, "EUR": 0.00064},
}


class ExpenseTestBase(APITestCase):
    def setUp(self):
        cache.clear()  # 환율 캐시가 다른 테스트로 새지 않게
        patcher = mock.patch("trips.travel_info._get_json", side_effect=AssertionError("테스트에서 외부 환율 API를 부르면 안 돼요"))
        self.get_json = patcher.start()
        self.addCleanup(patcher.stop)
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

    def test_won_amount_and_rate_are_decided_by_the_server(self):
        created = self.add(amount_krw=1, rate_per_krw="0.1")  # 보낸 환산 금액·환율은 무시한다.
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
        guest_id = self.guest.id
        self.guest.delete()
        self.client.force_authenticate(self.owner)
        (expense,) = self.client.get(self.list_url).data["expenses"]
        self.assertEqual((expense["title"], expense["payer_id"], expense["payer_name"]), ("간식", guest_id, "일행"))  # 번호와 이름이 남는다

    def test_deleting_trip_removes_its_expenses_and_budget_only(self):
        other = Trip.objects.create(owner=self.owner, start_date="2026-12-01", end_date="2026-12-02")
        self.add()
        self.client.put(self.budget_url, {"amount_krw": 1000}, format="json")
        Expense.objects.create(trip=other, title="다른 여행", amount=1, amount_krw=1, spent_on="2026-12-01")
        self.trip.delete()
        self.assertEqual(list(Expense.objects.values_list("title", flat=True)), ["다른 여행"])
        self.assertFalse(TripBudget.objects.exists())


class MultiCurrencyTests(ExpenseTestBase):
    def setUp(self):
        super().setUp()
        self.get_json.side_effect = None
        self.get_json.return_value = ER_API

    def test_foreign_expense_stores_rate_and_won_amount(self):
        created = self.add(title="라멘", amount=1200, currency="JPY")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        # 1200엔 / 0.11 = 10,909.09원 -> 10,909원
        self.assertEqual((created.data["currency"], created.data["amount"], created.data["amount_krw"]), ("JPY", "1200.00", 10909))
        self.assertEqual(created.data["rate_per_krw"], "0.11")
        expense = Expense.objects.get()
        self.assertEqual((expense.currency, expense.amount_krw), ("JPY", 10909))

    def test_foreign_amounts_are_summed_in_won(self):
        self.add(amount=1200, currency="JPY")  # 10,909원
        self.add(amount="14.50", currency="USD")  # 14.5 / 0.000714285714 = 20,300.0000... -> 20,300원
        self.add(amount=5000, currency="KRW")
        data = self.client.get(self.list_url).data
        self.assertEqual(data["total_krw"], 10909 + 20300 + 5000)
        self.assertEqual(data["by_category"]["food"], 36209)

    def test_rounding_is_half_up_to_the_won(self):
        # 1엔(0.11) -> 9.0909원 -> 9원, 5원은 45.4545 -> 45원
        self.assertEqual(self.add(amount=1, currency="JPY").data["amount_krw"], 9)
        self.get_json.return_value = {**ER_API, "rates": {"JPY": 0.2, "KRW": 1}}
        cache.clear()
        self.assertEqual(self.add(amount=1, currency="JPY").data["amount_krw"], 5)  # 정확히 5원
        self.get_json.return_value = {**ER_API, "rates": {"JPY": 0.4, "KRW": 1}}
        cache.clear()
        self.assertEqual(self.add(amount=1, currency="JPY").data["amount_krw"], 3)  # 2.5원 -> 3원(0.5 올림)

    def test_decimal_places_follow_the_currency(self):
        self.assertEqual(self.add(amount="1200.5", currency="JPY").status_code, status.HTTP_400_BAD_REQUEST)  # 엔은 정수
        self.assertEqual(self.add(amount="14.505", currency="USD").status_code, status.HTTP_400_BAD_REQUEST)  # 달러는 소수 둘째까지
        self.assertEqual(self.add(amount="14.5", currency="USD").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.add(amount="12000.5", currency="KRW").status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_currency_is_rejected(self):
        self.assertEqual(self.add(currency="XXX").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add(currency="").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add(currency="jpy").data["currency"], "JPY")  # 소문자는 대문자로

    def test_too_large_converted_amount_is_rejected(self):
        self.assertEqual(self.add(amount="99999999999", currency="USD").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Expense.objects.count(), 0)

    def test_editing_amount_keeps_the_original_rate(self):
        created = self.add(amount=1200, currency="JPY")
        self.get_json.return_value = {**ER_API, "rates": {"JPY": 0.2, "KRW": 1}}  # 그 뒤 환율이 바뀌어도
        cache.clear()
        updated = self.client.patch(f"/api/v1/expenses/{created.data['id']}/", {"amount": 2200}, format="json")
        self.assertEqual((updated.data["rate_per_krw"], updated.data["amount_krw"]), ("0.11", 20000))  # 2200 / 0.11
        self.client.patch(f"/api/v1/expenses/{created.data['id']}/", {"title": "라멘 세트"}, format="json")
        self.assertEqual(Expense.objects.get().amount_krw, 20000)  # 이름만 고치면 금액·환율은 그대로

    def test_changing_currency_applies_a_new_rate(self):
        created = self.add(amount=1200, currency="JPY").data["id"]
        url = f"/api/v1/expenses/{created}/"
        usd = self.client.patch(url, {"currency": "USD", "amount": "10"}, format="json")
        self.assertEqual((usd.data["currency"], usd.data["amount_krw"]), ("USD", 14000))
        won = self.client.patch(url, {"currency": "KRW", "amount": 9000}, format="json")
        self.assertEqual((won.data["currency"], won.data["rate_per_krw"], won.data["amount_krw"]), ("KRW", None, 9000))

    def test_currency_change_must_fit_the_amount(self):
        created = self.add(amount="14.5", currency="USD").data["id"]
        response = self.client.patch(f"/api/v1/expenses/{created}/", {"currency": "JPY"}, format="json")  # 14.5엔은 불가
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Expense.objects.get().currency, "USD")


class RateServiceFailureTests(ExpenseTestBase):
    def stored_foreign_expense(self):
        self.get_json.side_effect = None
        self.get_json.return_value = ER_API
        created = self.add(amount=1200, currency="JPY").data["id"]
        cache.clear()
        self.get_json.side_effect = travel_info.TravelInfoError("정보를 불러오지 못했어요.")
        return created

    def test_stored_expenses_stay_readable_when_the_rate_service_fails(self):
        self.stored_foreign_expense()
        data = self.client.get(self.list_url).data
        self.assertEqual((data["total_krw"], data["expenses"][0]["amount_krw"], data["expenses"][0]["rate_per_krw"]), (10909, 10909, "0.11"))

    def test_won_expenses_and_edits_work_without_the_rate_service(self):
        created = self.stored_foreign_expense()
        self.assertEqual(self.add(title="택시", amount=3000).status_code, status.HTTP_201_CREATED)
        edited = self.client.patch(f"/api/v1/expenses/{created}/", {"amount": 2400}, format="json")  # 같은 통화는 저장된 환율로
        self.assertEqual((edited.status_code, edited.data["amount_krw"]), (status.HTTP_200_OK, 21818))

    def test_new_foreign_expense_fails_clearly_without_the_rate_service(self):
        self.stored_foreign_expense()
        response = self.add(amount=10, currency="USD")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("환율", response.data["detail"])
        self.assertEqual(Expense.objects.count(), 1)  # 아무것도 저장하지 않는다.

    def test_unknown_currency_rate_is_a_service_error(self):
        self.get_json.side_effect = None
        self.get_json.return_value = {**ER_API, "rates": {"KRW": 1}}  # 제공처 응답에 엔이 없는 경우
        self.assertEqual(self.add(amount=10, currency="JPY").status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class ExpenseCurrenciesTests(ExpenseTestBase):
    def url(self):
        return f"/api/v1/trips/{self.trip.id}/expense-currencies/"

    def test_lists_currencies_with_trip_currencies_first_info(self):
        self.get_json.side_effect = None
        self.get_json.return_value = ER_API
        data = self.client.get(self.url()).data
        self.assertEqual(data["trip_currencies"], ["JPY"])  # 도쿄 여행
        by_code = {item["currency"]: item for item in data["currencies"]}
        self.assertEqual({"JPY", "USD", "EUR"}, set(by_code))  # 제공처에 환율이 있는 통화만
        self.assertEqual((by_code["JPY"]["decimals"], by_code["USD"]["decimals"]), (0, 2))
        self.assertEqual(by_code["JPY"]["per_krw"], "0.11")
        self.assertTrue(by_code["USD"]["flag"] and by_code["USD"]["name"])
        self.assertEqual(data["updated_at"], ER_API["time_last_update_utc"])

    def test_service_error_and_access(self):
        self.get_json.side_effect = travel_info.TravelInfoError("정보를 불러오지 못했어요.")
        self.assertEqual(self.client.get(self.url()).status_code, status.HTTP_502_BAD_GATEWAY)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.url()).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.guest)
        self.get_json.side_effect = None
        self.get_json.return_value = ER_API
        self.assertEqual(self.client.get(self.url()).status_code, status.HTTP_200_OK)
