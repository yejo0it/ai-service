from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AirlineViewSet,
    HotelDetailView,
    HotelSearchView,
    HotelViewSet,
    TripViewSet,
)

router = DefaultRouter()
router.register("trips", TripViewSet, basename="trip")
router.register("hotels", HotelViewSet, basename="hotel")
router.register("airlines", AirlineViewSet, basename="airline")

urlpatterns = [
    path("places/hotels/", HotelSearchView.as_view(), name="hotel-search"),
    path("places/hotels/<str:place_id>/", HotelDetailView.as_view(), name="hotel-detail"),
    path("", include(router.urls)),
]
