"""
짐싸기 노트

- DEFAULT_PACKING_ITEMS: 짐싸기 노트를 처음 열 때 넣는 기본 준비물 (분류, 이름)
- belongs_to_packing_note: 체크리스트 항목이 짐싸기 노트 '일정 연동 항목'에 들어갈지 자동 분류한다.
예약·예매·티켓 같은 사전 준비, 준비물·지참 같은 짐 성격의 낱말이 있으면 연동한다.
(사용자는 카드에서 직접 켜고 끌 수 있다)
"""

DEFAULT_PACKING_ITEMS = (
    ("essentials", "여권"),
    ("essentials", "신분증"),
    ("essentials", "항공권 E-ticket"),
    ("essentials", "숙소 예약 확인서"),
    ("essentials", "신용카드·체크카드"),
    ("essentials", "현금·환전"),
    ("toiletries", "칫솔·치약"),
    ("toiletries", "샴푸·바디워시"),
    ("toiletries", "스킨케어"),
    ("toiletries", "선크림"),
    ("clothing", "옷"),
    ("clothing", "속옷·양말"),
    ("clothing", "잠옷"),
    ("electronics", "휴대폰 충전기"),
    ("electronics", "보조배터리"),
    ("electronics", "멀티 어댑터"),
    ("medicine", "해열·진통제"),
    ("medicine", "소화제"),
    ("medicine", "밴드"),
    ("etc", "우산"),
)

PACKING_KEYWORDS = (
    # 예약 · 티켓
    "예약", "예매", "티켓", "입장권", "탑승권", "바우처", "패스", "쿠폰", "발권",
    # 준비물 · 짐
    "준비", "챙기", "챙길", "지참", "가져가", "가져갈", "필수", "여권", "신분증",
    "현금", "카드", "충전기", "어댑터", "우산", "선크림", "수영복",
)


def belongs_to_packing_note(text: str) -> bool:
    return any(keyword in text for keyword in PACKING_KEYWORDS)
