from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0002_itembatch_and_group_items'),
    ]

    operations = [
        migrations.AddField(
            model_name='itembatch',
            name='payment_status',
            field=models.CharField(
                choices=[('unpaid', 'غير مدفوع'), ('paid', 'مدفوع')],
                default='unpaid',
                max_length=10,
                verbose_name='حالة الدفع',
            ),
        ),
    ]
