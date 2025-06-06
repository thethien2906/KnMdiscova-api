# appointments/services/__init__.py

from .services import (
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentServiceError,
    AppointmentBookingError,
    AppointmentNotFoundError,
    AppointmentAccessDeniedError,
    AppointmentCancellationError,
    QRVerificationError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError,
    AppointmentSlotService,
    SlotGenerationError,
    AppointmentAnalyticsService,
    AppointmentUtilityService

)