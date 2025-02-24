from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule
from django_celery_beat.models import PeriodicTask


class Command(BaseCommand):
    help = "Setup periodic tasks"

    def handle(self, *args, **kwargs):
        try:
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=1,
                period=IntervalSchedule.SECONDS,
            )

            task, created = PeriodicTask.objects.get_or_create(
                name="Test periodic task",
                defaults={"task": "configs.tasks.test_task", "interval": schedule, "enabled": True},
            )

            if created:
                self.stdout.write(self.style.SUCCESS("Successfully created periodic task"))
            else:
                task.interval = schedule
                task.task = "configs.tasks.test_task"
                task.enabled = True
                task.save()
                self.stdout.write(self.style.SUCCESS("Successfully updated periodic task"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Unexpected error occurred: {str(e)}"))
            raise

        finally:
            self.stdout.write(self.style.SUCCESS("Command execution completed"))
