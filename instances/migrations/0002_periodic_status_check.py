from django.db import migrations


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    schedule, _ = IntervalSchedule.objects.get_or_create(every=5, period='minutes')
    PeriodicTask.objects.get_or_create(
        name='instances.refresh_all_instances_status',
        defaults={
            'interval': schedule,
            'task': 'instances.tasks.refresh_all_instances_status',
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='instances.refresh_all_instances_status').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0001_initial'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
