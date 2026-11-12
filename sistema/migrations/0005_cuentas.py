import secrets

import django.db.models.deletion
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models

import sistema.models


def dar_token_a_repartidores(apps, schema_editor):
    """Cada repartidor que ya existía recibe su propia clave para el link del celular."""
    Repartidor = apps.get_model('sistema', 'Repartidor')
    for r in Repartidor.objects.all():
        r.token = secrets.token_urlsafe(16)
        r.save(update_fields=['token'])


def crear_admin(apps, schema_editor):
    """Usuario administrador del comercio: admin / 123."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    admin, _ = User.objects.get_or_create(username='admin')
    admin.password = make_password('123')
    admin.is_staff = True
    admin.is_superuser = True
    admin.is_active = True
    admin.first_name = admin.first_name or 'Administrador'
    admin.save()


class Migration(migrations.Migration):

    dependencies = [
        ('sistema', '0004_tienda'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='cliente',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='pedidos', to=settings.AUTH_USER_MODEL),
        ),
        # Token en 3 pasos: si se agregara directo como único, todos los repartidores
        # existentes recibirían el mismo valor y la migración fallaría.
        migrations.AddField(
            model_name='repartidor',
            name='token',
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(dar_token_a_repartidores, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='repartidor',
            name='token',
            field=models.CharField(default=sistema.models.generar_token, max_length=32, unique=True),
        ),
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telefono', models.CharField(max_length=30)),
                ('direccion', models.CharField(blank=True, default='', max_length=255)),
                ('lat', models.FloatField(blank=True, null=True)),
                ('lng', models.FloatField(blank=True, null=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                 related_name='cliente', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(crear_admin, migrations.RunPython.noop),
    ]
