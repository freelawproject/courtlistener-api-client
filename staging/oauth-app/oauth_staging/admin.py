from django.contrib import admin

from oauth_staging.models import CLAPIToken


@admin.register(CLAPIToken)
class CLAPITokenAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created")
    readonly_fields = ("created",)
