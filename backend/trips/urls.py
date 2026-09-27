from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AirlineViewSet, HotelViewSet, TripViewSet

router = DefaultRouter()
router.register("trips", TripViewSet, basename="trip")
router.register("hotels", HotelViewSet, basename="hotel")
router.register("airlines", AirlineViewSet, basename="airline")

urlpatterns = [path("", include(router.urls))]
