# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-05-31 06:50
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('terminator', '0019_move_summary_data_to_conceptinlanguage'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='summarymessage',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='summarymessage',
            name='concept',
        ),
        migrations.RemoveField(
            model_name='summarymessage',
            name='language',
        ),
        migrations.DeleteModel(
            name='SummaryMessage',
        ),
    ]
