# appointments/services/face_verification_service.py

import face_recognition
import cv2
import numpy as np
import logging
import pickle
import requests
from PIL import Image
from io import BytesIO
from typing import Tuple, Optional, Dict, Any
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import Appointment
from parents.models import Parent

logger = logging.getLogger(__name__)


class FaceVerificationError(Exception):
    """Base exception for face verification errors"""
    pass


class NoFaceDetectedError(FaceVerificationError):
    """Raised when no face is detected in the image"""
    pass


class MultipleFacesDetectedError(FaceVerificationError):
    """Raised when multiple faces are detected in the image"""
    pass


class ParentEmbeddingNotFoundError(FaceVerificationError):
    """Raised when parent doesn't have a face embedding"""
    pass


class ImageProcessingError(FaceVerificationError):
    """Raised when image processing fails"""
    pass


class FaceVerificationService:
    """
    Service for face verification functionality including embedding generation and verification
    """

    # Face recognition tolerance (lower = more strict)
    FACE_RECOGNITION_TOLERANCE = getattr(settings, 'FACE_RECOGNITION', {}).get('TOLERANCE', 0.6)

    # Blur detection threshold (higher = less blurry required)
    BLUR_THRESHOLD = 100.0

    # Image validation settings
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_FORMATS = {'JPEG', 'PNG', 'JPG'}

    @staticmethod
    def verify_parent_for_session(appointment: Appointment, live_image_data: bytes) -> Dict[str, Any]:
        """
        Main function to verify parent identity for session start

        Args:
            appointment: Appointment instance
            live_image_data: Raw image data captured by psychologist

        Returns:
            Dict with verification result and details

        Raises:
            FaceVerificationError: Various face verification errors
        """
        try:
            # Validate appointment
            if appointment.session_type != 'InitialConsultation':
                raise FaceVerificationError("Face verification only available for Initial Consultations")

            if appointment.appointment_status != 'Scheduled':
                raise FaceVerificationError("Can only verify scheduled appointments")

            # Get parent and validate they have embedding
            parent = appointment.parent
            if not parent.face_embedding:
                raise ParentEmbeddingNotFoundError(
                    "Parent doesn't have a face embedding. Please update profile picture."
                )

            # Process live image and extract face encoding
            live_encoding = FaceVerificationService._extract_face_encoding_from_bytes(live_image_data)

            # Load stored embedding
            stored_encoding = FaceVerificationService._load_face_embedding(parent)

            # Perform face comparison
            is_match = FaceVerificationService._compare_face_encodings(stored_encoding, live_encoding)

            result = {
                'is_match': is_match,
                'confidence_score': FaceVerificationService._calculate_confidence_score(
                    stored_encoding, live_encoding
                ),
                'parent_id': str(parent.user.id),
                'parent_name': parent.full_name,
                'verification_timestamp': timezone.now().isoformat()
            }

            # If verification successful, update appointment
            if is_match:
                appointment.session_verified_at = timezone.now()
                appointment.actual_start_time = timezone.now()
                appointment.appointment_status = 'In_Progress'
                # Set the psychologist who performed the verification
                appointment.session_verified_by = appointment.psychologist
                appointment.save(update_fields=[
                    'session_verified_at', 'actual_start_time', 'appointment_status',
                    'session_verified_by', 'updated_at'
                ])

                result['appointment_updated'] = True
                result['new_status'] = 'In_Progress'

                logger.info(f"Face verification successful for appointment {appointment.appointment_id}")
            else:
                result['appointment_updated'] = False
                logger.warning(f"Face verification failed for appointment {appointment.appointment_id}")

            return result

        except FaceVerificationError:
            # Re-raise face verification errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in face verification: {str(e)}")
            raise FaceVerificationError(f"Face verification failed: {str(e)}")

    @staticmethod
    def _extract_face_encoding_from_bytes(image_data: bytes) -> np.ndarray:
        """
        Extract face encoding from raw image bytes

        Args:
            image_data: Raw image data

        Returns:
            Face encoding as numpy array

        Raises:
            NoFaceDetectedError: If no face found
            MultipleFacesDetectedError: If multiple faces found
            ImageProcessingError: If image processing fails
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(BytesIO(image_data))

            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Convert PIL Image to numpy array for face_recognition
            image_array = np.array(image)

            # Validate image is not too blurry
            if not FaceVerificationService._validate_image_quality(image_array):
                raise ImageProcessingError("Image is too blurry for face recognition")

            # Find face locations
            face_locations = face_recognition.face_locations(image_array)

            if len(face_locations) == 0:
                raise NoFaceDetectedError("No face detected in the image")

            if len(face_locations) > 1:
                raise MultipleFacesDetectedError("Multiple faces detected. Please ensure only one person is in the image")

            # Extract face encoding
            face_encodings = face_recognition.face_encodings(image_array, face_locations)

            if len(face_encodings) == 0:
                raise NoFaceDetectedError("Could not extract face features from the image")

            return face_encodings[0]

        except FaceVerificationError:
            # Re-raise face verification errors
            raise
        except Exception as e:
            logger.error(f"Error processing image for face encoding: {str(e)}")
            raise ImageProcessingError(f"Failed to process image: {str(e)}")

    @staticmethod
    def _validate_image_quality(image_array: np.ndarray) -> bool:
        """
        Validate image quality for face recognition

        Args:
            image_array: Image as numpy array

        Returns:
            True if image quality is acceptable
        """
        try:
            # Convert to grayscale for blur detection
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

            # Calculate variance of Laplacian (blur detection)
            variance = cv2.Laplacian(gray, cv2.CV_64F).var()

            # Return True if image is not too blurry
            return variance > FaceVerificationService.BLUR_THRESHOLD

        except Exception as e:
            logger.warning(f"Error validating image quality: {str(e)}")
            # If validation fails, assume image is acceptable
            return True

    @staticmethod
    def _load_face_embedding(parent: Parent) -> np.ndarray:
        """
        Load face embedding from parent model

        Args:
            parent: Parent instance

        Returns:
            Face encoding as numpy array

        Raises:
            ParentEmbeddingNotFoundError: If no embedding found
        """
        try:
            if not parent.face_embedding:
                raise ParentEmbeddingNotFoundError("No face embedding found for parent")

            # Deserialize the embedding
            embedding = pickle.loads(parent.face_embedding)

            # Validate it's a numpy array with correct shape
            if not isinstance(embedding, np.ndarray) or embedding.shape != (128,):
                raise ParentEmbeddingNotFoundError("Invalid face embedding format")

            return embedding

        except pickle.PickleError as e:
            logger.error(f"Error deserializing face embedding: {str(e)}")
            raise ParentEmbeddingNotFoundError("Could not load face embedding")

    @staticmethod
    def _compare_face_encodings(stored_encoding: np.ndarray, live_encoding: np.ndarray) -> bool:
        """
        Compare two face encodings to determine if they match

        Args:
            stored_encoding: Stored face encoding
            live_encoding: Live captured face encoding

        Returns:
            True if faces match
        """
        try:
            # Use face_recognition library's compare function
            matches = face_recognition.compare_faces(
                [stored_encoding],
                live_encoding,
                tolerance=FaceVerificationService.FACE_RECOGNITION_TOLERANCE
            )

            return matches[0] if matches else False

        except Exception as e:
            logger.error(f"Error comparing face encodings: {str(e)}")
            return False

    @staticmethod
    def _calculate_confidence_score(stored_encoding: np.ndarray, live_encoding: np.ndarray) -> float:
        """
        Calculate confidence score for face matching

        Args:
            stored_encoding: Stored face encoding
            live_encoding: Live captured face encoding

        Returns:
            Confidence score between 0 and 1
        """
        try:
            # Calculate face distance (lower = more similar)
            distance = face_recognition.face_distance([stored_encoding], live_encoding)[0]

            # Convert distance to confidence score (0-1, higher = more confident)
            # Distance typically ranges from 0 to 1, with 0.6 being the default threshold
            confidence = max(0.0, min(1.0, 1.0 - distance))

            return round(confidence, 3)

        except Exception as e:
            logger.warning(f"Error calculating confidence score: {str(e)}")
            return 0.0

    @staticmethod
    def generate_face_embedding_from_url(image_url: str) -> Optional[bytes]:
        """
        Generate face embedding from image URL (for profile picture processing)

        Args:
            image_url: URL to the image

        Returns:
            Serialized face embedding or None if failed

        Raises:
            FaceVerificationError: Various face processing errors
        """
        try:
            # Download image from URL
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Validate image size
            if len(response.content) > FaceVerificationService.MAX_IMAGE_SIZE:
                raise ImageProcessingError("Image file too large")

            # Extract face encoding
            face_encoding = FaceVerificationService._extract_face_encoding_from_bytes(response.content)

            # Serialize and return
            return pickle.dumps(face_encoding)

        except requests.RequestException as e:
            logger.error(f"Error downloading image from URL {image_url}: {str(e)}")
            raise ImageProcessingError(f"Could not download image: {str(e)}")
        except FaceVerificationError:
            # Re-raise face verification errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating embedding from URL: {str(e)}")
            raise FaceVerificationError(f"Failed to generate embedding: {str(e)}")

    @staticmethod
    def validate_profile_picture_for_embedding(image_url: str) -> Dict[str, Any]:
        """
        Validate profile picture before generating embedding

        Args:
            image_url: URL to the profile picture

        Returns:
            Validation result dictionary
        """
        try:
            # Download and validate image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Check file size
            if len(response.content) > FaceVerificationService.MAX_IMAGE_SIZE:
                return {
                    'valid': False,
                    'error': 'Image file too large (max 5MB)',
                    'error_code': 'FILE_TOO_LARGE'
                }

            # Check image format
            try:
                image = Image.open(BytesIO(response.content))
                if image.format not in FaceVerificationService.ALLOWED_FORMATS:
                    return {
                        'valid': False,
                        'error': f'Invalid image format. Allowed: {", ".join(FaceVerificationService.ALLOWED_FORMATS)}',
                        'error_code': 'INVALID_FORMAT'
                    }
            except Exception:
                return {
                    'valid': False,
                    'error': 'Invalid image file',
                    'error_code': 'INVALID_IMAGE'
                }

            # Validate face content
            try:
                FaceVerificationService._extract_face_encoding_from_bytes(response.content)
                return {
                    'valid': True,
                    'message': 'Profile picture is valid for face recognition'
                }
            except NoFaceDetectedError:
                return {
                    'valid': False,
                    'error': 'No face detected in the image. Please upload a clear photo of your face.',
                    'error_code': 'NO_FACE_DETECTED'
                }
            except MultipleFacesDetectedError:
                return {
                    'valid': False,
                    'error': 'Multiple faces detected. Please upload a photo with only your face.',
                    'error_code': 'MULTIPLE_FACES'
                }
            except ImageProcessingError as e:
                return {
                    'valid': False,
                    'error': str(e),
                    'error_code': 'IMAGE_QUALITY_ISSUE'
                }

        except requests.RequestException:
            return {
                'valid': False,
                'error': 'Could not access the image URL',
                'error_code': 'URL_ACCESS_ERROR'
            }
        except Exception as e:
            logger.error(f"Unexpected error validating profile picture: {str(e)}")
            return {
                'valid': False,
                'error': 'Failed to validate image',
                'error_code': 'VALIDATION_ERROR'
            }

    @staticmethod
    def get_parent_embedding_status(parent: Parent) -> Dict[str, Any]:
        """
        Get status of parent's face embedding

        Args:
            parent: Parent instance

        Returns:
            Embedding status information
        """
        has_embedding = bool(parent.face_embedding)
        has_profile_picture = bool(parent.user.profile_picture_url)

        status = {
            'has_embedding': has_embedding,
            'has_profile_picture': has_profile_picture,
            'embedding_created_at': parent.face_embedding_created_at,
            'can_verify_sessions': has_embedding,
        }

        if not has_embedding and not has_profile_picture:
            status['message'] = 'Please upload a profile picture to enable session verification'
            status['action_required'] = 'UPLOAD_PICTURE'
        elif not has_embedding and has_profile_picture:
            status['message'] = 'Processing profile picture for face recognition...'
            status['action_required'] = 'WAIT_PROCESSING'
        elif has_embedding:
            status['message'] = 'Face verification enabled'
            status['action_required'] = 'NONE'

        return status