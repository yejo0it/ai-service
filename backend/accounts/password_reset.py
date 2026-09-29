"""
휴대폰 인증을 마친 회원에게 발급하는 비밀번호 재설정 토큰.

Django의 PasswordResetTokenGenerator 토큰을 회원 ID와 함께 서명해 15분만 유효하게 한다.
생성기 토큰은 비밀번호 해시에 묶여 있어, 비밀번호를 바꾸면 같은 토큰을 다시 쓸 수 없다.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing

User = get_user_model()

TOKEN_SALT = "accounts.password-reset"
TOKEN_MAX_AGE_SECONDS = 15 * 60


def make_reset_token(user):
    return signing.dumps(
        {"uid": user.pk, "token": default_token_generator.make_token(user)}, salt=TOKEN_SALT
    )


def user_from_reset_token(reset_token):
    """유효한 토큰이면 회원을, 만료·위조·이미 사용한 토큰이면 None을 돌려준다."""
    try:
        data = signing.loads(reset_token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    user = User.objects.filter(pk=data.get("uid"), is_active=True).first()
    if user and default_token_generator.check_token(user, data.get("token", "")):
        return user
    return None
