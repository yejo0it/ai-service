from django.urls import path

from .views import (
    CheckEmailView,
    FindIdView,
    KakaoLoginView,
    LoginView,
    LogoutView,
    NaverLoginView,
    PasswordResetConfirmView,
    PasswordResetVerifyView,
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
    path("logout/", LogoutView.as_view(), name="logout"),
    path("find-id/", FindIdView.as_view(), name="find-id"),
    path("password-reset/verify/", PasswordResetVerifyView.as_view(), name="password-reset-verify"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("kakao/", KakaoLoginView.as_view(), name="kakao-login"),
    path("naver/", NaverLoginView.as_view(), name="naver-login"),
]
