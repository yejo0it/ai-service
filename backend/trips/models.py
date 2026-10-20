from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Airline(models.Model):
    """항공사 정보. IATA 코드 기반."""

    name_ko = models.CharField("국문 항공사명", max_length=100)
    iata_code = models.CharField("iata 코드", max_length=2, unique=True)
    country = models.CharField("국가", max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "항공사"
        verbose_name_plural = "항공사"
        ordering = ("name_ko",)

    def __str__(self) -> str:
        return f"[{self.iata_code}] {self.name_ko}"

class TripQuerySet(models.QuerySet):
    def accessible_to(self, user):
        """회원이 보고 편집할 수 있는 여행: 직접 만든 여행 + 초대받아 함께하는 여행."""
        return self.filter(
            Q(owner=user) | Q(pk__in=TripMember.objects.filter(user=user).values("trip_id"))
        )


class Trip(TimeStampedModel):
    """온보딩 Step 1(목적지) + Step 2(항공권/날짜)의 결과물."""

    class DateSource(models.TextChoices):
        FLIGHT = "flight", "항공권 기반"
        MANUAL = "manual", "날짜만 등록"

    class Color(models.TextChoices):
        """캘린더에 표시할 여행 색. 기본 색상 + 서비스 대표색(인디고)."""

        INDIGO = "indigo", "인디고"
        RED = "red", "빨강"
        ORANGE = "orange", "주황"
        YELLOW = "yellow", "노랑"
        GREEN = "green", "초록"
        BLUE = "blue", "파랑"
        PURPLE = "purple", "보라"
        GRAY = "gray", "회색"

    # [{"city": "도쿄", "city_code": "tokyo"}, {"city": "오사카", "city_code": "osaka"}]
    # city_code는 서비스 자체 도시 id(backend/data/cities.json)다. IATA 코드가 없는 소도시도 있다.
    # 도시 이동 순서를 그대로 유지하므로 list 순서가 곧 여행 동선이다.
    destinations = models.JSONField(
        "여행지",
        default=list,
        blank=True,
        help_text='[{"city": "도시명", "city_code": "도시코드"}] 형태의 목록',
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
    # 비어 있으면 프론트가 여행마다 팔레트에서 자동으로 고른다.
    color = models.CharField("색상", max_length=10, choices=Color.choices, blank=True, default="")
    # 여행을 만든 회원. 회원 연결 전에 만든 여행은 비어 있어 누구의 목록에도 나오지 않는다.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="회원",
        related_name="trips",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # 상세 화면을 처음 열 때 항공편·숙소로 일정 카드를 한 번 만들었는지
    itinerary_initialized = models.BooleanField("일정 초기화 여부", default=False)
    # 짐싸기 노트를 처음 열 때 기본 준비물을 한 번 넣었는지 (지운 기본 항목이 다시 생기지 않도록)
    packing_initialized = models.BooleanField("짐싸기 노트 초기화 여부", default=False)

    objects = TripQuerySet.as_manager()

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
        return f"{self.destination_label} ({self.start_date} ~ {self.end_date})"

    @property
    def city_names(self) -> list[str]:
        """destinations에서 도시명만 순서대로 뽑아낸다."""
        return [
            entry["city"]
            for entry in (self.destinations or [])
            if isinstance(entry, dict) and entry.get("city")
        ]

    @property
    def destination_label(self) -> str:
        """`도쿄 → 나고야 → 오사카` 형태의 사람이 읽는 동선 표기."""
        return " → ".join(self.city_names) or "목적지 미정"

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
    # Google Places에서 고른 숙소. 직접 입력한 숙소는 비어 있다.
    place_id = models.CharField("Google Place ID", max_length=255, blank=True, default="")
    latitude = models.FloatField("위도", null=True, blank=True)
    longitude = models.FloatField("경도", null=True, blank=True)
    # Google Places 전화번호 (여행 상세 숙소 카드에 표시)
    phone = models.CharField("전화번호", max_length=40, blank=True, default="")
    # 이 숙소가 속한 여행지(Trip.destinations의 city_code)
    city_code = models.CharField("도시코드", max_length=32, blank=True, default="")
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
        return f"{self.name} @ {self.trip.destination_label}"

    @property
    def nights(self):
        if self.check_out is None:
            return None
        return (self.check_out - self.check_in).days


class ItineraryItem(TimeStampedModel):
    """
    여행 상세의 일정 카드 한 장. 날짜(day)별로 order 순서대로 보여준다.
    항공편·숙소 카드는 상세 화면을 처음 열 때 만들어지고(source=auto), 장소는 직접(manual)·AI(ai)로 추가한다.
    stops는 카드 안의 위치 목록(지도 핀): [{"kind", "caption", "label", "lat", "lng"}]
    """

    class Kind(models.TextChoices):
        FLIGHT = "flight", "항공편"
        HOTEL = "hotel", "숙소"
        AIRPORT = "airport", "공항"
        SIGHT = "sight", "관광지"
        RESTAURANT = "restaurant", "식당"
        CAFE = "cafe", "카페"

    class Source(models.TextChoices):
        AUTO = "auto", "항공편·숙소"
        MANUAL = "manual", "직접 추가"
        AI = "ai", "AI 추천"

    trip = models.ForeignKey(Trip, related_name="itinerary_items", on_delete=models.CASCADE)
    day = models.DateField("날짜")
    order = models.PositiveIntegerField("순서", default=0)
    kind = models.CharField("유형", max_length=12, choices=Kind.choices)
    source = models.CharField("추가 방법", max_length=8, choices=Source.choices, default=Source.MANUAL)
    title = models.CharField("이름", max_length=150)
    # 방문 시각(선택). 숙소 카드처럼 시각 대신 "체크인" 등을 보여줄 때는 time_label을 쓴다.
    time = models.TimeField("시간", null=True, blank=True)
    time_label = models.CharField("시간 표기", max_length=20, blank=True, default="")
    subtitle = models.CharField("부가 설명", max_length=100, blank=True, default="")
    stops = models.JSONField("위치", default=list, blank=True)
    # 예상 체류 시간(분). AI가 정한 값. 비어 있으면 모른다(일정 계산에서는 종류별 기본값을 쓴다).
    stay_minutes = models.PositiveSmallIntegerField("예상 체류 시간(분)", null=True, blank=True)
    # 예상 도착 시각. 'AI와 함께 만들기'가 이동 시간으로 계산한 값이며 추정치다. 순서·시간을 직접 바꾸면 지워진다.
    expected_arrival = models.TimeField("예상 도착 시각", null=True, blank=True)
    # 장소 상세 (Google Places)
    place_id = models.CharField("Google Place ID", max_length=255, blank=True, default="")
    address = models.CharField("주소", max_length=255, blank=True, default="")
    phone = models.CharField("전화번호", max_length=40, blank=True, default="")
    opening_hours = models.JSONField("영업시간", default=list, blank=True)

    class Meta:
        verbose_name = "일정"
        verbose_name_plural = "일정"
        ordering = ("day", "order", "id")

    def __str__(self) -> str:
        return f"{self.day} #{self.order} {self.title}"


class PackingItem(TimeStampedModel):
    """짐싸기 노트의 준비물. 기본 준비물로 시작하고 사용자가 직접 더하거나 지운다."""

    class Category(models.TextChoices):
        """화면에도 이 순서대로 나온다."""

        TODO = "todo", "해야 할 일"
        ESSENTIALS = "essentials", "필수 준비물"
        TOILETRIES = "toiletries", "세면도구/화장품"
        CLOTHING = "clothing", "의류"
        ELECTRONICS = "electronics", "전자제품"
        MEDICINE = "medicine", "상비약"
        ETC = "etc", "기타"

    trip = models.ForeignKey(Trip, related_name="packing_items", on_delete=models.CASCADE)
    category = models.CharField("분류", max_length=12, choices=Category.choices, default=Category.ETC)
    text = models.CharField("준비물", max_length=100)
    done = models.BooleanField("챙김", default=False)
    is_default = models.BooleanField("기본 준비물", default=False)

    class Meta:
        verbose_name = "짐싸기 준비물"
        verbose_name_plural = "짐싸기 준비물"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return self.text


class TripMember(models.Model):
    """
    초대 링크로 여행에 함께하는 일행. 만든 회원(Trip.owner)은 포함하지 않는다.
    일정·장소·항공·숙소·AI·짐싸기 노트는 만든 회원과 똑같이 편집하고,
    여행 삭제·초대 링크 발급·일행 내보내기는 만든 회원만 한다.
    """

    # 만든 회원을 빼고 함께할 수 있는 일행 수
    MAX_PER_TRIP = 10

    trip = models.ForeignKey(Trip, related_name="members", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="trip_memberships", on_delete=models.CASCADE
    )
    joined_at = models.DateTimeField("참여일", auto_now_add=True)

    class Meta:
        verbose_name = "여행 일행"
        verbose_name_plural = "여행 일행"
        ordering = ("joined_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("trip", "user"), name="trip_member_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.trip_id}"


class TripInvitation(models.Model):
    """
    여행 초대 링크(/trips/invite/{token}). 여행마다 하나이고 만든 뒤 7일 동안 쓸 수 있다.
    새 링크를 만들면 토큰을 바꿔 저장하므로 이전 링크는 바로 쓸 수 없게 된다.
    """

    VALID_DAYS = 7

    trip = models.OneToOneField(Trip, related_name="invitation", on_delete=models.CASCADE)
    token = models.CharField("토큰", max_length=64, unique=True)
    created_at = models.DateTimeField("발급일")
    expires_at = models.DateTimeField("만료일")

    class Meta:
        verbose_name = "여행 초대 링크"
        verbose_name_plural = "여행 초대 링크"

    def __str__(self) -> str:
        return f"{self.trip_id} ~{self.expires_at:%Y-%m-%d}"

    @property
    def is_valid(self) -> bool:
        return self.expires_at > timezone.now()
