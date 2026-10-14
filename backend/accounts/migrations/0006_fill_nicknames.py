from django.conf import settings
from django.db import migrations

from accounts.nickname import usable_nickname


def fill_nicknames(apps, schema_editor):
    """기존 회원 모두에게 닉네임을 준다. 예전에 쓰던 이름(first_name)이 규칙에 맞으면 그대로, 아니면 랜덤으로."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Profile = apps.get_model("accounts", "Profile")
    for user in User.objects.all():
        profile, _ = Profile.objects.get_or_create(user=user)
        if not profile.nickname:
            profile.nickname = usable_nickname(user.first_name)
            profile.save(update_fields=["nickname"])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_profile_nickname'),
    ]

    operations = [
        migrations.RunPython(fill_nicknames, migrations.RunPython.noop),
    ]
