from django.db import models
from django.db.models import F, Q


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Trip(TimeStampedModel):
    """온보딩 Step 1(목적지) + Step 2(항공권/날짜)의 결과물."""

    class DateSource(models.TextChoices):
        FLIGHT = "flight", "항공권 기반"
        MANUAL = "manual", "날짜만 등록"

    destination = models.CharField("목적지 도시", max_length=120)
    destination_code = models.CharField(
        "도시/공항 코드", max_length=8, blank=True, default=""
    )
    start_date = models.DateField("여행 시작일")
    end_date = models.DateField("여행 종료일")
    date_source = models.CharField(
        "날짜 출처", max_length=10, choices=DateSource.choices, default=DateSource.MANUAL
    )
    # Step 2에서 항공권을 입력하지 않으면 null.
    # {"airline": "KE", "flight_number": "KE001", "departure_at": "...", "arrival_at": "...",
    #  "return_flight_number": "KE002", "return_departure_at": "...", "return_arrival_at": "..."}
    flight_info = models.JSONField("항공권 정보", null=True, blank=True)

    class Meta:
        verbose_name = "여행"
        verbose_name_plural = "여행"
        ordering = ("-start_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="trip_end_date_gte_start_date",
            )
        ]

    def __str__(self) -> str:
        return f"{self.destination} ({self.start_date} ~ {self.end_date})"

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def has_flight(self) -> bool:
        return bool(self.flight_info)


class Hotel(TimeStampedModel):
    """온보딩 Step 3. Skip 가능하므로 Trip 당 0개 이상."""

    trip = models.ForeignKey(Trip, related_name="hotels", on_delete=models.CASCADE)
    name = models.CharField("숙소명", max_length=150)
    address = models.CharField("주소", max_length=255)
    check_in = models.DateField("체크인")
    # 체크아웃 미정(막날 공항 이동 등)인 경우를 위해 Nullable.
    check_out = models.DateField("체크아웃", null=True, blank=True)

    class Meta:
        verbose_name = "숙소"
        verbose_name_plural = "숙소"
        ordering = ("check_in", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(check_out__isnull=True) | Q(check_out__gte=F("check_in")),
                name="hotel_check_out_gte_check_in",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} @ {self.trip.destination}"

    @property
    def nights(self):
        if self.check_out is None:
            return None
        return (self.check_out - self.check_in).days
