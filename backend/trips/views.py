from django.db.models import TextField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Hotel, Trip, Airline
from .serializers import HotelSerializer, TripSerializer, AirlineSerializer

class AirlineViewSet(viewsets.ReadOnlyModelViewSet):
    """
    `/api/v1/airlines/` — 항공사 목록 조회. CSV import 후 DB에 저장된 항공사 정보 제공.
    """

    queryset = Airline.objects.all()
    serializer_class = AirlineSerializer


class TripViewSet(viewsets.ModelViewSet):
    """
    `/api/v1/trips/`

    - POST: 온보딩 Step 1~2만 저장하거나, `hotels: [...]`를 함께 보내 Step 1~3을 한 번에 저장.
    - PATCH: 단계별 저장 시 Step 2 결과를 이어서 갱신.
    - GET `/api/v1/trips/{id}/hotels/` · POST 로 Step 3만 따로 저장.
    """

    queryset = Trip.objects.prefetch_related("hotels")
    serializer_class = TripSerializer
    permission_classes = [AllowAny]  # MVP: 인증 도입 시 IsAuthenticated로 교체

    def get_queryset(self):
        queryset = super().get_queryset()
        destination = self.request.query_params.get("destination")
        if destination:
            # destinations는 JSONField(list)이므로 text로 캐스팅해 부분 검색한다.
            # 도시명("도쿄")과 도시코드("TYO") 모두로 찾을 수 있다.
            queryset = queryset.annotate(
                destinations_text=Cast("destinations", TextField())
            ).filter(destinations_text__icontains=destination)
        return queryset

    @action(detail=True, methods=["get", "post"], url_path="hotels")
    def hotels(self, request, pk=None):
        trip = self.get_object()
        if request.method == "GET":
            serializer = HotelSerializer(trip.hotels.all(), many=True)
            return Response(serializer.data)

        many = isinstance(request.data, list)
        serializer = HotelSerializer(
            data=request.data, many=many, context={**self.get_serializer_context(), "trip": trip}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(trip=trip)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HotelViewSet(viewsets.ModelViewSet):
    """`/api/v1/hotels/` — Step 3 단독 저장/수정/삭제. `?trip={id}`로 필터링."""

    queryset = Hotel.objects.select_related("trip")
    serializer_class = HotelSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        trip_id = self.request.query_params.get("trip")
        if trip_id:
            queryset = queryset.filter(trip_id=trip_id)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        trip_id = self.request.data.get("trip") if hasattr(self.request, "data") else None
        if trip_id:
            context["trip"] = get_object_or_404(Trip, pk=trip_id)
        return context
