"""
여행 경비 3단계: 결제자·분담 인원·정산

- 지출마다 결제자와 비용을 나눌 인원(여행에 함께하는 사람)을 고르고, 선택한 인원끼리 균등 분할한다.
- 나누어떨어지지 않는 나머지(원)는 1원씩 더 부담해 합계가 지출 금액과 정확히 맞는다.
- 정산은 읽을 때 계산하므로 지출 수정·삭제, 일행 변경이 바로 반영된다.
- 탈퇴·나간 사람도 내역과 정산에 남는다.
- 분담 방식은 균등 분할 또는 직접 입력이다. 직접 입력은 합계가 지출 금액과 정확히 같아야 하고,
  사람마다 입력한 금액의 비율로 원화 부담액을 정한다(나머지 원은 최대 잔여법).
"""

import random
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile

from .. import settlement
from ..models import Expense, ExpenseShare, Trip, TripMember

User = get_user_model()


def eq(amount, payer, refs):
    """정산 입력 한 건: 균등 분할한 부담액"""
    return (amount, payer, settlement.split_equally(amount, refs, payer))


class SplitEquallyTests(APITestCase):
    def test_exact_division(self):
        self.assertEqual(settlement.split_equally(30000, [1, 2, 3]), {1: 10000, 2: 10000, 3: 10000})

    def test_remainder_is_split_one_won_at_a_time_and_total_matches(self):
        shares = settlement.split_equally(10000, [3, 1, 2])
        self.assertEqual(sum(shares.values()), 10000)
        self.assertEqual(sorted(shares.values()), [3333, 3333, 3334])
        self.assertEqual(shares[1], 3334)  # 나머지 1원은 번호가 가장 작은 사람부터

    def test_payer_takes_the_remainder_first(self):
        shares = settlement.split_equally(10000, [1, 2, 3], payer_ref=3)
        self.assertEqual(shares, {1: 3333, 2: 3333, 3: 3334})
        shares = settlement.split_equally(10001, [1, 2, 3], payer_ref=3)  # 나머지 2원: 결제자, 그다음 번호순
        self.assertEqual(shares, {1: 3334, 2: 3333, 3: 3334})

    def test_one_person_and_tiny_amounts(self):
        self.assertEqual(settlement.split_equally(7, [5]), {5: 7})
        shares = settlement.split_equally(2, [1, 2, 3])  # 사람보다 금액이 작아도 합계는 맞는다.
        self.assertEqual((sum(shares.values()), sorted(shares.values())), (2, [0, 1, 1]))
        self.assertEqual(settlement.split_equally(5, [1, 1, 2]), {1: 3, 2: 2})  # 중복 번호는 한 명으로

    def test_total_always_matches(self):
        rng = random.Random(1)
        for _ in range(300):
            refs = rng.sample(range(1, 40), rng.randint(1, 11))
            amount = rng.randint(0, 5_000_000)
            shares = settlement.split_equally(amount, refs, rng.choice([None, *refs]))
            self.assertEqual(sum(shares.values()), amount)
            self.assertLessEqual(max(shares.values()) - min(shares.values()), 1)


class SplitByWeightsTests(APITestCase):
    def test_exact_amounts_are_kept(self):
        self.assertEqual(settlement.split_by_weights(10000, {1: Decimal(7000), 2: Decimal(3000)}), {1: 7000, 2: 3000})

    def test_foreign_currency_weights_follow_the_ratio(self):
        # 1,000엔을 600엔/400엔으로 나눴고 원화 환산이 9,091원이면 비율대로 5,455 / 3,636원
        shares = settlement.split_by_weights(9091, {1: Decimal(600), 2: Decimal(400)})
        self.assertEqual(shares, {1: 5455, 2: 3636})
        self.assertEqual(sum(shares.values()), 9091)

    def test_largest_remainder_gets_the_extra_won(self):
        # 100원을 1:1:1로 나누면 33.33.. 씩 -> 나머지 1원은 번호가 작은 사람(결제자 없음)
        self.assertEqual(settlement.split_by_weights(100, {3: Decimal(1), 1: Decimal(1), 2: Decimal(1)}), {1: 34, 2: 33, 3: 33})
        # 소수 부분이 가장 큰 사람이 먼저: 10원 / (0.5, 0.3, 0.2) 비율이 아니라 (2.0, 1.1, 0.9)
        shares = settlement.split_by_weights(10, {1: Decimal("2.0"), 2: Decimal("1.1"), 3: Decimal("0.9")})
        self.assertEqual(sum(shares.values()), 10)

    def test_zero_weights_and_total_always_matches(self):
        self.assertEqual(settlement.split_by_weights(500, {1: Decimal(0), 2: Decimal(10)}), {1: 0, 2: 500})
        rng = random.Random(3)
        for _ in range(300):
            refs = rng.sample(range(1, 40), rng.randint(1, 8))
            weights = {ref: Decimal(rng.randint(0, 100000)) / 100 for ref in refs}
            if sum(weights.values()) == 0:
                continue
            amount = rng.randint(0, 3_000_000)
            shares = settlement.split_by_weights(amount, weights, rng.choice([None, *refs]))
            self.assertEqual(sum(shares.values()), amount)
            self.assertTrue(all(value >= 0 for value in shares.values()))


class SettleTests(APITestCase):
    def test_who_sends_how_much_to_whom(self):
        # A가 90,000원을 셋이 나누고, B가 30,000원을 A·B가 나눈다.
        balances, transfers = settlement.settle([eq(90000, 1, [1, 2, 3]), eq(30000, 2, [1, 2])], [1, 2, 3])
        net = {b["ref"]: b["net"] for b in balances}
        self.assertEqual(net, {1: 90000 - 30000 - 15000, 2: 30000 - 30000 - 15000, 3: -30000})
        self.assertEqual(sum(net.values()), 0)
        self.assertEqual(
            transfers,
            [{"from": 3, "to": 1, "amount": 30000}, {"from": 2, "to": 1, "amount": 15000}],
        )

    def test_transfers_settle_everyone_exactly(self):
        rng = random.Random(7)
        for _ in range(200):
            people = rng.sample(range(1, 30), rng.randint(2, 8))
            expenses = [
                eq(rng.randint(1, 300000), rng.choice(people), rng.sample(people, rng.randint(1, len(people))))
                for _ in range(rng.randint(1, 12))
            ]
            balances, transfers = settlement.settle(expenses, people)
            self.assertEqual(sum(b["net"] for b in balances), 0)
            remaining = {b["ref"]: b["net"] for b in balances}
            for t in transfers:
                self.assertGreater(t["amount"], 0)
                remaining[t["from"]] += t["amount"]
                remaining[t["to"]] -= t["amount"]
            self.assertEqual(set(remaining.values()), {0})  # 송금하면 모두 0원
            self.assertLessEqual(len(transfers), len(people) - 1)

    def test_nothing_to_settle(self):
        balances, transfers = settlement.settle([eq(10000, 1, [1])], [1, 2])
        self.assertEqual(transfers, [])
        self.assertEqual([(b["ref"], b["paid"], b["share"], b["net"]) for b in balances], [(1, 10000, 10000, 0), (2, 0, 0, 0)])

    def test_payer_not_in_participants(self):
        balances, transfers = settlement.settle([eq(10000, 1, [2, 3])], [1, 2, 3])
        self.assertEqual({b["ref"]: b["net"] for b in balances}, {1: 10000, 2: -5000, 3: -5000})
        self.assertEqual(sorted((t["from"], t["to"], t["amount"]) for t in transfers), [(2, 1, 5000), (3, 1, 5000)])


class SettlementApiBase(APITestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("trips.travel_info._get_json", side_effect=AssertionError("외부 환율 API 호출 금지"))
        self.get_json = patcher.start()
        self.addCleanup(patcher.stop)
        make = lambda name, nick: User.objects.create_user(username=f"{name}@example.com", email=f"{name}@example.com")
        self.a = make("a", "에이")
        self.b = make("b", "비")
        self.c = make("c", "씨")
        self.stranger = make("x", "남")
        for user, nick in ((self.a, "에이"), (self.b, "비"), (self.c, "씨"), (self.stranger, "남")):
            Profile.objects.create(user=user, nickname=nick)
        self.trip = Trip.objects.create(
            owner=self.a,
            destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date="2026-11-10",
            end_date="2026-11-12",
            itinerary_initialized=True,
        )
        TripMember.objects.create(trip=self.trip, user=self.b)
        TripMember.objects.create(trip=self.trip, user=self.c)
        self.client.force_authenticate(self.a)

    @property
    def list_url(self):
        return f"/api/v1/trips/{self.trip.id}/expenses/"

    @property
    def settlement_url(self):
        return f"/api/v1/trips/{self.trip.id}/settlement/"

    def add(self, **body):
        data = {"title": "저녁", "amount": 90000, "spent_on": "2026-11-10", "category": "food", **body}
        return self.client.post(self.list_url, data, format="json")

    def settlement(self):
        return self.client.get(self.settlement_url).data

    def transfers(self):
        return [(t["from_name"], t["to_name"], t["amount_krw"]) for t in self.settlement()["transfers"]]


class PayerAndParticipantsTests(SettlementApiBase):
    def test_defaults_payer_to_creator_and_no_participants(self):
        created = self.add()
        self.assertEqual((created.data["payer_id"], created.data["payer_name"], created.data["participants"]), (self.a.id, "에이", []))

    def test_choose_payer_and_participants(self):
        created = self.add(payer_id=self.b.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual((created.data["payer_id"], created.data["payer_name"]), (self.b.id, "비"))
        self.assertEqual(
            [(p["name"], p["share_krw"]) for p in created.data["participants"]],
            [("에이", 30000), ("비", 30000), ("씨", 30000)],
        )

    def test_indivisible_amount_shows_each_share_and_sums_exactly(self):
        created = self.add(amount=10000, payer_id=self.c.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        shares = {p["name"]: p["share_krw"] for p in created.data["participants"]}
        self.assertEqual(sum(shares.values()), 10000)
        self.assertEqual(shares, {"에이": 3333, "비": 3333, "씨": 3334})  # 나머지 1원은 결제자(씨)가

    def test_only_trip_people_can_be_chosen(self):
        for body in ({"payer_id": self.stranger.id}, {"participant_ids": [self.a.id, self.stranger.id]},
                     {"participant_ids": []}, {"participant_ids": [0]}, {"payer_id": 0}):
            self.assertEqual(self.add(**body).status_code, status.HTTP_400_BAD_REQUEST, body)
        self.assertEqual(Expense.objects.count(), 0)

    def test_duplicates_are_merged(self):
        created = self.add(amount=10000, participant_ids=[self.a.id, self.a.id, self.b.id])
        self.assertEqual([p["id"] for p in created.data["participants"]], [self.a.id, self.b.id])

    def test_edit_participants_and_payer(self):
        expense_id = self.add(participant_ids=[self.a.id, self.b.id, self.c.id]).data["id"]
        url = f"/api/v1/expenses/{expense_id}/"
        edited = self.client.patch(url, {"participant_ids": [self.a.id, self.b.id], "payer_id": self.b.id}, format="json")
        self.assertEqual([(p["name"], p["share_krw"]) for p in edited.data["participants"]], [("에이", 45000), ("비", 45000)])
        self.assertEqual(edited.data["payer_name"], "비")
        self.assertEqual(ExpenseShare.objects.filter(expense_id=expense_id).count(), 2)
        # 금액만 고쳐도 인원은 그대로, 부담액은 다시 계산된다.
        again = self.client.patch(url, {"amount": 50001}, format="json")
        self.assertEqual(sorted(p["share_krw"] for p in again.data["participants"]), [25000, 25001])
        self.assertEqual(sum(p["share_krw"] for p in again.data["participants"]), 50001)


class SettlementApiTests(SettlementApiBase):
    def test_settlement_who_pays_whom(self):
        self.add(amount=90000, payer_id=self.a.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        self.add(amount=30000, payer_id=self.b.id, participant_ids=[self.a.id, self.b.id])
        data = self.settlement()
        by_name = {b["name"]: (b["paid_krw"], b["share_krw"], b["net_krw"]) for b in data["balances"]}
        self.assertEqual(by_name, {"에이": (90000, 45000, 45000), "비": (30000, 45000, -15000), "씨": (0, 30000, -30000)})
        self.assertEqual(self.transfers(), [("씨", "에이", 30000), ("비", "에이", 15000)])
        self.assertEqual((data["settled_krw"], data["excluded_count"]), (120000, 0))

    def test_foreign_currency_is_settled_in_won(self):
        self.get_json.side_effect = None
        self.get_json.return_value = {"result": "success", "time_last_update_utc": "x", "rates": {"JPY": 0.1, "KRW": 1}}
        self.add(amount=3000, currency="JPY", payer_id=self.b.id, participant_ids=[self.a.id, self.b.id])  # 30,000원
        self.assertEqual(self.transfers(), [("에이", "비", 15000)])

    def test_expenses_without_participants_are_left_out(self):
        self.add(amount=50000)  # 인원 미지정(1·2단계에서 만든 내역과 같다)
        self.add(amount=20000, participant_ids=[self.a.id, self.b.id])
        data = self.settlement()
        self.assertEqual((data["settled_krw"], data["excluded_count"]), (20000, 1))
        self.assertEqual(self.transfers(), [("비", "에이", 10000)])

    def test_empty_trip_lists_everyone_with_zero(self):
        data = self.settlement()
        self.assertEqual(sorted(b["name"] for b in data["balances"]), ["비", "씨", "에이"])
        self.assertEqual((data["transfers"], data["settled_krw"], data["excluded_count"]), ([], 0, 0))

    def test_recalculates_after_edit_and_delete(self):
        first = self.add(amount=60000, payer_id=self.a.id, participant_ids=[self.a.id, self.b.id, self.c.id]).data["id"]
        second = self.add(amount=30000, payer_id=self.c.id, participant_ids=[self.a.id, self.c.id]).data["id"]
        self.assertEqual(self.transfers(), [("비", "에이", 20000), ("씨", "에이", 5000)])
        self.client.patch(f"/api/v1/expenses/{first}/", {"amount": 30000}, format="json")  # 금액 수정
        self.assertEqual(self.transfers(), [("비", "에이", 5000), ("비", "씨", 5000)])
        self.client.patch(f"/api/v1/expenses/{first}/", {"participant_ids": [self.a.id, self.b.id]}, format="json")  # 인원 수정
        self.assertEqual(self.transfers(), [("비", "씨", 15000)])
        self.client.delete(f"/api/v1/expenses/{second}/")  # 삭제
        self.assertEqual(self.transfers(), [("비", "에이", 15000)])
        self.client.delete(f"/api/v1/expenses/{first}/")
        self.assertEqual(self.settlement()["transfers"], [])

    def test_access(self):
        self.add(participant_ids=[self.a.id])
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.get(self.settlement_url).status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.settlement_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.add(participant_ids=[self.a.id]).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.settlement_url).status_code, (401, 403))


class MembershipChangeTests(SettlementApiBase):
    def test_member_who_left_stays_in_existing_expenses_and_settlement(self):
        self.add(amount=90000, payer_id=self.b.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        TripMember.objects.filter(trip=self.trip, user=self.c).delete()  # 씨가 나감
        data = self.settlement()
        by_name = {b["name"]: b["active"] for b in data["balances"]}
        self.assertEqual(by_name, {"에이": True, "비": True, "씨": False})  # 나간 일행으로 남는다.
        self.assertEqual(self.transfers(), [("에이", "비", 30000), ("씨", "비", 30000)])
        listed = self.client.get(self.list_url).data["expenses"][0]
        self.assertEqual([p["name"] for p in listed["participants"]], ["에이", "비", "씨"])

    def test_left_member_cannot_be_chosen_again_but_can_stay_on_old_expense(self):
        expense_id = self.add(amount=60000, participant_ids=[self.a.id, self.b.id, self.c.id]).data["id"]
        TripMember.objects.filter(trip=self.trip, user=self.c).delete()
        self.assertEqual(self.add(participant_ids=[self.a.id, self.c.id]).status_code, status.HTTP_400_BAD_REQUEST)
        edited = self.client.patch(f"/api/v1/expenses/{expense_id}/", {"participant_ids": [self.a.id, self.b.id, self.c.id], "title": "수정"}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)  # 이 지출에 이미 있던 사람은 그대로 둘 수 있다.
        self.assertEqual(len(edited.data["participants"]), 3)
        dropped = self.client.patch(f"/api/v1/expenses/{expense_id}/", {"participant_ids": [self.a.id, self.b.id]}, format="json")
        self.assertEqual([p["share_krw"] for p in dropped.data["participants"]], [30000, 30000])  # 빼는 것도 가능

    def test_new_member_can_be_added_to_new_expenses(self):
        late = User.objects.create_user(username="late@example.com", email="late@example.com")
        Profile.objects.create(user=late, nickname="늦참")
        self.assertEqual(self.add(participant_ids=[self.a.id, late.id]).status_code, status.HTTP_400_BAD_REQUEST)  # 아직 일행이 아님
        TripMember.objects.create(trip=self.trip, user=late)
        self.assertEqual(self.add(participant_ids=[self.a.id, late.id]).status_code, status.HTTP_201_CREATED)

    def test_withdrawn_member_keeps_name_and_balance(self):
        self.add(amount=90000, payer_id=self.b.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        self.c.delete()  # 회원 탈퇴
        data = self.settlement()
        by_name = {b["name"]: (b["share_krw"], b["active"]) for b in data["balances"]}
        self.assertEqual(by_name["씨"], (30000, False))  # 탈퇴해도 부담액이 남아 정산이 어긋나지 않는다.
        self.assertEqual(sum(b["net_krw"] for b in data["balances"]), 0)
        listed = self.client.get(self.list_url).data["expenses"][0]
        self.assertEqual([p["name"] for p in listed["participants"]], ["에이", "비", "씨"])

    def test_withdrawn_payer_is_kept(self):
        self.add(amount=90000, payer_id=self.c.id, participant_ids=[self.a.id, self.b.id, self.c.id])
        self.c.delete()
        listed = self.client.get(self.list_url).data["expenses"][0]
        self.assertEqual((listed["payer_name"], listed["payer_id"] is not None), ("씨", True))
        self.assertEqual(self.transfers(), [("에이", "씨", 30000), ("비", "씨", 30000)])

    def test_deleting_trip_removes_shares(self):
        self.add(participant_ids=[self.a.id, self.b.id])
        self.trip.delete()
        self.assertEqual(ExpenseShare.objects.count(), 0)


class LegacyDataTests(SettlementApiBase):
    def test_expense_from_before_settlement_has_payer_and_no_participants(self):
        expense = Expense.objects.create(trip=self.trip, title="예전", amount=1000, amount_krw=1000, spent_on="2026-11-10",
                                         payer=self.b, payer_name="비")  # payer_ref가 비어 있는 예전 데이터
        listed = self.client.get(self.list_url).data["expenses"][0]
        self.assertEqual((listed["payer_name"], listed["participants"]), ("비", []))
        self.assertEqual(self.settlement()["excluded_count"], 1)
        # 그 지출에 인원을 정해 주면 정산에 들어간다(결제자 번호도 채워진다).
        edited = self.client.patch(f"/api/v1/expenses/{expense.id}/", {"payer_id": self.b.id, "participant_ids": [self.a.id, self.b.id]}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertEqual(self.transfers(), [("에이", "비", 500)])


class CustomSplitTests(SettlementApiBase):
    def custom(self, amounts, **body):
        """amounts: {사용자: 금액}"""
        return self.add(split_method="custom", participant_amounts=[{"id": u.id, "amount": a} for u, a in amounts.items()], **body)

    def test_custom_split_amounts_are_kept(self):
        created = self.custom({self.a: 50000, self.b: 30000, self.c: 10000})
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["split_method"], "custom")
        self.assertEqual([(p["name"], p["share_krw"], p["amount"]) for p in created.data["participants"]],
                         [("에이", 50000, "50000.00"), ("비", 30000, "30000.00"), ("씨", 10000, "10000.00")])

    def test_participant_amounts_alone_means_custom(self):
        created = self.add(participant_amounts=[{"id": self.a.id, "amount": 40000}, {"id": self.b.id, "amount": 50000}])
        self.assertEqual((created.status_code, created.data["split_method"]), (status.HTTP_201_CREATED, "custom"))

    def test_sum_must_equal_the_expense_amount(self):
        for amounts in ({self.a: 50000, self.b: 30000},  # 합이 모자람
                        {self.a: 50000, self.b: 50000},  # 넘침
                        {self.a: 90000.5, self.b: 0}):
            self.assertEqual(self.custom(amounts).status_code, status.HTTP_400_BAD_REQUEST, amounts)
        self.assertEqual(Expense.objects.count(), 0)

    def test_other_invalid_custom_input(self):
        base = {"split_method": "custom"}
        self.assertEqual(self.add(**base).status_code, status.HTTP_400_BAD_REQUEST)  # 금액 없음
        self.assertEqual(self.add(participant_amounts=[], **base).status_code, status.HTTP_400_BAD_REQUEST)
        dup = [{"id": self.a.id, "amount": 45000}, {"id": self.a.id, "amount": 45000}]
        self.assertEqual(self.add(participant_amounts=dup).status_code, status.HTTP_400_BAD_REQUEST)
        outsider = [{"id": self.a.id, "amount": 45000}, {"id": self.stranger.id, "amount": 45000}]
        self.assertEqual(self.add(participant_amounts=outsider).status_code, status.HTTP_400_BAD_REQUEST)
        negative = [{"id": self.a.id, "amount": 100000}, {"id": self.b.id, "amount": -10000}]
        self.assertEqual(self.add(participant_amounts=negative).status_code, status.HTTP_400_BAD_REQUEST)
        mixed = {"participant_ids": [self.a.id], "participant_amounts": [{"id": self.a.id, "amount": 90000}]}
        self.assertEqual(self.add(**mixed).status_code, status.HTTP_400_BAD_REQUEST)  # 둘을 함께 보내면 모호
        self.assertEqual(self.add(split_method="equal", participant_amounts=[{"id": self.a.id, "amount": 90000}]).status_code, 400)
        self.assertEqual(Expense.objects.count(), 0)

    def test_custom_split_settles_by_the_entered_amounts(self):
        self.custom({self.a: 20000, self.b: 60000, self.c: 10000}, payer_id=self.a.id)
        self.assertEqual(self.transfers(), [("비", "에이", 60000), ("씨", "에이", 10000)])
        data = self.settlement()
        self.assertEqual({b["name"]: b["share_krw"] for b in data["balances"]}, {"에이": 20000, "비": 60000, "씨": 10000})
        self.assertEqual(sum(b["net_krw"] for b in data["balances"]), 0)

    def test_equal_and_custom_expenses_are_settled_together(self):
        self.add(amount=30000, payer_id=self.a.id, participant_ids=[self.a.id, self.b.id, self.c.id])  # 각 10,000
        self.custom({self.b: 70000, self.c: 20000}, payer_id=self.b.id)
        by_name = {b["name"]: b["net_krw"] for b in self.settlement()["balances"]}
        self.assertEqual(by_name, {"에이": 20000, "비": 90000 - 10000 - 70000, "씨": -10000 - 20000})

    def test_foreign_currency_custom_split_uses_the_ratio_of_won_amount(self):
        self.get_json.side_effect = None
        self.get_json.return_value = {"result": "success", "time_last_update_utc": "x", "rates": {"JPY": 0.11, "KRW": 1}}
        created = self.add(amount=1000, currency="JPY", split_method="custom", payer_id=self.a.id,
                           participant_amounts=[{"id": self.a.id, "amount": 600}, {"id": self.b.id, "amount": 400}])
        self.assertEqual(created.data["amount_krw"], 9091)  # 1000 / 0.11
        self.assertEqual([(p["share_krw"], p["amount"]) for p in created.data["participants"]], [(5455, "600.00"), (3636, "400.00")])
        self.assertEqual(self.transfers(), [("비", "에이", 3636)])
        bad = self.add(amount=1000, currency="JPY", participant_amounts=[{"id": self.a.id, "amount": "600.5"}, {"id": self.b.id, "amount": "399.5"}])
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)  # 엔은 정수

    def test_editing_amount_requires_new_custom_amounts(self):
        expense_id = self.custom({self.a: 50000, self.b: 40000}).data["id"]
        url = f"/api/v1/expenses/{expense_id}/"
        self.assertEqual(self.client.patch(url, {"amount": 60000}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Expense.objects.get().amount, 90000)  # 바뀌지 않았다.
        ok = self.client.patch(url, {"amount": 60000, "participant_amounts": [{"id": self.a.id, "amount": 20000}, {"id": self.b.id, "amount": 40000}]}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual([p["share_krw"] for p in ok.data["participants"]], [20000, 40000])
        # 이름만 고치면 분담은 그대로
        again = self.client.patch(url, {"title": "수정"}, format="json")
        self.assertEqual((again.data["split_method"], [p["share_krw"] for p in again.data["participants"]]), ("custom", [20000, 40000]))

    def test_switch_between_custom_and_equal(self):
        expense_id = self.custom({self.a: 80000, self.b: 10000}).data["id"]
        url = f"/api/v1/expenses/{expense_id}/"
        equal = self.client.patch(url, {"split_method": "equal"}, format="json")  # 인원은 그대로 균등으로
        self.assertEqual((equal.data["split_method"], [(p["share_krw"], p["amount"]) for p in equal.data["participants"]]),
                         ("equal", [(45000, None), (45000, None)]))
        self.assertFalse(ExpenseShare.objects.filter(expense_id=expense_id).exclude(custom_amount=None).exists())
        back = self.client.patch(url, {"participant_amounts": [{"id": self.a.id, "amount": 1000}, {"id": self.c.id, "amount": 89000}]}, format="json")
        self.assertEqual([(p["name"], p["share_krw"]) for p in back.data["participants"]], [("에이", 1000), ("씨", 89000)])
        equal_ids = self.client.patch(url, {"participant_ids": [self.a.id, self.b.id, self.c.id]}, format="json")  # 인원만 보내면 균등
        self.assertEqual((equal_ids.data["split_method"], sorted(p["share_krw"] for p in equal_ids.data["participants"])), ("equal", [30000] * 3))

    def test_changing_currency_of_a_custom_expense_requires_new_amounts(self):
        self.get_json.side_effect = None
        self.get_json.return_value = {"result": "success", "time_last_update_utc": "x", "rates": {"JPY": 0.11, "KRW": 1}}
        expense_id = self.custom({self.a: 50000, self.b: 40000}).data["id"]
        self.assertEqual(self.client.patch(f"/api/v1/expenses/{expense_id}/", {"currency": "JPY"}, format="json").status_code, 400)

    def test_left_member_amount_stays_and_totals_match(self):
        expense_id = self.custom({self.a: 30000, self.b: 30000, self.c: 30000}, payer_id=self.a.id).data["id"]
        TripMember.objects.filter(trip=self.trip, user=self.c).delete()  # 씨가 나감
        edited = self.client.patch(
            f"/api/v1/expenses/{expense_id}/",
            {"participant_amounts": [{"id": self.a.id, "amount": 20000}, {"id": self.b.id, "amount": 30000}, {"id": self.c.id, "amount": 40000}]},
            format="json",
        )
        self.assertEqual(edited.status_code, status.HTTP_200_OK)  # 나간 일행도 이 지출에 있던 사람이면 금액을 바꿀 수 있다.
        by_name = {b["name"]: (b["share_krw"], b["active"]) for b in self.settlement()["balances"]}
        self.assertEqual(by_name, {"에이": (20000, True), "비": (30000, True), "씨": (40000, False)})
        self.assertEqual(self.transfers(), [("씨", "에이", 40000), ("비", "에이", 30000)])

    def test_custom_expense_recalculates_on_delete(self):
        first = self.custom({self.a: 50000, self.b: 40000}, payer_id=self.a.id).data["id"]
        self.add(amount=20000, payer_id=self.b.id, participant_ids=[self.a.id, self.b.id])
        self.assertEqual(self.transfers(), [("비", "에이", 30000)])  # 에이 +40000 - 10000, 비 -40000 + 10000
        self.client.delete(f"/api/v1/expenses/{first}/")
        self.assertEqual(self.transfers(), [("에이", "비", 10000)])
