# Generated manually

from collections import defaultdict

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def group_existing_items(apps, schema_editor):
    Item = apps.get_model('items', 'Item')
    ItemBatch = apps.get_model('items', 'ItemBatch')

    groups = defaultdict(list)
    for item in Item.objects.select_related('supplier').order_by('created_at'):
        key = (item.supplier_id, item.created_at.date())
        groups[key].append(item)

    for (supplier_id, _), items in groups.items():
        batch = ItemBatch.objects.create(
            supplier_id=supplier_id,
            created_at=items[0].created_at,
        )
        Item.objects.filter(id__in=[item.id for item in items]).update(batch_id=batch.id)


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0001_initial'),
        ('suppliers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ItemBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='item_batches', to=settings.AUTH_USER_MODEL, verbose_name='أنشئ بواسطة')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='item_batches', to='suppliers.supplier', verbose_name='الشركة / المورد')),
            ],
            options={
                'verbose_name': 'ملف أصناف',
                'verbose_name_plural': 'ملفات الأصناف',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='item',
            name='batch',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='items', to='items.itembatch', verbose_name='الملف'),
        ),
        migrations.RunPython(group_existing_items, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='item',
            name='supplier',
        ),
        migrations.AlterField(
            model_name='item',
            name='batch',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='items.itembatch', verbose_name='الملف'),
        ),
    ]
