# appointments/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AppointmentViewSet,
    AppointmentSlotViewSet,
    AppointmentAnalyticsViewSet
)

# Create router for ViewSets
router = DefaultRouter()
router.register('', AppointmentViewSet, basename='appointment')  # Main appointment endpoints
router.register('slots', AppointmentSlotViewSet, basename='appointment-slots')
router.register('analytics', AppointmentAnalyticsViewSet, basename='appointment-analytics')

# URL patterns
urlpatterns = [
    # ViewSet routes (handled by router)
    path('', include(router.urls)),
]

# The resulting URL patterns will be:
#
# Main Appointment Management:
# - GET    /api/appointments/                                  -> list appointments (with permission filtering)
# - POST   /api/appointments/                                  -> book new appointment
# - GET    /api/appointments/{id}/                             -> get detailed appointment information
# - PATCH  /api/appointments/{id}/                             -> update appointment details (notes)
# - GET    /api/appointments/my-appointments/                  -> get current user's appointments
# - POST   /api/appointments/{id}/cancel/                      -> cancel appointment
# - POST   /api/appointments/verify-qr/                        -> verify in-person appointment using QR code
# - POST   /api/appointments/search/                           -> search appointments with filters
# - GET    /api/appointments/available-slots/                  -> get available appointment slots for booking
# - POST   /api/appointments/{id}/complete/                    -> mark appointment as completed (psychologists only)
# - GET    /api/appointments/upcoming/                         -> get upcoming appointments
# - GET    /api/appointments/history/                          -> get past appointments
#
# Appointment Slot Management:
# - GET    /api/appointments/slots/                            -> list appointment slots (filtered by permissions)
# - POST   /api/appointments/slots/                            -> create appointment slot (admin/system use)
# - GET    /api/appointments/slots/{id}/                       -> get specific appointment slot details
# - DELETE /api/appointments/slots/{id}/                       -> delete appointment slot
# - GET    /api/appointments/slots/my-slots/                   -> get current psychologist's appointment slots
# - POST   /api/appointments/slots/generate-slots/             -> generate slots from availability blocks
# - GET    /api/appointments/slots/available-for-booking/      -> get available appointment slots for booking
# - POST   /api/appointments/slots/cleanup-past-slots/         -> clean up past unbooked slots (admin only)
# - GET    /api/appointments/slots/statistics/                 -> get appointment slot statistics (admin only)
#
# Appointment Analytics & Reporting:
# - GET    /api/appointments/analytics/psychologist-stats/     -> get appointment statistics for a psychologist
# - GET    /api/appointments/analytics/platform-stats/         -> get platform-wide appointment statistics (admin only)