from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('space_rentals', '0002_replace_tenant_with_supplier'),
    ]

    operations = [
        migrations.AddField(
            model_name='spacerental',
            name='rental_type',
            field=models.CharField(
                choices=[('shelf', 'إيجار رف'), ('floor_gondola', 'إيجار جندولة أرضية')],
                default='shelf',
                max_length=20,
                verbose_name='نوع الإيجار',
            ),
        ),
        migrations.RemoveField(
            model_name='spacerental',
            name='area_sqm',
        ),
    ]
