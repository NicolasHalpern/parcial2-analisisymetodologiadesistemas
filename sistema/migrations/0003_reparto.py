# Agrega lo necesario para el reparto: ubicación/turno del repartidor, pedidos y avisos.
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import sistema.models


class Migration(migrations.Migration):

    dependencies = [
        ('sistema', '0002_producto_repartidor'),
    ]

    operations = [
        migrations.AddField(
            model_name='repartidor',
            name='telefono',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='repartidor',
            name='disponible',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='repartidor',
            name='lat',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='repartidor',
            name='lng',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='repartidor',
            name='ultima_ubicacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='repartidor',
            name='color',
            field=models.CharField(default='#0d6efd', max_length=7),
        ),
        migrations.CreateModel(
            name='Pedido',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cliente_nombre', models.CharField(max_length=100)),
                ('cliente_telefono', models.CharField(max_length=30)),
                ('direccion', models.CharField(max_length=255)),
                ('lat', models.FloatField()),
                ('lng', models.FloatField()),
                ('detalle', models.TextField(blank=True, default='')),
                ('notas', models.CharField(blank=True, default='', max_length=255)),
                ('estado', models.CharField(choices=[('PREPARACION', 'En preparación'), ('EN_CAMINO', 'En camino'), ('ENTREGADO', 'Entregado'), ('CANCELADO', 'Cancelado')], default='PREPARACION', max_length=12)),
                ('orden_ruta', models.PositiveIntegerField(blank=True, null=True)),
                ('distancia_km', models.FloatField(blank=True, null=True)),
                ('hora_estimada', models.DateTimeField(blank=True, null=True)),
                ('tiempo_preparacion_min', models.PositiveIntegerField(default=15)),
                ('alerta_demora', models.BooleanField(default=False)),
                ('codigo', models.CharField(default=sistema.models.generar_codigo, max_length=8, unique=True)),
                ('creado', models.DateTimeField(default=django.utils.timezone.now)),
                ('salida', models.DateTimeField(blank=True, null=True)),
                ('entregado', models.DateTimeField(blank=True, null=True)),
                ('repartidor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pedidos', to='sistema.repartidor')),
            ],
            options={
                'ordering': ['-creado'],
            },
        ),
        migrations.CreateModel(
            name='Notificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mensaje', models.CharField(max_length=255)),
                ('tipo', models.CharField(choices=[('info', 'Info'), ('success', 'Éxito'), ('warning', 'Alerta'), ('danger', 'Peligro')], default='info', max_length=10)),
                ('para_cliente', models.BooleanField(default=False)),
                ('creada', models.DateTimeField(default=django.utils.timezone.now)),
                ('leida', models.BooleanField(default=False)),
                ('pedido', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones', to='sistema.pedido')),
            ],
            options={
                'ordering': ['-creada'],
            },
        ),
    ]
