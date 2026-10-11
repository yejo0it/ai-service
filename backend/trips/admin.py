from django.contrib import admin

from .models import Hotel, Trip, TripInvitation, TripMember


class HotelInline(admin.TabularInline):
    model = Hotel
    extra = 0


class TripMemberInline(admin.TabularInline):
    model = TripMember
    extra = 0
    raw_id_fields = ("user",)
    readonly_fields = ("joined_at",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "destination_label",
        "start_date",
        "end_date",
        "date_source",
        "created_at",
    )
    list_filter = ("date_source",)
    inlines = [HotelInline, TripMemberInline]

    @admin.display(description="여행지")
    def destination_label(self, obj):
        return obj.destination_label


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("name", "trip", "check_in", "check_out")
    search_fields = ("name", "address")


@admin.register(TripMember)
class TripMemberAdmin(admin.ModelAdmin):
    """초대 링크로 함께하는 일행 (만든 회원은 Trip.owner)"""

    list_display = ("user", "trip", "joined_at")
    search_fields = ("user__username", "user__first_name")
    raw_id_fields = ("trip", "user")
    readonly_fields = ("joined_at",)


@admin.register(TripInvitation)
class TripInvitationAdmin(admin.ModelAdmin):
    """여행마다 하나인 초대 링크 (7일 유효)"""

    list_display = ("trip", "created_at", "expires_at", "is_valid")
    raw_id_fields = ("trip",)
    readonly_fields = ("token", "created_at")

    def has_add_permission(self, request):
        # 토큰은 서비스(일행 초대하기)에서만 만든다. 관리자 화면에서는 조회·만료일 조정·삭제만 한다.
        return False

    @admin.display(description="사용 가능", boolean=True)
    def is_valid(self, obj):
        return obj.is_valid
