import time
from typing import Any
from django.core.management.base import BaseCommand
from psycopg2 import OperationalError as Psycopg2Error
from django.db.utils import OperationalError


class Command(BaseCommand):
    def handle(self, *arg: Any, **options: Any):
        self.stdout.write('waiting for db')
        db_up=False
        while db_up is False:
            try:
                self.check(databases=["default"])
                db_up=True
            except (Psycopg2Error, OperationalError):
                self.stdout.write("Database unavailable waiting 1 sec")
                time.sleep(1)
        self.stdout.write(self.style.SUCCESS('DATABASE AVAILABLE'))