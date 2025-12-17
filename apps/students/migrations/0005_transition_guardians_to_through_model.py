# apps/students/migrations/0005_transition_guardians_to_through_model.py

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


def migrate_existing_guardian_relationships(apps, schema_editor):
    """
    Migrate data from the old student_guardians M2M table 
    to the new StudentGuardian through model
    """
    Student = apps.get_model('students', 'Student')
    Guardian = apps.get_model('students', 'Guardian')
    StudentGuardian = apps.get_model('students', 'StudentGuardian')
    
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("""
                SELECT student_id, guardian_id 
                FROM students_student_guardians
            """)
            
            relationships = cursor.fetchall()
            
            for student_id, guardian_id in relationships:
                try:
                    StudentGuardian.objects.using(db_alias).create(
                        student_id=student_id,
                        guardian_id=guardian_id,
                        relationship='Guardian',
                        is_primary=False,
                        is_financial_responsible=True,
                        can_pickup=True,
                        can_authorize_medical=False,
                        emergency_contact_priority=999,
                    )
                except Exception as e:
                    print(f"Error migrating relationship {student_id}-{guardian_id}: {e}")
                    
        except Exception as e:
            print(f"No existing guardian relationships to migrate: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0004_boardingenrollment_dormitory_studentclassenrollment_and_more'),
    ]

    operations = [
        # Step 1: Create the StudentGuardian through model
        migrations.CreateModel(
            name='StudentGuardian',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Updated At')),
                ('created_by_id', models.CharField(blank=True, db_index=True, max_length=50, null=True, verbose_name='Created By ID')),
                ('updated_by_id', models.CharField(blank=True, db_index=True, max_length=50, null=True, verbose_name='Updated By ID')),
                ('created_from_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='Created From IP')),
                ('updated_from_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='Updated From IP')),
                ('change_reason', models.CharField(blank=True, max_length=255, null=True, verbose_name='Change Reason')),
                ('relationship', models.CharField(
                    choices=[
                        ('Father', 'Father'),
                        ('Mother', 'Mother'),
                        ('Step_Father', 'Step Father'),
                        ('Step_Mother', 'Step Mother'),
                        ('Foster_Father', 'Foster Father'),
                        ('Foster_Mother', 'Foster Mother'),
                        ('Grandfather', 'Grandfather'),
                        ('Grandmother', 'Grandmother'),
                        ('Uncle', 'Uncle'),
                        ('Aunt', 'Aunt'),
                        ('Brother', 'Brother'),
                        ('Sister', 'Sister'),
                        ('Cousin', 'Cousin'),
                        ('Guardian', 'Legal Guardian'),
                        ('Sponsor', 'Sponsor'),
                        ('Friend', 'Family Friend'),
                        ('Other', 'Other'),
                    ],
                    max_length=20,
                    verbose_name='Relationship'
                )),
                ('is_primary', models.BooleanField(default=False, verbose_name='Primary Guardian')),
                ('is_financial_responsible', models.BooleanField(default=False, verbose_name='Financial Responsibility')),
                ('can_pickup', models.BooleanField(default=True, verbose_name='Can Pickup Student')),
                ('can_authorize_medical', models.BooleanField(default=False, verbose_name='Can Authorize Medical Treatment')),
                ('emergency_contact_priority', models.PositiveSmallIntegerField(default=999, help_text='Lower number = higher priority', verbose_name='Emergency Contact Priority')),
                ('has_custody', models.BooleanField(default=False, verbose_name='Has Legal Custody')),
                ('custody_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name='Custody Percentage')),
                ('receives_academic_reports', models.BooleanField(default=True, verbose_name='Receives Academic Reports')),
                ('receives_financial_statements', models.BooleanField(default=True, verbose_name='Receives Financial Statements')),
                ('receives_emergency_notifications', models.BooleanField(default=True, verbose_name='Receives Emergency Notifications')),
                ('is_active', models.BooleanField(default=True, verbose_name='Is Active')),
                ('relationship_start_date', models.DateField(default=django.utils.timezone.now, verbose_name='Relationship Start Date')),
                ('relationship_end_date', models.DateField(blank=True, null=True, verbose_name='Relationship End Date')),
                ('guardian', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_relationships', to='students.guardian', verbose_name='Guardian')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guardian_relationships', to='students.student', verbose_name='Student')),
            ],
            options={
                'verbose_name': 'Student Guardian Relationship',
                'verbose_name_plural': 'Student Guardian Relationships',
                'ordering': ['emergency_contact_priority', 'relationship'],
            },
        ),
        
        # Step 2: Add indexes
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['student', 'is_active'], name='students_sg_st_act_idx'),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['guardian', 'is_active'], name='students_sg_gu_act_idx'),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['is_primary'], name='students_sg_prim_idx'),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['emergency_contact_priority'], name='students_sg_emer_idx'),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(fields=['is_financial_responsible'], name='students_sg_fina_idx'),
        ),
        
        # Step 3: Add unique constraint
        migrations.AlterUniqueTogether(
            name='studentguardian',
            unique_together={('student', 'guardian')},
        ),
        
        # Step 4: Migrate existing data
        migrations.RunPython(
            code=migrate_existing_guardian_relationships,
            reverse_code=migrations.RunPython.noop,
        ),
        
        # Step 5: Remove old guardians field
        migrations.RemoveField(
            model_name='student',
            name='guardians',
        ),
        
        # Step 6: Add new guardians field with through model
        migrations.AddField(
            model_name='student',
            name='guardians',
            field=models.ManyToManyField(
                blank=True,
                related_name='students',
                through='students.StudentGuardian',
                through_fields=('student', 'guardian'),
                to='students.guardian'
            ),
        ),
    ]