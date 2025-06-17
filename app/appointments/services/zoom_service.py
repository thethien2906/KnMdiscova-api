# appointments/services/zoom_service.py

import logging
import requests
import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


class ZoomAuthenticationError(Exception):
    """Raised when Zoom authentication fails"""
    pass


class ZoomMeetingCreationError(Exception):
    """Raised when Zoom meeting creation fails"""
    pass


class ZoomMeetingUpdateError(Exception):
    """Raised when Zoom meeting update fails"""
    pass


class ZoomMeetingDeletionError(Exception):
    """Raised when Zoom meeting deletion fails"""
    pass


class ZoomService:
    """
    Service layer for Zoom API integration.
    Handles OAuth authentication, meeting creation, updates, and deletion.
    """

    def __init__(self):
        self.config = settings.ZOOM_CONFIG
        self.enabled = self.config.get('ENABLED', False)
        self.token_cache_key = 'zoom_oauth_token'

    def is_enabled(self) -> bool:
        """Check if Zoom integration is enabled"""
        return self.enabled and all([
            self.config.get('ACCOUNT_ID'),
            self.config.get('CLIENT_ID'),
            self.config.get('CLIENT_SECRET')
        ])

    def _get_access_token(self) -> str:
        """
        Get Zoom OAuth access token using Server-to-Server OAuth.
        Implements caching to avoid unnecessary token requests.
        """
        # Check cache first
        cached_token = cache.get(self.token_cache_key)
        if cached_token:
            return cached_token

        # Request new token
        try:
            url = self.config['OAUTH_TOKEN_URL']

            # Server-to-Server OAuth flow
            params = {
                'grant_type': 'account_credentials',
                'account_id': self.config['ACCOUNT_ID']
            }

            # Basic auth with client credentials
            auth = (self.config['CLIENT_ID'], self.config['CLIENT_SECRET'])

            response = requests.post(
                url,
                params=params,
                auth=auth,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Zoom OAuth failed: {response.status_code} - {response.text}")
                raise ZoomAuthenticationError(f"Failed to obtain access token: {response.status_code}")

            data = response.json()
            access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)  # Default 1 hour

            if not access_token:
                raise ZoomAuthenticationError("No access token in response")

            # Cache token (expire 5 minutes before actual expiry)
            cache_duration = max(expires_in - 300, 60)
            cache.set(self.token_cache_key, access_token, cache_duration)

            logger.info("Successfully obtained Zoom access token")
            return access_token

        except requests.RequestException as e:
            logger.error(f"Zoom OAuth request failed: {str(e)}")
            raise ZoomAuthenticationError(f"OAuth request failed: {str(e)}")

    def _make_api_request(self, method: str, endpoint: str,
                         data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated request to Zoom API
        """
        if not self.is_enabled():
            raise ZoomMeetingCreationError("Zoom integration is not enabled")

        access_token = self._get_access_token()

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        url = f"{self.config['API_BASE_URL']}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=30
            )

            # Handle different response codes
            if response.status_code == 401:
                # Token might be expired, clear cache and retry once
                cache.delete(self.token_cache_key)
                access_token = self._get_access_token()
                headers['Authorization'] = f'Bearer {access_token}'

                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    timeout=30
                )

            response.raise_for_status()

            # Some endpoints return empty response
            if response.content:
                return response.json()
            return {}

        except requests.RequestException as e:
            logger.error(f"Zoom API request failed: {str(e)}")
            raise

    def create_meeting_for_appointment(self, appointment) -> Dict[str, Any]:
        """
        Create a Zoom meeting for an online appointment.

        Args:
            appointment: Appointment model instance

        Returns:
            Dict containing meeting_id and meeting_link
        """
        if appointment.session_type != 'OnlineMeeting':
            raise ValueError("Zoom meetings are only for online sessions")

        try:
            # Generate secure meeting password
            meeting_password = self._generate_meeting_password()

            # Prepare meeting data
            meeting_data = {
                'topic': f"Session with {appointment.psychologist.display_name}",
                'type': 2,  # Scheduled meeting
                'start_time': appointment.scheduled_start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'duration': self.config['MEETING_DEFAULTS']['DURATION_MINUTES'],
                'timezone': self.config['MEETING_DEFAULTS']['TIMEZONE'],
                'password': meeting_password,
                'agenda': f"Online therapy session for {appointment.child.display_name}",
                'settings': {
                    'host_video': True,
                    'participant_video': True,
                    'join_before_host': self.config['MEETING_DEFAULTS']['ENABLE_JOIN_BEFORE_HOST'],
                    'jbh_time': self.config['MEETING_DEFAULTS']['JOIN_BEFORE_HOST_MINUTES'],
                    'mute_upon_entry': self.config['MEETING_DEFAULTS']['MUTE_UPON_ENTRY'],
                    'watermark': False,
                    'use_pmi': False,
                    'approval_type': 2,  # No registration required
                    'audio': 'both',  # Both telephony and VoIP
                    'auto_recording': self.config['MEETING_DEFAULTS']['AUTO_RECORDING'],
                    'waiting_room': self.config['MEETING_DEFAULTS']['ENABLE_WAITING_ROOM'],
                    'meeting_authentication': self.config['SECURITY']['ENFORCE_LOGIN'],
                    'authentication_domains': self.config['SECURITY']['ENFORCE_LOGIN_DOMAINS'],
                }
            }

            # Add alternative hosts if configured
            alt_hosts = self.config['SECURITY'].get('ALTERNATIVE_HOSTS', '').strip()
            if alt_hosts:
                meeting_data['settings']['alternative_hosts'] = alt_hosts

            # Create meeting via API
            result = self._make_api_request('POST', '/users/me/meetings', meeting_data)

            logger.info(f"Created Zoom meeting {result['id']} for appointment {appointment.appointment_id}")

            return {
                'meeting_id': str(result['id']),
                'meeting_link': result['join_url'],
                'meeting_password': meeting_password,
                'host_start_url': result.get('start_url'),  # For psychologist
                'meeting_details': {
                    'topic': result.get('topic'),
                    'duration': result.get('duration'),
                    'timezone': result.get('timezone'),
                }
            }

        except requests.RequestException as e:
            logger.error(f"Failed to create Zoom meeting: {str(e)}")
            raise ZoomMeetingCreationError(f"Failed to create meeting: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Zoom meeting: {str(e)}")
            raise ZoomMeetingCreationError(f"Unexpected error: {str(e)}")

    def update_meeting(self, meeting_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing Zoom meeting.

        Args:
            meeting_id: Zoom meeting ID
            updates: Dictionary of fields to update

        Returns:
            Updated meeting details
        """
        try:
            # Validate updates
            allowed_updates = {
                'topic', 'start_time', 'duration', 'timezone',
                'password', 'agenda', 'settings'
            }

            filtered_updates = {
                k: v for k, v in updates.items()
                if k in allowed_updates
            }

            if not filtered_updates:
                raise ValueError("No valid fields to update")

            result = self._make_api_request(
                'PATCH',
                f'/meetings/{meeting_id}',
                filtered_updates
            )

            logger.info(f"Updated Zoom meeting {meeting_id}")
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to update Zoom meeting {meeting_id}: {str(e)}")
            raise ZoomMeetingUpdateError(f"Failed to update meeting: {str(e)}")

    def delete_meeting(self, meeting_id: str) -> None:
        """
        Delete a Zoom meeting.

        Args:
            meeting_id: Zoom meeting ID to delete
        """
        try:
            self._make_api_request('DELETE', f'/meetings/{meeting_id}')
            logger.info(f"Deleted Zoom meeting {meeting_id}")

        except requests.RequestException as e:
            logger.error(f"Failed to delete Zoom meeting {meeting_id}: {str(e)}")
            raise ZoomMeetingDeletionError(f"Failed to delete meeting: {str(e)}")

    def get_meeting_details(self, meeting_id: str) -> Dict[str, Any]:
        """
        Get details of a Zoom meeting.

        Args:
            meeting_id: Zoom meeting ID

        Returns:
            Meeting details
        """
        try:
            result = self._make_api_request('GET', f'/meetings/{meeting_id}')
            return result

        except requests.RequestException as e:
            logger.error(f"Failed to get Zoom meeting details {meeting_id}: {str(e)}")
            raise

    def _generate_meeting_password(self) -> str:
        """
        Generate a secure meeting password following Zoom requirements.
        - 10 characters max
        - Can include alphanumeric and @-_* characters
        """
        # Use alphanumeric characters for better compatibility
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'
        password = ''.join(secrets.choice(alphabet) for _ in range(8))
        return password