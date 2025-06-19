# appointments/services/face_verification_service.py
"""
Face verification service for session verification.
Handles face recognition logic using the face_recognition library.
"""

import logging
import face_recognition
import numpy as np
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image
import io
import base64

from appointments.models import Appointment
from parents.models import Parent
from psychologists.models import Psychologist
from users.models import User

logger = logging.getLogger(__name__)


class FaceVerificationError(Exception):
    """Base exception for face verification errors"""
    pass


class NoFaceDetectedError(FaceVerificationError):
    """Raised when no face is detected in the image"""
    pass


class MultipleFacesDetectedError(FaceVerificationError):
    """Raised when multiple faces are detected"""
    pass


class ProfilePictureMissingError(FaceVerificationError):
    """Raised when parent has no profile picture"""
    pass


class FaceNotMatchedError(FaceVerificationError):
    """Raised when face doesn't match the stored embedding"""
    pass


class VerificationWindowExpiredError(FaceVerificationError):
    """Raised when verification is attempted outside allowed time window"""
    pass



class FaceVerificationService:
    """
    Service class for face verification business logic
    """

    # Face recognition tolerance (lower = stricter matching)
    FACE_MATCH_TOLERANCE = 0.6

    # Time window for verification (before and after scheduled time)
    VERIFICATION_WINDOW_BEFORE_MINUTES = 15
    VERIFICATION_WINDOW_AFTER_MINUTES = 30

    @staticmethod
    def generate_face_embedding(image_data: bytes) -> Optional[bytes]:
        """
        Generate face embedding from image data.

        Args:
            image_data: Image bytes

        Returns:
            Face embedding as bytes, or None if no face detected

        Raises:
            NoFaceDetectedError: If no face is detected
            MultipleFacesDetectedError: If multiple faces are detected
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Convert to numpy array
            image_array = np.array(image)

            # Find face encodings
            face_encodings = face_recognition.face_encodings(image_array)

            if len(face_encodings) == 0:
                raise NoFaceDetectedError("No face detected in the image")

            if len(face_encodings) > 1:
                raise MultipleFacesDetectedError(
                    f"Multiple faces detected ({len(face_encodings)}). Please ensure only one face is visible."
                )

            # Convert face encoding to bytes
            face_embedding = face_encodings[0].tobytes()

            logger.info("Face embedding generated successfully")
            return face_embedding

        except Exception as e:
            if isinstance(e, (NoFaceDetectedError, MultipleFacesDetectedError)):
                raise
            logger.error(f"Error generating face embedding: {str(e)}")
            raise FaceVerificationError(f"Failed to process image: {str(e)}")

    @staticmethod
    def compare_faces(stored_embedding: bytes, live_embedding: bytes) -> bool:
        """
        Compare two face embeddings.

        Args:
            stored_embedding: Stored face embedding bytes
            live_embedding: Live face embedding bytes

        Returns:
            True if faces match, False otherwise
        """
        try:
            # Convert bytes back to numpy arrays
            stored_array = np.frombuffer(stored_embedding, dtype=np.float64)
            live_array = np.frombuffer(live_embedding, dtype=np.float64)

            # Calculate face distance
            face_distance = face_recognition.face_distance([stored_array], live_array)[0]

            # Check if match
            is_match = face_distance <= FaceVerificationService.FACE_MATCH_TOLERANCE

            logger.info(f"Face comparison - Distance: {face_distance}, Match: {is_match}")
            return is_match

        except Exception as e:
            logger.error(f"Error comparing faces: {str(e)}")
            return False

    @classmethod
    def verify_appointment_parent(
        cls,
        appointment: Appointment,
        live_image_data: bytes,
        psychologist: Psychologist
    ) -> Dict[str, Any]:
        """
        Verify parent's identity for an appointment using face recognition.

        Args:
            appointment: The appointment to verify
            live_image_data: The live captured image data
            psychologist: The psychologist performing verification

        Returns:
            Dict with verification results

        Raises:
            Various FaceVerificationError subclasses
        """
        try:
            # Check if appointment belongs to the psychologist
            if appointment.psychologist != psychologist:
                raise FaceVerificationError("Appointment does not belong to this psychologist")

            # Check if within verification time window
            now = datetime.now(appointment.scheduled_start_time.tzinfo)
            scheduled_time = appointment.scheduled_start_time

            time_before = scheduled_time - timedelta(minutes=cls.VERIFICATION_WINDOW_BEFORE_MINUTES)
            time_after = scheduled_time + timedelta(minutes=cls.VERIFICATION_WINDOW_AFTER_MINUTES)

            if now < time_before or now > time_after:
                raise VerificationWindowExpiredError(
                    f"Verification allowed between {time_before.strftime('%H:%M')} "
                    f"and {time_after.strftime('%H:%M')}"
                )

            # Check appointment status
            if appointment.appointment_status not in ['Payment_Pending', 'Scheduled']:
                raise FaceVerificationError(
                    f"Cannot verify appointment with status: {appointment.appointment_status}"
                )

            # Get parent
            parent = appointment.parent

            # Check if parent has face embedding
            if not parent.face_embedding:
                # Try to generate from profile picture if available
                user = parent.user
                if not user.profile_picture_url:
                    raise ProfilePictureMissingError(
                        "Parent has no profile picture for verification"
                    )

                # For MVP, we'll require pre-generated embeddings
                raise ProfilePictureMissingError(
                    "Parent face embedding not found. Please update profile picture."
                )

            # Generate embedding from live image
            live_embedding = cls.generate_face_embedding(live_image_data)

            # Compare faces
            is_match = cls.compare_faces(parent.face_embedding, live_embedding)

            if not is_match:
                raise FaceNotMatchedError("Face verification failed - no match")

            # Update appointment with verification
            with transaction.atomic():
                appointment.session_verified_at = now
                appointment.session_verified_by = psychologist
                appointment.appointment_status = 'In_Progress'
                appointment.actual_start_time = now
                appointment.save(update_fields=[
                    'session_verified_at',
                    'session_verified_by',
                    'appointment_status',
                    'actual_start_time',
                    'updated_at'
                ])

            logger.info(
                f"Appointment {appointment.appointment_id} verified successfully "
                f"by psychologist {psychologist.user.email}"
            )

            return {
                'status': 'success',
                'message': 'Session verified successfully.',
                'appointment_status': appointment.appointment_status,
                'actual_start_time': appointment.actual_start_time.isoformat()
            }

        except FaceVerificationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in face verification: {str(e)}")
            raise FaceVerificationError(f"Verification failed: {str(e)}")

    @staticmethod
    def update_parent_face_embedding(parent: Parent, image_data: bytes) -> None:
        """
        Update parent's face embedding from profile picture.

        Args:
            parent: Parent instance
            image_data: Profile picture image data
        """
        try:
            # Generate face embedding
            face_embedding = FaceVerificationService.generate_face_embedding(image_data)

            if face_embedding:
                parent.face_embedding = face_embedding
                parent.face_embedding_created_at = datetime.now()
                parent.save(update_fields=[
                    'face_embedding',
                    'face_embedding_created_at',
                    'updated_at'
                ])

                logger.info(f"Updated face embedding for parent {parent.user.email}")

        except Exception as e:
            logger.error(f"Failed to update face embedding: {str(e)}")
            # Don't raise - this is a non-critical operation