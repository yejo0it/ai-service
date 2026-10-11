"""
전화번호 없이 저장된 숙소(Google Places에서 고른 숙소)의 전화번호를 채운다.
여행 상세 일정에 이미 저장된 숙소 카드(자동 생성)에도 같은 번호를 넣는다.

    python manage.py fill_hotel_phones
"""

from django.core.management.base import BaseCommand

from trips import places
from trips.models import Hotel, ItineraryItem


class Command(BaseCommand):
    help = "Google Places 숙소의 전화번호를 채우고 여행 상세 숙소 카드에 반영한다."

    def handle(self, *args, **options):
        hotels = Hotel.objects.filter(phone="").exclude(place_id="")
        filled = 0
        for hotel in hotels:
            try:
                phone = places.place_details(hotel.place_id).get("phone", "")
            except places.PlacesError as exc:
                self.stderr.write(f"{hotel.name}: {exc}")
                continue
            if not phone:
                continue
            hotel.phone = phone
            hotel.save(update_fields=["phone"])
            ItineraryItem.objects.filter(
                trip=hotel.trip, kind=ItineraryItem.Kind.HOTEL, title=hotel.name, phone=""
            ).update(phone=phone)
            filled += 1
        self.stdout.write(f"전화번호를 채운 숙소: {filled} / {hotels.count()}")
