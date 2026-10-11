from django.db import migrations


def create_role(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    if not Role.objects.filter(role_type='supplier').exists() and not Role.objects.filter(name='مورد').exists():
        Role.objects.create(name='مورد', role_type='supplier', is_system_role=True,
                            description='حساب مورد: يدخل بوابة الموردين فقط لطلب الخدمات ومتابعتها')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_supplier_portal'),
    ]

    operations = [
        migrations.RunPython(create_role, migrations.RunPython.noop),
    ]
