import datetime

from django.db import transaction
from rest_framework import serializers

from .models import Hotel, Trip, Airline


def _jsonify(value):
    """검증된 payload(datetime 포함)를 JSONField에 저장 가능한 형태로 변환한다."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    return value


class AirlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Airline
        fields = ["id", "name_ko", "iata_code", "country"]
        read_only_fields = ("id",)


class DestinationSerializer(serializers.Serializer):
    """Trip.destinations(JSONField)의 각 여행지 항목을 검증한다."""

    city = serializers.CharField(max_length=100)
    city_code = serializers.CharField(
        max_length=8, required=False, allow_blank=True, default=""
    )

    def validate_city(self, value):
        return value.strip()

    def validate_city_code(self, value):
        return value.strip().upper()


class FlightInfoSerializer(serializers.Serializer):
    """Trip.flight_info(JSONField)에 저장될 payload의 형태를 검증한다."""

    airline = serializers.CharField(max_length=60, required=False, allow_blank=True)
    flight_number = serializers.CharField(max_length=20)
    departure_at = serializers.DateTimeField()
    arrival_at = serializers.DateTimeField(required=False, allow_null=True)
    return_flight_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    return_departure_at = serializers.DateTimeField(required=False, allow_null=True)
    return_arrival_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        outbound = attrs.get("departure_at")
        inbound = attrs.get("return_departure_at")
        if outbound and inbound and inbound < outbound:
            raise serializers.ValidationError(
                {"return_departure_at": "돌아오는 편은 가는 편보다 늦어야 합니다."}
            )
        return attrs


def _validate_hotel_range(check_in, check_out, trip_start, trip_end):
    """숙소 일정이 여행 기간 안에 들어오는지 확인한다."""
    errors = {}
    if check_in and trip_start and check_in < trip_start:
        errors["check_in"] = "체크인은 여행 시작일 이후여야 합니다."
    last_day = check_out or check_in
    if last_day and trip_end and last_day > trip_end:
        errors["check_out" if check_out else "check_in"] = (
            "숙소 일정이 여행 종료일을 넘을 수 없습니다."
        )
    if errors:
        raise serializers.ValidationError(errors)


class NestedHotelSerializer(serializers.ModelSerializer):
    """Trip 생성 요청(Step 1~3 단일 요청)에 포함되는 숙소."""

    nights = serializers.IntegerField(read_only=True)

    class Meta:
        model = Hotel
        fields = ("id", "name", "address", "check_in", "check_out", "nights")
        read_only_fields = ("id", "nights")

    def validate(self, attrs):
        check_in = attrs.get("check_in") or getattr(self.instance, "check_in", None)
        check_out = attrs.get("check_out", getattr(self.instance, "check_out", None))
        if check_in and check_out and check_out < check_in:
            raise serializers.ValidationError(
                {"check_out": "체크아웃은 체크인 이후여야 합니다."}
            )
        return attrs


class HotelSerializer(NestedHotelSerializer):
    """`/api/v1/hotels/` 용. Step 3만 따로 저장할 때 사용한다."""

    trip = serializers.PrimaryKeyRelatedField(
        queryset=Trip.objects.all(), required=False, allow_null=True
    )

    class Meta(NestedHotelSerializer.Meta):
        fields = NestedHotelSerializer.Meta.fields + ("trip", "created_at")
        read_only_fields = NestedHotelSerializer.Meta.read_only_fields + ("created_at",)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # trip은 body 또는 중첩 라우트(/trips/{id}/hotels/)에서 온다.
        trip = attrs.get("trip") or self.context.get("trip")
        if trip is None and self.instance is not None:
            trip = self.instance.trip
        if trip is None:
            raise serializers.ValidationError({"trip": "여행 ID가 필요합니다."})
        attrs["trip"] = trip

        _validate_hotel_range(
            attrs.get("check_in") or getattr(self.instance, "check_in", None),
            attrs.get("check_out", getattr(self.instance, "check_out", None)),
            trip.start_date,
            trip.end_date,
        )
        return attrs


class TripSerializer(serializers.ModelSerializer):
    """Step 1~3을 한 번에 받거나, Step 1~2만 먼저 저장할 수 있다."""

    hotels = NestedHotelSerializer(many=True, required=False)
    flight_info = FlightInfoSerializer(required=False, allow_null=True)
    # 여행지는 1개 이상. partial update(PATCH)에서는 DRF가 required를 자동 해제한다.
    destinations = DestinationSerializer(many=True, allow_empty=False)
    destination_label = serializers.CharField(read_only=True)
    nights = serializers.IntegerField(read_only=True)
    has_flight = serializers.BooleanField(read_only=True)

    class Meta:
        model = Trip
        fields = (
            "id",
            "destinations",
            "destination_label",
            "start_date",
            "end_date",
            "date_source",
            "flight_info",
            "has_flight",
            "nights",
            "hotels",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "destination_label",
            "has_flight",
            "nights",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            # 항공권에서 날짜를 추론할 수 있으므로 필수 해제 후 validate에서 확인한다.
            "start_date": {"required": False},
            "end_date": {"required": False},
        }

    def validate(self, attrs):
        instance = self.instance
        start = attrs.get("start_date") or getattr(instance, "start_date", None)
        end = attrs.get("end_date") or getattr(instance, "end_date", None)

        if "destinations" in attrs:
            # OrderedDict -> 순수 list[dict]로 변환해 JSONField에 저장한다.
            attrs["destinations"] = [_jsonify(dict(entry)) for entry in attrs["destinations"]]

        if "flight_info" in attrs:
            flight = attrs["flight_info"]  # 검증 통과한 dict(datetime 포함) 또는 None
            if flight:
                attrs.setdefault("date_source", Trip.DateSource.FLIGHT)
                # Step 2에서 항공권을 입력했다면 날짜를 항공권에서 채운다.
                if start is None:
                    start = flight["departure_at"].date()
                    attrs["start_date"] = start
                arrival = flight.get("return_arrival_at") or flight.get("arrival_at")
                if end is None and arrival:
                    end = arrival.date()
                    attrs["end_date"] = end
                attrs["flight_info"] = _jsonify(dict(flight))
            else:
                attrs.setdefault("date_source", Trip.DateSource.MANUAL)

        missing = {
            field: "이 필드는 필수입니다."
            for field, value in (("start_date", start), ("end_date", end))
            if value is None
        }
        if missing:
            raise serializers.ValidationError(missing)
        if end < start:
            raise serializers.ValidationError(
                {"end_date": "종료일은 시작일 이후여야 합니다."}
            )

        for index, hotel in enumerate(attrs.get("hotels", [])):
            try:
                _validate_hotel_range(
                    hotel.get("check_in"), hotel.get("check_out"), start, end
                )
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"hotels": {index: exc.detail}}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        hotels = validated_data.pop("hotels", [])
        trip = Trip.objects.create(**validated_data)
        Hotel.objects.bulk_create([Hotel(trip=trip, **hotel) for hotel in hotels])
        return trip

    @transaction.atomic
    def update(self, instance, validated_data):
        # 중첩 hotels가 전달되면 전체 교체한다(부분 수정은 /hotels/ 엔드포인트 사용).
        hotels = validated_data.pop("hotels", None)
        # destinations/flight_info는 JSONField이지만 중첩 Serializer로 검증하므로
        # ModelSerializer.update()의 nested-write 검사에 걸린다. 직접 대입 후 저장한다.
        for json_field in ("destinations", "flight_info"):
            if json_field in validated_data:
                setattr(instance, json_field, validated_data.pop(json_field))
        trip = super().update(instance, validated_data)
        if hotels is not None:
            trip.hotels.all().delete()
            Hotel.objects.bulk_create([Hotel(trip=trip, **hotel) for hotel in hotels])
        return trip
