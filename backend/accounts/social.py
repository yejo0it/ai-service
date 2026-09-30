"""
카카오·네이버 OAuth 2.0 인가 코드 교환과 회원 프로필 조회.

프론트가 인가 URL로 보냈다가 받은 code를 넘기면, 서버에서 client secret으로 토큰을 받아
프로필을 조회한다(토큰은 저장하지 않는다).
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT_SECONDS = 5


class SocialAuthError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SocialProfile:
    uid: str
    email: str
    # 제공자가 소유를 확인한 이메일인지. 확인되지 않은 이메일은 계정에 저장하지 않는다.
    email_verified: bool
    name: str


def _request(url, data=None, token=None):
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 잘못된·만료된 인가 코드는 400대로 돌아온다.
        raise SocialAuthError("소셜 로그인에 실패했어요. 다시 시도해 주세요.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SocialAuthError("소셜 로그인 서버에 연결하지 못했어요.", 502) from exc


def _require(name):
    value = os.environ.get(name, "")
    if not value:
        raise SocialAuthError("소셜 로그인이 설정되지 않았어요.", 503)
    return value


def kakao_profile(code, redirect_uri):
    data = {
        "grant_type": "authorization_code",
        "client_id": _require("KAKAO_REST_API_KEY"),
        "redirect_uri": redirect_uri,
        "code": code,
    }
    # 카카오 콘솔에서 Client Secret을 켠 경우에만 필요하다.
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "")
    if client_secret:
        data["client_secret"] = client_secret
    token = _request("https://kauth.kakao.com/oauth/token", data)["access_token"]

    me = _request("https://kapi.kakao.com/v2/user/me", token=token)
    account = me.get("kakao_account", {})
    return SocialProfile(
        uid=str(me["id"]),
        email=account.get("email", ""),
        email_verified=bool(account.get("is_email_valid") and account.get("is_email_verified")),
        name=account.get("profile", {}).get("nickname", ""),
    )


def naver_profile(code, state):
    data = {
        "grant_type": "authorization_code",
        "client_id": _require("NAVER_CLIENT_ID"),
        "client_secret": _require("NAVER_CLIENT_SECRET"),
        "code": code,
        "state": state,
    }
    result = _request("https://nid.naver.com/oauth2.0/token", data)
    if "access_token" not in result:
        raise SocialAuthError("소셜 로그인에 실패했어요. 다시 시도해 주세요.")

    me = _request("https://openapi.naver.com/v1/nid/me", token=result["access_token"])
    profile = me.get("response", {})
    email = profile.get("email", "")
    return SocialProfile(
        uid=str(profile["id"]),
        email=email,
        # 네이버 회원정보에 등록된 연락 이메일이다(별도 인증 여부 필드는 없다).
        email_verified=bool(email),
        name=profile.get("name") or profile.get("nickname", ""),
    )
