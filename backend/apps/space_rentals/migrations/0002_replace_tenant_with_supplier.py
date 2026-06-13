from django.db import migrations, models
import django.db.models.deletion


def set_default_supplier(apps, schema_editor):
    SpaceRental = apps.get_model('space_rentals', 'SpaceRental')
    Supplier = apps.get_model('suppliers', 'Supplier')
    default_supplier = Supplier.objects.order_by('id').first()
    if default_supplier:
        SpaceRental.objects.filter(supplier__isnull=True).update(supplier_id=default_supplier.id)


class Migration(migrations.Migration):

    dependencies = [
        ('suppliers', '0001_initial'),
        ('space_rentals', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='spacerental',
            name='supplier',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='space_rentals',
                to='suppliers.supplier',
                verbose_name='المورد',
            ),
        ),
        migrations.RunPython(set_default_supplier, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='spacerental',
            name='tenant_name',
        ),
        migrations.AlterField(
            model_name='spacerental',
            name='supplier',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='space_rentals',
                to='suppliers.supplier',
                verbose_name='المورد',
            ),
        ),
    ]
