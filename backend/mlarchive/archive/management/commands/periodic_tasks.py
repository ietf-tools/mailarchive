# Copyright The IETF Trust 2024, All Rights Reserved

from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django.core.management.base import BaseCommand

CRONTAB_DEFS = {
    # same as "@weekly" in a crontab
    "weekly": {
        "minute": "0",
        "hour": "0",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "0",
    },
    "daily": {
        "minute": "5",
        "hour": "0",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "*",
    },
    "hourly": {
        "minute": "5",
        "hour": "*",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "*",
    },
    "every_15m": {
        "minute": "*/15",
        "hour": "*",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "*",
    },
}


class Command(BaseCommand):
    """Manage periodic tasks"""
    crontabs = None

    def add_arguments(self, parser):
        parser.add_argument("--create-default", action="store_true")
        parser.add_argument("--enable", type=int, action="append")
        parser.add_argument("--disable", type=int, action="append")

    def handle(self, *args, **options):
        self.crontabs = self.get_or_create_crontabs()
        if options["create_default"]:
            self.create_default_tasks()
        if options["enable"]:
            self.enable_tasks(options["enable"])
        if options["disable"]:
            self.disable_tasks(options["disable"])
        self.show_tasks()

    def get_or_create_crontabs(self):
        crontabs = {}
        for label, definition in CRONTAB_DEFS.items():
            crontabs[label], _ = CrontabSchedule.objects.get_or_create(**definition)
        return crontabs

    def create_default_tasks(self):
        PeriodicTask.objects.get_or_create(
            name="Get list subscriber counts",
            task="mlarchive.archive.tasks.get_subscriber_counts_task",
            defaults=dict(
                enabled=False,
                crontab=self.crontabs["daily"],
                description="Get list subscriber counts from mailman"
            ),
        )

        PeriodicTask.objects.get_or_create(
            name="Get list membership",
            task="mlarchive.archive.tasks.get_membership_task",
            defaults=dict(
                enabled=False,
                crontab=self.crontabs["daily"],
                description="Get list membership from mailman"
            ),
        )

        PeriodicTask.objects.get_or_create(
            name="Purge incoming",
            task="mlarchive.archive.tasks.purge_incoming_task",
            defaults=dict(
                enabled=False,
                crontab=self.crontabs["daily"],
                description="Purge old messages from incoming directory"
            ),
        )

        PeriodicTask.objects.get_or_create(
            name="Update MBOX",
            task="mlarchive.archive.tasks.update_mbox_files_task",
            defaults=dict(
                enabled=False,
                crontab=self.crontabs["daily"],
                description="Update archive MBOX files"
            ),
        )


    def show_tasks(self):
        for label, crontab in self.crontabs.items():
            tasks = PeriodicTask.objects.filter(crontab=crontab).order_by(
                "task", "name"
            )
            self.stdout.write(f"\n{label} ({crontab.human_readable})\n")
            if tasks:
                for task in tasks:
                    desc = f"  {task.id:-3d}: {task.task} - {task.name}"
                    if task.enabled:
                        self.stdout.write(desc)
                    else:
                        self.stdout.write(self.style.NOTICE(f"{desc} - disabled"))
            else:
                self.stdout.write("  Nothing scheduled")

    def enable_tasks(self, pks):
        PeriodicTask.objects.filter(
            crontab__in=self.crontabs.values(), pk__in=pks
        ).update(enabled=True)

    def disable_tasks(self, pks):
        PeriodicTask.objects.filter(
            crontab__in=self.crontabs.values(), pk__in=pks
        ).update(enabled=False)
