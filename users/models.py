from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    AUTH_PROVIDERS = (
        ('email', 'email'),
        ('google', 'google'),
    )
    
    auth_provider = models.CharField(
        max_length=50, 
        choices=AUTH_PROVIDERS, 
        default='email'
    )

    username = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    password = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username
