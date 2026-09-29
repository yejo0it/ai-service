from django.urls import path

from .views import (
    CheckEmailView,
    KakaoLoginView,
    LoginView,
    NaverLoginView,
    PhoneRequestView,
    PhoneVerifyView,
    SignupView,
)

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("check-email/", CheckEmailView.as_view(), name="check-email"),
    path("phone/request/", PhoneRequestView.as_view(), name="phone-request"),
    path("phone/verify/", PhoneVerifyView.as_view(), name="phone-verify"),
    path("login/", LoginView.as_view(), name="login"),
    path("kakao/", KakaoLoginView.as_view(), name="kakao-login"),
    path("naver/", NaverLoginView.as_view(), name="naver-login"),
]
