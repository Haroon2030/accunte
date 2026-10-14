from django.db import migrations, models
import django.db.models.deletion


def link_notices_to_supplier_records(apps, schema_editor):
    """Every notice points at the supplier record of its account (creating the record when the account has none)."""
    Notice, Supplier = apps.get_model('portal', 'Notice'), apps.get_model('portal', 'Supplier')
    for n in Notice.objects.select_related('supplier').order_by('id'):
        user = n.supplier
        sup = Supplier.objects.filter(pk=user.supplier_id).first() if user.supplier_id else None
        if sup is None:
            code = (user.code or '').strip() or f'U-{user.pk}'
            sup = Supplier.objects.filter(code__iexact=code).first() or Supplier.objects.create(
                name=user.org or user.name, code=code, tax_no=user.tax_no or '')
        n.company = sup
        n.save(update_fields=['company'])


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0007_supplier_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='notice',
            name='company',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='portal.supplier'),
        ),
        migrations.RunPython(link_notices_to_supplier_records, migrations.RunPython.noop),
    ]
