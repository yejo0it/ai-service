"""
여행 일행 초대.

- 만든 회원이 초대 링크(/trips/invite/{token})를 만들고 카카오톡·링크 복사로 나눈다.
- 링크를 연 회원은 로그인(또는 가입) 뒤 일행으로 들어와 만든 회원과 똑같이 여행을 편집한다.
- 링크는 여행마다 하나, 7일 동안 쓸 수 있고, 새로 만들면 이전 링크는 바로 쓸 수 없다.
- 여행 삭제·초대 링크 발급·일행 내보내기는 만든 회원만, 나가기는 일행 본인이 한다.
"""

import secrets
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Trip, TripInvitation, TripMember


def display_name(user) -> str:
    """
    일행 목록에 보여줄 이름. 상단 메뉴(AppHeader)와 같이 닉네임, 없으면 이메일 아이디(@ 앞)를 쓴다.
    이메일 전체는 다른 회원에게 보여주지 않는다.
    """
    return user.first_name.strip() or user.email.split("@")[0] or "PinRoute 회원"


def invitation_data(invitation):
    if invitation is None or not invitation.is_valid:
        return None
    return {"token": invitation.token, "expires_at": invitation.expires_at}


class TripMembersView(APIView):
    """`GET /api/v1/trips/{id}/members/` — 만든 회원·일행 목록, 최대 인원, 지금 쓸 수 있는 초대 링크."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trip = get_object_or_404(
            Trip.objects.accessible_to(request.user).select_related("owner"), pk=pk
        )
        members = trip.members.select_related("user")
        return Response(
            {
                "is_owner": trip.owner_id == request.user.id,
                "owner": {"id": trip.owner_id, "name": display_name(trip.owner)} if trip.owner else None,
                "members": [
                    {"id": member.user_id, "name": display_name(member.user), "joined_at": member.joined_at}
                    for member in members
                ],
                "max_members": TripMember.MAX_PER_TRIP,
                "invitation": invitation_data(TripInvitation.objects.filter(trip=trip).first()),
            }
        )


class TripMemberView(APIView):
    """
    `DELETE /api/v1/trips/{id}/members/{user_id}/`
    만든 회원은 일행을 내보내고, 일행은 자기 자신을 지워 여행에서 나간다.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, user_id):
        trip = get_object_or_404(Trip.objects.accessible_to(request.user), pk=pk)
        is_owner = trip.owner_id == request.user.id
        if not is_owner and user_id != request.user.id:
            return Response(
                {"detail": "일행 내보내기는 여행을 만든 회원만 할 수 있어요."},
                status=status.HTTP_403_FORBIDDEN,
            )
        member = get_object_or_404(TripMember, trip=trip, user_id=user_id)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TripInvitationCreateView(APIView):
    """
    `POST /api/v1/trips/{id}/invitations/` — 초대 링크 토큰 만들기 (만든 회원만).
    쓸 수 있는 링크가 있으면 그대로 돌려주고(200), 없거나 `regenerate: true`면 새로 만든다(201).
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        trip = get_object_or_404(Trip.objects.accessible_to(request.user), pk=pk)
        if trip.owner_id != request.user.id:
            return Response(
                {"detail": "초대 링크는 여행을 만든 회원만 만들 수 있어요."},
                status=status.HTTP_403_FORBIDDEN,
            )
        invitation = TripInvitation.objects.select_for_update().filter(trip=trip).first()
        if invitation and invitation.is_valid and request.data.get("regenerate") is not True:
            return Response(invitation_data(invitation))

        now = timezone.now()
        invitation, _ = TripInvitation.objects.update_or_create(
            trip=trip,
            defaults={
                "token": secrets.token_urlsafe(24),
                "created_at": now,
                "expires_at": now + timedelta(days=TripInvitation.VALID_DAYS),
            },
        )
        return Response(invitation_data(invitation), status=status.HTTP_201_CREATED)


class InvitationAcceptView(APIView):
    """
    `POST /api/v1/trips/invitations/{token}/accept/` — 초대 링크로 일행이 되기.
    이미 만든 회원이거나 일행이면 그대로 여행 id를 돌려준다(joined=false).
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, token):
        invitation = (
            TripInvitation.objects.select_related("trip").filter(token=token[:64]).first()
        )
        if invitation is None:
            return Response(
                {"detail": "초대 링크를 찾을 수 없어요. 새 링크를 받아 주세요."},
                status=status.HTTP_404_NOT_FOUND,
            )
        # 같은 여행에 동시에 들어와도 최대 인원을 넘지 않도록 여행 행을 잠근다.
        trip = Trip.objects.select_for_update().get(pk=invitation.trip_id)
        user = request.user
        if trip.owner_id == user.id or trip.members.filter(user=user).exists():
            return Response({"trip_id": trip.id, "joined": False})
        if not invitation.is_valid:
            return Response(
                {"detail": "초대 링크의 유효 기간(7일)이 지났어요. 새 링크를 받아 주세요."},
                status=status.HTTP_410_GONE,
            )
        if trip.members.count() >= TripMember.MAX_PER_TRIP:
            return Response(
                {"detail": f"이 여행은 일행이 가득 찼어요. (최대 {TripMember.MAX_PER_TRIP}명)"},
                status=status.HTTP_409_CONFLICT,
            )
        TripMember.objects.create(trip=trip, user=user)
        return Response({"trip_id": trip.id, "joined": True}, status=status.HTTP_201_CREATED)
