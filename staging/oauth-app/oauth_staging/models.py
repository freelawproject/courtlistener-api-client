"""User model with CL-like API token.

Mirrors CourtListener's pattern: each user has a static API token
(like DRF TokenAuthentication) that the MCP server uses to call the
CL API on their behalf. The OAuth flow binds an OAuth access token
to the user, and the MCP server exchanges that for the user's CL
API token via the token introspection endpoint.
"""

import secrets

from django.conf import settings
from django.db import models


class CLAPIToken(models.Model):
    """Simulates a CourtListener API token.

    In real CL, this is ``rest_framework.authtoken.models.Token``.
    We replicate the same pattern so the MCP server can look up
    a user's CL token from their OAuth identity.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cl_api_token",
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CLAPIToken(user={self.user.username})"
