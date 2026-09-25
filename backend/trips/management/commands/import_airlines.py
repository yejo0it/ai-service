import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from trips.models import Airline

class Command(BaseCommand):
    help = "CSV 파일로부터 항공사 목록 데이터를 읽어와 DB에 등록합니다."

    def add_arguments(self, parser):
        default_path = Path(settings.BASE_DIR) / "data" / "airlines.csv"
        parser.add_argument(
            "--file",
            type=str,
            default=str(default_path),
            help=f"항공사 CSV 파일 경로 (기본값: {default_path})"
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        path = Path(file_path)

        if not path.exists():
            self.stdout.write(self.style.ERROR(f"CSV 파일이 존재하지 않습니다: {file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"CSV 파일을 읽어옵니다: {file_path}"))    

        airlines_to_create = []

        with open(path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                name_ko = row.get("국문 항공사명")
                iata_code = row.get("IATA")
                country = row.get("국가")

                if not name_ko or not iata_code:
                    self.stdout.write(self.style.WARNING(f"항공사명 또는 IATA 코드가 누락된 행을 건너뜁니다: {row}"))
                    continue

                airlines_to_create.append(
                    Airline(
                    name_ko=name_ko,
                    iata_code=iata_code,
                    country=country
                    )
                )

            # 중복 insert 방지 처리 및 bulk_create 실행
            # ignore_conflicts=True: 이미 존재하는 iata_code가 있을 경우 무시하고 건너뜀
            created_objs = Airline.objects.bulk_create(airlines_to_create, ignore_conflicts=True)

            self.stdout.write(self.style.SUCCESS(f"총 {len(airlines_to_create)}개 중 {len(created_objs)}개의 항공사 정보가 성공적으로 DB에 등록되었습니다!" ))