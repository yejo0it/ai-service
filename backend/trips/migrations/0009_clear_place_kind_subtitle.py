from django.db import migrations

# 직접 추가·AI로 넣은 장소 카드는 이름 밑에 유형(관광지·식당 등)을 부제로 저장했었다. 표시하지 않으므로 비운다.
KIND_LABELS = ["항공편", "숙소", "공항", "관광지", "식당", "카페"]


def clear_kind_subtitle(apps, schema_editor):
    ItineraryItem = apps.get_model("trips", "ItineraryItem")
    ItineraryItem.objects.filter(source__in=["manual", "ai"], subtitle__in=KIND_LABELS).update(subtitle="")


class Migration(migrations.Migration):
    dependencies = [
        ("trips", "0008_hotel_phone"),
    ]

    operations = [
        migrations.RunPython(clear_kind_subtitle, migrations.RunPython.noop),
    ]
