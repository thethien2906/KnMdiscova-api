from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    '''
    Customer user
    '''

    def email_validator(self, email):
        '''
        Validate email address
        '''
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError(_('Invalid email address'))

    def create_user(self, email, password=None, **extra_fields):
        '''
        Create user
        '''
        if not email:
            raise ValueError(_('The Email field must be set'))

        email = self.normalize_email(email)
        self.email_validator(email)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'Admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)

    def create_parent(self, email, password=None, **extra_fields):
        '''
        Create parent
        '''
        extra_fields.setdefault('is_verified', False)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'Parent')

        return self.create_user(email, password, **extra_fields)

    def create_psychologist(self, email, password=None, **extra_fields):
        '''
        Create psychologist
        '''
        extra_fields.setdefault('is_verified', False)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'Psychologist')

        return self.create_user(email, password, **extra_fields)