# parents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ParentProfileViewSet,
    ParentManagementViewSet
)

# Create router for ViewSets
router = DefaultRouter()
router.register('profile', ParentProfileViewSet, basename='parent-profile')
router.register('manage', ParentManagementViewSet, basename='parent-management')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),
]

# The resulting URL patterns will be:
#
# Parent Profile Management (for current parent):
# - GET    /api/parents/profile/                              -> get current parent's profile
# - PATCH  /api/parents/profile/                              -> update current parent's profile
# - GET    /api/parents/profile/completeness/                 -> get profile completeness score
# - GET    /api/parents/profile/communication-preferences/    -> get communication preferences
# - PATCH  /api/parents/profile/communication-preferences/    -> update communication preferences
# - POST   /api/parents/profile/communication-preferences/reset/ -> reset preferences to defaults
#
# Parent Management (admin/psychologist access):
# - GET    /api/parents/manage/                               -> list parents (filtered by permissions)
# - GET    /api/parents/manage/{id}/                          -> retrieve specific parent profile
# - POST   /api/parents/manage/search/                        -> search parents (admin only)