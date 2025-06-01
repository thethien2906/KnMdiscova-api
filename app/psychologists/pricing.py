# Create psychologists/pricing.py
from django.conf import settings
from decimal import Decimal

class MVPPricingService:
    """
    MVP pricing service with fixed rates for all psychologists
    """

    @staticmethod
    def get_online_session_rate():
        """Get fixed rate for online sessions"""
        return Decimal(getattr(settings, 'MVP_PRICING', {}).get('ONLINE_SESSION_RATE', '150.00'))

    @staticmethod
    def get_initial_consultation_rate():
        """Get fixed rate for initial consultations"""
        return Decimal(getattr(settings, 'MVP_PRICING', {}).get('INITIAL_CONSULTATION_RATE', '280.00'))

    @staticmethod
    def get_psychologist_rates(psychologist):
        """Get rates for a specific psychologist (MVP: same for all)"""
        return {
            'online_session_rate': MVPPricingService.get_online_session_rate(),
            'initial_consultation_rate': MVPPricingService.get_initial_consultation_rate(),
            'currency': 'USD'
        }

    @staticmethod
    def calculate_appointment_cost(session_type):
        """Calculate cost for appointment based on session type"""
        if session_type == 'OnlineMeeting':
            return MVPPricingService.get_online_session_rate()
        elif session_type == 'InitialConsultation':
            return MVPPricingService.get_initial_consultation_rate()
        else:
            raise ValueError(f"Unknown session type: {session_type}")