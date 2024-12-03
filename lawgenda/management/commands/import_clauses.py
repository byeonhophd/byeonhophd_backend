# management/commands/import_clauses.py

from django.core.management.base import BaseCommand
from django.db import transaction
from lawgenda.models import Clause
import json

class Command(BaseCommand):
    help = 'Import clauses from JSON file efficiently using bulk_create'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Path to the JSON file to import')

    def handle(self, *args, **kwargs):
        json_file = kwargs['json_file']
        self.stdout.write(f"Importing clauses from {json_file}...")

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        clauses = []
        for identifier, content in data.items():
            clauses.append(Clause(identifier=identifier, content=content))

        batch_size = 1000  # 적절한 배치 크기로 조정 가능
        total = len(clauses)
        self.stdout.write(f"Total clauses to import: {total}")

        try:
            with transaction.atomic():
                Clause.objects.bulk_create(clauses, batch_size=batch_size, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS('Successfully imported clauses.'))
        except Exception as e:
            self.stderr.write(f"Error importing clauses: {e}")