from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0008_notice_company'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notice',
            name='supplier',
        ),
        migrations.RenameField(
            model_name='notice',
            old_name='company',
            new_name='supplier',
        ),
        migrations.AlterField(
            model_name='notice',
            name='supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='notices', to='portal.supplier'),
        ),
    ]
