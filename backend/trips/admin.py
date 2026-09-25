from django.contrib import admin

from .models import Hotel, Trip


class HotelInline(admin.TabularInline):
    model = Hotel
    extra = 0


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
    inlines = [HotelInline]

    @admin.display(description="여행지")
    def destination_label(self, obj):
        return obj.destination_label


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("name", "trip", "check_in", "check_out")
    search_fields = ("name", "address")
