from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import expense_views as expense
from . import invitation_views as invitation
from . import place_photo_views as place_photo
from . import summary_views as summary
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
    path("places/photo/", place_photo.PlacePhotoView.as_view(), name="place-photo"),
    path("places/hotels/<str:place_id>/", HotelDetailView.as_view(), name="hotel-detail"),
    path("travel-info/weather/", WeatherView.as_view(), name="travel-weather"),
    path("travel-info/exchange-rates/", ExchangeRateView.as_view(), name="travel-exchange-rates"),
    # 여행 상세 일정 (router의 trips/{pk}/ 보다 먼저 둔다)
    path("trips/<int:pk>/itinerary/", itinerary.ItineraryView.as_view(), name="trip-itinerary"),
    path("trips/<int:pk>/itinerary/init/", itinerary.ItineraryInitView.as_view(), name="trip-itinerary-init"),
    path("trips/<int:pk>/itinerary/reorder/", itinerary.ItineraryReorderView.as_view(), name="trip-itinerary-reorder"),
    path("trips/<int:pk>/packing-note/", itinerary.PackingNoteView.as_view(), name="trip-packing-note"),
    # 여행 경비 (router의 trips/{pk}/ 보다 먼저 둔다)
    path("trips/<int:pk>/expenses/", expense.ExpenseListView.as_view(), name="trip-expenses"),
    path("trips/<int:pk>/budget/", expense.BudgetView.as_view(), name="trip-budget"),
    path("trips/<int:pk>/expense-currencies/", expense.ExpenseCurrenciesView.as_view(), name="trip-expense-currencies"),
    path("trips/<int:pk>/settlement/", expense.SettlementView.as_view(), name="trip-settlement"),
    # 여행 요약(메모·사진)
    path("trips/<int:pk>/summary/", summary.SummaryView.as_view(), name="trip-summary"),
    path("trips/<int:pk>/photos/", summary.PhotoListView.as_view(), name="trip-photos"),
    path("trips/<int:pk>/photos/<int:photo_id>/", summary.PhotoView.as_view(), name="trip-photo"),
    path("trip-photos/<int:photo_id>/file/", summary.PhotoFileView.as_view(), name="trip-photo-file"),
    path("expenses/<int:expense_id>/", expense.ExpenseView.as_view(), name="expense"),
    path("trips/<int:pk>/ai/propose/", itinerary.AiProposeView.as_view(), name="trip-ai-propose"),
    path("trips/<int:pk>/ai/apply/", itinerary.AiApplyView.as_view(), name="trip-ai-apply"),
    # 일행 초대 (router의 trips/{pk}/ 보다 먼저 둔다)
    path("trips/<int:pk>/members/", invitation.TripMembersView.as_view(), name="trip-members"),
    path("trips/<int:pk>/members/<int:user_id>/", invitation.TripMemberView.as_view(), name="trip-member"),
    path("trips/<int:pk>/invitations/", invitation.TripInvitationCreateView.as_view(), name="trip-invitations"),
    path("trips/invitations/<str:token>/accept/", invitation.InvitationAcceptView.as_view(), name="trip-invitation-accept"),
    path("trips/<int:pk>/days/<str:day>/legs/", itinerary.DayLegsView.as_view(), name="trip-day-legs"),
    path("itinerary-items/<int:item_id>/", itinerary.ItineraryItemView.as_view(), name="itinerary-item"),
    path("packing-items/<int:packing_id>/", itinerary.PackingItemView.as_view(), name="packing-item"),
    path("places/search/", itinerary.PlaceSearchView.as_view(), name="place-search"),
    path("", include(router.urls)),
]
