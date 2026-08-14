from django.db import migrations


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    schedule, _ = IntervalSchedule.objects.get_or_create(every=5, period='minutes')
    PeriodicTask.objects.get_or_create(
        name='triggers.dispatch_due_scheduled_messages',
        defaults={
            'interval': schedule,
            'task': 'triggers.tasks.dispatch_due_scheduled_messages',
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='triggers.dispatch_due_scheduled_messages').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('triggers', '0002_trigger_followup_apos_horas_and_more'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
