"""Seed the AppState singleton and enforce unique non-empty lower(email)."""

from django.db import migrations


def create_app_state(apps, schema_editor):
    AppState = apps.get_model("core", "AppState")
    AppState.objects.get_or_create(pk=1)


def remove_app_state(apps, schema_editor):
    AppState = apps.get_model("core", "AppState")
    AppState.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_app_state, remove_app_state),
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_lower_uniq "
                "ON auth_user (LOWER(email)) WHERE email <> '';"
            ),
            reverse_sql="DROP INDEX IF EXISTS auth_user_email_lower_uniq;",
        ),
    ]
