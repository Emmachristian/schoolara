# apps/students/migrations/0006_remove_old_guardians_table.py

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0005_transition_guardians_to_through_model'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS students_student_guardians;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]