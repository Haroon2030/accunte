"""
Migration for Notification model
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0004_create_default_roles'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('payment', 'طلبات الدفع'), ('system', 'النظام')], default='payment', max_length=20, verbose_name='التصنيف')),
                ('title', models.CharField(max_length=200, verbose_name='العنوان')),
                ('message', models.TextField(verbose_name='الرسالة')),
                ('link', models.CharField(blank=True, max_length=500, verbose_name='الرابط')),
                ('is_read', models.BooleanField(default=False, verbose_name='مقروء')),
                ('read_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ القراءة')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL, verbose_name='المستلم')),
            ],
            options={
                'verbose_name': 'إشعار',
                'verbose_name_plural': 'الإشعارات',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['recipient', 'is_read', '-created_at'], name='core_notifi_recipie_6f0f0d_idx')],
            },
        ),
    ]
