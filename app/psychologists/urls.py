# psychologists/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PsychologistProfileViewSet,
    PsychologistAvailabilityViewSet,
    PsychologistMarketplaceViewSet,
    PsychologistManagementViewSet
)

# Create router for ViewSets
router = DefaultRouter()
router.register('profile', PsychologistProfileViewSet, basename='psychologist-profile')
router.register('availability', PsychologistAvailabilityViewSet, basename='psychologist-availability')
router.register('marketplace', PsychologistMarketplaceViewSet, basename='psychologist-marketplace')
router.register('manage', PsychologistManagementViewSet, basename='psychologist-management')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),
]

# The resulting URL patterns will be:
#
# Psychologist Profile Management (for psychologists):
# - GET    /api/psychologists/profile/                              -> get current psychologist's profile
# - POST   /api/psychologists/profile/                              -> create psychologist profile
# - PATCH  /api/psychologists/profile/                              -> update current psychologist's profile
# - GET    /api/psychologists/profile/completeness/                 -> get profile completeness & verification status
# - GET    /api/psychologists/profile/education/                    -> get education entries
# - PATCH  /api/psychologists/profile/education/                    -> update education entries
# - GET    /api/psychologists/profile/certifications/               -> get certification entries
# - PATCH  /api/psychologists/profile/certifications/               -> update certification entries
#
# Psychologist Availability Management:
# - GET    /api/psychologists/availability/my-availability/         -> get current psychologist's availability blocks
# - POST   /api/psychologists/availability/                         -> create availability block
# - GET    /api/psychologists/availability/{id}/                    -> get specific availability block
# - PATCH  /api/psychologists/availability/{id}/                    -> update availability block
# - DELETE /api/psychologists/availability/{id}/                    -> delete availability block
# - GET    /api/psychologists/availability/weekly-summary/          -> get weekly availability summary
# - POST   /api/psychologists/availability/bulk-create/             -> create multiple availability blocks
# - GET    /api/psychologists/availability/appointment-slots/       -> get available appointment slots
#
# Psychologist Marketplace (for parents to browse):
# - GET    /api/psychologists/marketplace/                          -> list marketplace psychologists
# - GET    /api/psychologists/marketplace/{id}/                     -> get detailed psychologist profile
# - POST   /api/psychologists/marketplace/search/                   -> search psychologists
# - GET    /api/psychologists/marketplace/filter/                   -> filter psychologists by query params
# - GET    /api/psychologists/marketplace/{id}/availability/        -> get psychologist availability for booking
#
# Psychologist Management (admin access):
# - GET    /api/psychologists/manage/                               -> list all psychologists (admin)
# - GET    /api/psychologists/manage/{id}/                          -> get detailed psychologist profile (admin)
# - POST   /api/psychologists/manage/search/                        -> search all psychologists (admin)
# - GET    /api/psychologists/manage/statistics/                    -> get platform-wide statistics (admin)