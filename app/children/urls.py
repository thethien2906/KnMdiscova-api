# children/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChildProfileViewSet,
    ChildManagementViewSet
)

# Create router for ViewSets
router = DefaultRouter()
router.register('profile', ChildProfileViewSet, basename='child-profile')
router.register('manage', ChildManagementViewSet, basename='child-management')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),
]

# The resulting URL patterns will be:
#
# Child Profile Management (for parents):
# - GET    /api/children/profile/my-children/               -> get current parent's children list
# - POST   /api/children/profile/                          -> create new child profile
# - GET    /api/children/profile/{id}/                     -> get detailed child profile
# - PATCH  /api/children/profile/{id}/                     -> update child profile
# - DELETE /api/children/profile/{id}/                     -> delete child profile
# - GET    /api/children/profile/{id}/profile-summary/     -> get child profile summary & metrics
# - POST   /api/children/profile/{id}/manage-consent/      -> manage individual consent
# - POST   /api/children/profile/{id}/bulk-consent/        -> manage multiple consents at once
#
# Child Management (admin/psychologist access):
# - GET    /api/children/manage/                           -> list children (filtered by permissions)
# - GET    /api/children/manage/{id}/                      -> retrieve specific child profile
# - POST   /api/children/manage/search/                    -> search children by criteria
# - GET    /api/children/manage/statistics/                -> get platform-wide child statistics (admin only)