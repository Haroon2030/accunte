from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('portal', '0016_lookup_codes'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='priority',
            field=models.CharField(
                choices=[('urgent', 'مستعجل'), ('medium', 'متوسط'), ('normal', 'عادي')],
                default='normal',
                max_length=6,
                verbose_name='أولوية السداد',
            ),
        ),
    ]
