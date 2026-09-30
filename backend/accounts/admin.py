from django.contrib import admin

from .models import PhoneVerification, Profile, SocialAccount


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "phone")


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "uid", "created_at")
    list_filter = ("provider",)


@admin.register(PhoneVerification)
class PhoneVerificationAdmin(admin.ModelAdmin):
    list_display = ("phone", "attempts", "expires_at", "verified_at", "created_at")
    exclude = ("code_hash",)
