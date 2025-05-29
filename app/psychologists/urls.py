from django.urls import path
from .views import (
    PsychologistRegistrationView,
    PsychologistProfileView,
    PsychologistSearchView,
    AvailabilityCreateView,
    AvailabilityDetailView,
    AvailabilityListView,
    AvailabilityBulkView,
    PsychologistVerificationView,
)

app_name = 'psychologists'

urlpatterns = [
    path('register/', PsychologistRegistrationView.as_view(), name='register'),
    path('me/', PsychologistProfileView.as_view(), name='profile'),
    path('search/', PsychologistSearchView.as_view(), name='search'),
    path('availability/', AvailabilityCreateView.as_view(), name='availability-create'),
    path('availability/<int:availability_id>/', AvailabilityDetailView.as_view(), name='availability-detail'),
    path('availability/list/', AvailabilityListView.as_view(), name='availability-list'),
    path('availability/bulk/', AvailabilityBulkView.as_view(), name='availability-bulk'),
    path('<str:psychologist_id>/verify/', PsychologistVerificationView.as_view(), name='verify'),
]