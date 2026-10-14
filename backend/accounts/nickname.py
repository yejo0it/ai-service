"""
닉네임 규칙과 랜덤 닉네임. 가입·소셜 가입·마이페이지·일행 목록이 함께 쓴다.

닉네임은 Profile.nickname에 저장하며 중복을 허용한다. 형식은 한글·영문·숫자·밑줄 2~12자이고
단어 사이의 공백(한 칸)은 허용하지만 앞뒤 공백이나 공백뿐인 값은 허용하지 않는다(입력 단계에서 앞뒤 공백을 지운다).
랜덤 닉네임은 '형용사 동물'(예: 용감한 펭귄)로 만들어 같은 규칙을 지키게 한다.
"""

import re
import secrets

# 형용사·동물은 각각 따로 늘릴 수 있다. 공백 포함 12자를 넘지 않도록 형용사 5자·동물 6자 이하로 둔다.
ADJECTIVES = (
    "여행하는", "대견한", "용감한", "느긋한", "씩씩한", "다정한", "활기찬", "상냥한", "든든한", "호기심많은",
    "행복한", "반짝이는", "포근한", "당당한", "유쾌한", "부지런한", "명랑한", "차분한", "엉뚱한", "느릿한",
)
ANIMALS = (
    "고래", "열대어", "펭귄", "수달", "돌고래", "코알라", "고양이", "강아지", "토끼", "다람쥐",
    "판다", "알파카", "해달", "오리", "거북이", "여우", "앵무새", "사슴", "부엉이", "카피바라",
)

NICKNAME_PATTERN = re.compile(r"^(?=.{2,12}$)[가-힣A-Za-z0-9_]+(?: [가-힣A-Za-z0-9_]+)*$")
NICKNAME_RULE_MESSAGE = "닉네임은 한글, 영문, 숫자, 밑줄(_)로 2~12자 입력해 주세요."
NICKNAME_SPACING_MESSAGE = "단어 사이 공백은 한 칸만 허용합니다."


def nickname_error(value: str) -> str:
    """앞뒤 공백을 지운 닉네임의 형식 오류 메시지. 문제가 없으면 빈 문자열. 공백이 두 칸 이상이면 그 안내만 한다."""
    if "  " in value:
        return NICKNAME_SPACING_MESSAGE
    return "" if NICKNAME_PATTERN.match(value) else NICKNAME_RULE_MESSAGE


def random_nickname() -> str:
    return f"{secrets.choice(ADJECTIVES)} {secrets.choice(ANIMALS)}"


def usable_nickname(value: str) -> str:
    """형식에 맞는 값이면 그대로, 아니면 랜덤 닉네임 (소셜 계정 이름처럼 규칙을 모르는 값에 쓴다)."""
    value = (value or "").strip()
    return value if NICKNAME_PATTERN.match(value) else random_nickname()


def nickname_of(user) -> str:
    """
    화면·일행 목록·메일에 쓸 닉네임. 닉네임이 아직 없는 회원(예전 가입자 등)은 한 번 만들어 저장한다.
    이메일은 어디에도 쓰지 않는다.
    """
    from .models import Profile

    profile, _ = Profile.objects.get_or_create(user=user)
    if not profile.nickname:
        profile.nickname = random_nickname()
        profile.save(update_fields=["nickname"])
    return profile.nickname
