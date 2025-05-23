from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AuthViewSet,
    UserViewSet,
    EmailVerificationView,
    PasswordResetRequestView,
    PasswordResetConfirmView
)

# Create router for ViewSets
router = DefaultRouter()
router.register('auth', AuthViewSet, basename='auth')
router.register('users', UserViewSet, basename='users')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),

    # Individual APIView routes
    path('auth/verify-email/<str:uidb64>/<str:token>/',
         EmailVerificationView.as_view(),
         name='verify-email'),

    path('auth/password-reset/',
         PasswordResetRequestView.as_view(),
         name='password-reset-request'),

    path('auth/password-reset-confirm/',
         PasswordResetConfirmView.as_view(),
         name='password-reset-confirm'),
]