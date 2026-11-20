from django.db import migrations


def documents_shared_to_none(apps, schema_editor):
    """Documents is per user only (Paperless adapter). Migration 0007 once stored 'shared' for it.

    Nobody on a 'shared' value ever got a Paperless account, so the honest value is 'none':
    it matches what exists and no longer fails validation. An admin can grant per-user access later.
    """
    for model_name in ('User', 'Invitation'):
        model = apps.get_model('portal', model_name)
        field = 'service_access' if model_name == 'User' else 'services'
        for row in model.objects.all():
            values = dict(getattr(row, field) or {})
            if values.get('documents') == 'shared':
                values['documents'] = 'none'
                setattr(row, field, values)
                row.save(update_fields=[field])


class Migration(migrations.Migration):
    dependencies = [('portal', '0009_sitesettings_network_roles')]
    operations = [migrations.RunPython(documents_shared_to_none, migrations.RunPython.noop)]
