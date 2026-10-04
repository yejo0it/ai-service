from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import itinerary_views as itinerary
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
    # 여행 상세 일정 (router의 trips/{pk}/ 보다 먼저 둔다)
    path("trips/<int:pk>/itinerary/", itinerary.ItineraryView.as_view(), name="trip-itinerary"),
    path("trips/<int:pk>/itinerary/init/", itinerary.ItineraryInitView.as_view(), name="trip-itinerary-init"),
    path("trips/<int:pk>/itinerary/reorder/", itinerary.ItineraryReorderView.as_view(), name="trip-itinerary-reorder"),
    path("trips/<int:pk>/packing-note/", itinerary.PackingNoteView.as_view(), name="trip-packing-note"),
    path("trips/<int:pk>/ai/propose/", itinerary.AiProposeView.as_view(), name="trip-ai-propose"),
    path("trips/<int:pk>/ai/apply/", itinerary.AiApplyView.as_view(), name="trip-ai-apply"),
    path("itinerary-items/<int:item_id>/", itinerary.ItineraryItemView.as_view(), name="itinerary-item"),
    path("itinerary-items/<int:item_id>/checklist/", itinerary.ChecklistCreateView.as_view(), name="itinerary-checklist"),
    path("checklist-items/<int:check_id>/", itinerary.ChecklistItemView.as_view(), name="checklist-item"),
    path("places/search/", itinerary.PlaceSearchView.as_view(), name="place-search"),
    path("", include(router.urls)),
]
