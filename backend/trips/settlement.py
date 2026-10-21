"""
여행 경비 정산 계산(순수 계산, DB를 쓰지 않는다). 금액은 모두 정수 원이다.

- 분담(균등): 지출을 선택한 인원끼리 균등하게 나눈다. 나누어떨어지지 않는 나머지(원)는 한 사람이 1원씩 더 부담해
  합계가 지출 금액과 정확히 맞는다. 나머지는 결제자(분담 인원이면)부터, 그다음은 회원 번호가 작은 순서로 배분한다.
- 분담(직접 입력): 사람마다 입력한 금액(지출 통화 기준, 합계는 지출 금액과 같다)의 비율대로 원화 금액을 나눈다.
  원 단위로 떨어지지 않는 나머지는 소수 부분이 큰 사람부터 1원씩 배분(최대 잔여법)해 합계가 정확히 맞는다.
- 정산: 사용자별로 결제한 금액에서 부담액을 뺀 값(순액)을 구하고, 받을 사람과 보낼 사람을 큰 금액부터 짝지어
  송금 횟수를 줄인다. 순액의 합은 언제나 0이므로 마지막에 남는 금액이 없다.
- 사용자는 회원 번호(ref)로 구분한다. 탈퇴한 회원도 번호가 남아 내역과 정산이 어긋나지 않는다.
"""

from decimal import Decimal


def split_equally(amount, refs, payer_ref=None):
    """amount원을 refs(회원 번호 목록)에게 균등 분할한 {회원 번호: 부담액}. 합계는 항상 amount다."""
    refs = list(dict.fromkeys(refs))
    quotient, remainder = divmod(amount, len(refs))
    shares = {ref: quotient for ref in refs}
    # 나머지를 1원씩 받을 순서: 결제자 먼저, 그다음 번호순
    for ref in sorted(refs, key=lambda ref: (ref != payer_ref, ref))[:remainder]:
        shares[ref] += 1
    return shares


def split_by_weights(amount, weights, payer_ref=None):
    """
    amount원을 weights({회원 번호: 비중(Decimal)})의 비율대로 나눈 {회원 번호: 부담액}. 합계는 항상 amount다.
    비중이 같은 통화 금액이면 그 비율이 곧 부담 비율이다. 소수 부분이 큰 사람부터 1원씩 더 받고,
    같으면 결제자, 그다음 번호순이다.
    """
    total = sum(weights.values())
    exact = {ref: Decimal(amount) * weight / total for ref, weight in weights.items()}
    shares = {ref: int(value) for ref, value in exact.items()}  # 내림
    remainder = amount - sum(shares.values())
    order = sorted(shares, key=lambda ref: (-(exact[ref] - shares[ref]), ref != payer_ref, ref))
    for ref in order[:remainder]:
        shares[ref] += 1
    return shares


def settle(expenses, people):
    """
    expenses: [(원화 금액, 결제자 번호, {회원 번호: 부담액})] — 분담 인원이 지정된 지출만 넘긴다.
    부담액은 split_equally·split_by_weights로 미리 구한다(합계는 원화 금액과 같다).
    people: 정산표에 꼭 넣을 회원 번호(지금 여행에 함께하는 사람들). 지출에 나온 사람은 자동으로 들어간다.
    반환: (balances, transfers)
      balances  [{"ref", "paid", "share", "net"}] 번호순
      transfers [{"from", "to", "amount"}] 보내는 사람 -> 받는 사람
    """
    paid = {ref: 0 for ref in people}
    share = {ref: 0 for ref in people}
    for amount, payer_ref, shares in expenses:
        paid[payer_ref] = paid.get(payer_ref, 0) + amount
        share.setdefault(payer_ref, 0)
        for ref, value in shares.items():
            share[ref] = share.get(ref, 0) + value
            paid.setdefault(ref, 0)

    balances = [
        {"ref": ref, "paid": paid[ref], "share": share[ref], "net": paid[ref] - share[ref]} for ref in sorted(paid)
    ]
    creditors = sorted(([b["net"], b["ref"]] for b in balances if b["net"] > 0), key=lambda item: (-item[0], item[1]))
    debtors = sorted(([-b["net"], b["ref"]] for b in balances if b["net"] < 0), key=lambda item: (-item[0], item[1]))
    transfers = []
    i = j = 0
    while i < len(creditors) and j < len(debtors):
        amount = min(creditors[i][0], debtors[j][0])
        transfers.append({"from": debtors[j][1], "to": creditors[i][1], "amount": amount})
        creditors[i][0] -= amount
        debtors[j][0] -= amount
        if creditors[i][0] == 0:
            i += 1
        if debtors[j][0] == 0:
            j += 1
    return balances, transfers
