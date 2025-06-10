# users/exceptions.py
"""
Custom exceptions for authentication and user management
"""

class AuthenticationServiceError(Exception):
    """Base exception for authentication service errors"""
    pass


class GoogleAuthError(AuthenticationServiceError):
    """Base exception for Google authentication errors"""
    pass


class InvalidGoogleTokenError(GoogleAuthError):
    """Raised when Google token is invalid or expired"""
    pass


class GoogleUserInfoError(GoogleAuthError):
    """Raised when unable to retrieve user info from Google"""
    pass


class EmailAlreadyExistsError(AuthenticationServiceError):
    """Raised when attempting to register with an existing email"""
    def __init__(self, email: str, existing_provider: str = None):
        self.email = email
        self.existing_provider = existing_provider
        super().__init__(f"Email {email} already exists with {existing_provider or 'regular'} authentication")


class GoogleEmailNotVerifiedError(GoogleAuthError):
    """Raised when Google account email is not verified"""
    pass


class UserTypeRequiredError(AuthenticationServiceError):
    """Raised when user type is required for Google registration"""
    pass


class GoogleConfigurationError(GoogleAuthError):
    """Raised when Google OAuth is not properly configured"""
    pass