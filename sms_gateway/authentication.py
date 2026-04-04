"""
SMS Gateway API Authentication

This module provides API key authentication for REST APIs.
"""
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import authentication, exceptions
from .models import APIKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom API Key authentication for Django REST Framework.
    
    Clients should include the API key in the Authorization header:
        Authorization: ApiKey <api_key>
    
    Or in the X-API-Key header:
        X-API-Key: <api_key>
    """
    
    keyword = 'ApiKey'
    
    def authenticate(self, request):
        """
        Authenticate the request using API key.
        """
        # Check Authorization header
        auth_header = authentication.get_authorization_header(request).split()
        
        api_key = None
        
        # Try Authorization header: "ApiKey <key>"
        if len(auth_header) == 2 and auth_header[0].decode().lower() == self.keyword.lower():
            api_key = auth_header[1].decode()
        else:
            # Try X-API-Key header
            api_key = request.META.get('HTTP_X_API_KEY') or request.headers.get('X-API-Key')
        
        if not api_key:
            return None
        
        return self.authenticate_credentials(api_key)
    
    def authenticate_credentials(self, key):
        """
        Validate the API key and return the user.
        """
        try:
            api_key = APIKey.objects.select_related('user').get(
                key=key,
                is_active=True,
                revoked_at__isnull=True
            )
        except APIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')
        
        # Check if key is expired
        if api_key.expires_at and api_key.expires_at < timezone.now():
            raise exceptions.AuthenticationFailed('API key has expired')
        
        # Update last used timestamp
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=['last_used_at'])
        
        return (api_key.user, api_key)
    
    def authenticate_header(self, request):
        return self.keyword


class APIKeyManager:
    """
    Manager class for API key operations.
    """
    
    KEY_PREFIX = 'sg_live_'
    KEY_LENGTH = 48  # Length of the random part
    
    @classmethod
    def generate_key(cls):
        """
        Generate a new API key.
        
        Returns:
            str: The generated API key
        """
        # Generate a cryptographically secure random key
        random_part = secrets.token_urlsafe(cls.KEY_LENGTH)
        # Remove padding and take only what we need
        random_part = random_part.replace('-', '').replace('_', '')[:cls.KEY_LENGTH]
        return f"{cls.KEY_PREFIX}{random_part}"
    
    @classmethod
    def create_api_key(cls, user, name='Default', expires_days=None):
        """
        Create a new API key for a user.
        
        Args:
            user: User instance
            name: Name/description for the API key
            expires_days: Number of days until expiration (None for no expiration)
            
        Returns:
            APIKey: The created API key instance (with plaintext key in .key attribute)
        """
        key = cls.generate_key()
        
        expires_at = None
        if expires_days:
            expires_at = timezone.now() + timedelta(days=expires_days)
        
        api_key = APIKey.objects.create(
            user=user,
            key=key,
            name=name,
            expires_at=expires_at
        )
        
        # Store the plaintext key temporarily (only for display to user)
        api_key._plaintext_key = key
        
        return api_key
    
    @classmethod
    def revoke_api_key(cls, api_key_id, user):
        """
        Revoke an API key.
        
        Args:
            api_key_id: ID of the API key to revoke
            user: User requesting the revocation (must own the key)
            
        Returns:
            bool: True if revoked successfully
        """
        try:
            api_key = APIKey.objects.get(id=api_key_id, user=user)
            api_key.is_active = False
            api_key.revoked_at = timezone.now()
            api_key.save(update_fields=['is_active', 'revoked_at'])
            return True
        except APIKey.DoesNotExist:
            return False
    
    @classmethod
    def get_user_api_keys(cls, user, active_only=True):
        """
        Get all API keys for a user.
        
        Args:
            user: User instance
            active_only: If True, return only active keys
            
        Returns:
            QuerySet: APIKey queryset
        """
        queryset = APIKey.objects.filter(user=user)
        if active_only:
            queryset = queryset.filter(is_active=True, revoked_at__isnull=True)
        return queryset.order_by('-created_at')
