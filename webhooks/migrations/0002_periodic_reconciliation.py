from django.db import migrations


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')

    schedule, _ = IntervalSchedule.objects.get_or_create(every=15, period='minutes')
    PeriodicTask.objects.get_or_create(
        name='webhooks.reconcile_missed_webhooks',
        defaults={
            'interval': schedule,
            'task': 'webhooks.tasks.reconcile_missed_webhooks',
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(name='webhooks.reconcile_missed_webhooks').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0001_initial'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
