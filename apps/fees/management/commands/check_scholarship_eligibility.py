"""
fees/management/commands/check_scholarship_eligibility.py

Reads every active ScholarshipProgram with auto_award=True and creates
StudentScholarship records for students who qualify but don't have one yet.

Safe types for auto_award:
    NEED_BASED, SPECIAL_CIRCUMSTANCES, EMERGENCY_AID, GOVERNMENT_BURSARY

Merit types (ACADEMIC_MERIT, SPORTS_EXCELLENCE, etc.) are skipped even if
someone accidentally enables auto_award — the model's clean() prevents it,
but we guard here too.

Usage:
    python manage.py check_scholarship_eligibility
    python manage.py check_scholarship_eligibility --session <uuid>
    python manage.py check_scholarship_eligibility --program <code>
    python manage.py check_scholarship_eligibility --dry-run
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Auto-award scholarships to eligible students who are not yet enrolled.'

    # =========================================================================
    # ARGUMENTS
    # =========================================================================

    def add_arguments(self, parser):
        parser.add_argument(
            '--session',
            type=str,
            metavar='UUID',
            help='Restrict check to a specific academic session ID. '
                 'Defaults to the current active session.',
        )
        parser.add_argument(
            '--program',
            type=str,
            metavar='CODE',
            help='Restrict check to a single ScholarshipProgram by code.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would happen without creating any records.',
        )

    # =========================================================================
    # MAIN
    # =========================================================================

    def handle(self, *args, **options):
        dry_run    = options['dry_run']
        session_id = options.get('session')
        program_code = options.get('program')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no records will be created.\n'))

        # --- Resolve session ---
        session = self._resolve_session(session_id)
        self.stdout.write(f'Session: {session}\n')

        # --- Resolve programs ---
        programs = self._resolve_programs(program_code)
        if not programs.exists():
            self.stdout.write(self.style.WARNING('No eligible auto-award programs found.'))
            return

        self.stdout.write(f'Programs to check: {programs.count()}\n')

        total_awarded  = 0
        total_skipped  = 0
        total_ineligible = 0

        for program in programs:
            awarded, skipped, ineligible = self._process_program(
                program, session, dry_run
            )
            total_awarded    += awarded
            total_skipped    += skipped
            total_ineligible += ineligible

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone.  '
                f'Awarded: {total_awarded}  |  '
                f'Already enrolled (skipped): {total_skipped}  |  '
                f'Not eligible: {total_ineligible}'
            )
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _resolve_session(self, session_id):
        from academics.models import AcademicSession
        if session_id:
            try:
                return AcademicSession.objects.get(pk=session_id)
            except AcademicSession.DoesNotExist:
                raise CommandError(f'Academic session "{session_id}" not found.')

        session = AcademicSession.objects.filter(is_current=True).first()
        if not session:
            raise CommandError(
                'No current academic session found. '
                'Set one as current or pass --session <uuid>.'
            )
        return session

    def _resolve_programs(self, program_code):
        from fees.models import ScholarshipProgram

        qs = ScholarshipProgram.objects.filter(is_active=True, auto_award=True)

        if program_code:
            qs = qs.filter(code=program_code)
            if not qs.exists():
                raise CommandError(
                    f'No active auto-award program with code "{program_code}" found.'
                )

        return qs

    def _process_program(self, program, session, dry_run):
        """
        Award the scholarship to all eligible students not already enrolled.
        Returns (awarded_count, skipped_count, ineligible_count).
        """
        from fees.models import StudentScholarship

        self.stdout.write(f'\nChecking: {program.name} ({program.code})')

        # Safety guard — never auto-award merit types (belt-and-suspenders)
        MERIT_TYPES = {
            'ACADEMIC_MERIT', 'SPORTS_EXCELLENCE', 'ARTS_TALENT',
            'LEADERSHIP', 'COMMUNITY_SERVICE',
            'ALUMNI_SPONSORED', 'CORPORATE_SPONSORED',
        }
        if program.scholarship_type in MERIT_TYPES:
            self.stdout.write(
                self.style.WARNING(
                    f'  SKIPPED — {program.get_scholarship_type_display()} '
                    f'requires human approval. Disable auto_award on this program.'
                )
            )
            return 0, 0, 0

        # Check program capacity
        can_accept, reason = program.can_accept_new_recipient()
        if not can_accept:
            self.stdout.write(self.style.WARNING(f'  SKIPPED — {reason}'))
            return 0, 0, 0

        eligible_students = self._get_eligible_students(program, session)

        awarded    = 0
        skipped    = 0
        ineligible = 0

        for student in eligible_students:
            # Already has an active scholarship under this program?
            already = StudentScholarship.objects.filter(
                student=student,
                scholarship_program=program,
                status='ACTIVE',
            ).exists()

            if already:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  [DRY RUN] Would award to: {student.get_full_name()}'
                )
                awarded += 1
                continue

            try:
                with transaction.atomic():
                    StudentScholarship.objects.create(
                        student=student,
                        scholarship_program=program,
                        status='ACTIVE',
                        start_date=timezone.now().date(),
                        # Policy-based: amount is 0 — discount comes from program %
                        amount_awarded=Decimal('0.00'),
                        awarded_date=timezone.now().date(),
                        notes=(
                            f'Auto-awarded by check_scholarship_eligibility '
                            f'for session {session}.'
                        ),
                    )

                    # Update recipient count on the program
                    program.__class__.objects.filter(pk=program.pk).update(
                        current_recipient_count=program.current_recipient_count + 1
                    )

                self.stdout.write(
                    f'  Awarded to: {student.get_full_name()}'
                )
                awarded += 1

            except Exception as e:
                self.stderr.write(
                    f'  ERROR awarding to {student.get_full_name()}: {e}'
                )
                logger.error(
                    f'check_scholarship_eligibility: failed to award '
                    f'{program.code} to student {student.pk}: {e}',
                    exc_info=True,
                )

        self.stdout.write(
            f'  Result: awarded={awarded}, skipped={skipped}, ineligible={ineligible}'
        )
        return awarded, skipped, ineligible

    def _get_eligible_students(self, program, session):
        """
        Return students enrolled in `session` who qualify for `program`.
        Extend this method as you add more auto-awardable program types.
        """
        from students.models import Student
        from academics.models import StudentClassEnrollment

        # Base pool: all active students enrolled in this session
        enrolled_ids = StudentClassEnrollment.objects.filter(
            academic_session=session,
        ).values_list('student_id', flat=True)

        base_qs = Student.objects.filter(pk__in=enrolled_ids, status='ACTIVE')

        stype = program.scholarship_type

        # --- Need-based ---
        if stype == 'NEED_BASED':
            threshold = program.family_income_threshold
            if not threshold:
                self.stdout.write(
                    self.style.WARNING(
                        '  No family_income_threshold set on program — '
                        'cannot evaluate NEED_BASED eligibility. Skipping.'
                    )
                )
                return Student.objects.none()
            return base_qs.filter(family_income__lte=threshold)

        # --- Special circumstances ---
        if stype == 'SPECIAL_CIRCUMSTANCES':
            return base_qs.filter(has_special_circumstances=True)

        # --- Emergency aid ---
        if stype == 'EMERGENCY_AID':
            return base_qs.filter(flagged_for_emergency_aid=True)

        # --- Government bursary ---
        if stype == 'GOVERNMENT_BURSARY':
            return base_qs.filter(has_government_bursary=True)

        # --- Full / partial scholarship (catch-all — must have flag on student) ---
        if stype in ['FULL_SCHOLARSHIP', 'PARTIAL_SCHOLARSHIP']:
            return base_qs.filter(eligible_for_auto_scholarship=True)

        # Anything else — no auto-award logic defined
        self.stdout.write(
            self.style.WARNING(
                f'  No eligibility logic defined for type '
                f'"{program.get_scholarship_type_display()}". Skipping.'
            )
        )
        return Student.objects.none()