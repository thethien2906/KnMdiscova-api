# parents/urls.py
from django.urls import path
from . import views

app_name = 'parents'

urlpatterns = [
    # Parent profile endpoints
    path(
        'profile/',
        views.ParentProfileView.as_view(),
        name='profile'
    ),

    # Communication preferences endpoints
    path(
        'communication-preferences/',
        views.CommunicationPreferencesView.as_view(),
        name='communication-preferences'
    ),

    # Onboarding status
    path(
        'onboarding-status/',
        views.ParentOnboardingStatusView.as_view(),
        name='onboarding-status'
    ),
]