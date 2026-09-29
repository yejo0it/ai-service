from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AirlineViewSet,
    ExchangeRateView,
    HotelDetailView,
    HotelSearchView,
    HotelViewSet,
    TripViewSet,
    WeatherView,
)

router = DefaultRouter()
router.register("trips", TripViewSet, basename="trip")
router.register("hotels", HotelViewSet, basename="hotel")
router.register("airlines", AirlineViewSet, basename="airline")

urlpatterns = [
    path("places/hotels/", HotelSearchView.as_view(), name="hotel-search"),
    path("places/hotels/<str:place_id>/", HotelDetailView.as_view(), name="hotel-detail"),
    path("travel-info/weather/", WeatherView.as_view(), name="travel-weather"),
    path("travel-info/exchange-rates/", ExchangeRateView.as_view(), name="travel-exchange-rates"),
    path("", include(router.urls)),
]
