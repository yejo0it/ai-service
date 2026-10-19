from django.db import migrations
from django.utils import timezone


def start_sessions(apps, schema_editor):
    """
    만료 정책 도입 전에 발급된 토큰은 로그인 시각 기록이 없어 오래된 토큰이 한꺼번에 만료되어 버린다.
    기존 로그인은 배포 시점을 로그인·마지막 활동 시각으로 보고 정책을 적용한다.
    """
    Token = apps.get_model("authtoken", "Token")
    AuthSession = apps.get_model("accounts", "AuthSession")
    now = timezone.now()
    Token.objects.update(created=now)
    for token in Token.objects.all():
        AuthSession.objects.update_or_create(token=token, defaults={"last_active_at": now})


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_authsession'),
        ('authtoken', '0004_alter_tokenproxy_options'),
    ]

    operations = [
        migrations.RunPython(start_sessions, migrations.RunPython.noop),
    ]
