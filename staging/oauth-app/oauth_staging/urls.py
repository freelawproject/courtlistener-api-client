from django.contrib import admin
from django.urls import include, path

from oauth_staging import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # django-oauth-toolkit endpoints:
    #   /oauth/authorize/   - authorization endpoint
    #   /oauth/token/       - token endpoint
    #   /oauth/revoke/      - token revocation
    path("oauth/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    # Custom introspection that returns the CL API token
    path("oauth/introspect/", views.introspect, name="introspect"),
]
