# core/management/commands/diagnose_scholarships.py

"""
Django Management Command: Diagnose Scholarship Application Issues

Usage:
    python manage.py diagnose_scholarships --student-id=123 --issue-date=2024-03-15

This command will:
1. Show all scholarships for the student
2. Check which scholarships are active for the given issue date
3. Explain why scholarships are/aren't being applied
4. Test the actual discount calculation logic
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from datetime import datetime
from decimal import Decimal

class Command(BaseCommand):
    help = 'Diagnose why scholarships are not being applied to invoices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--student-id',
            type=str,
            required=True,
            help='Student ID (admission_number or pk)'
        )
        parser.add_argument(
            '--issue-date',
            type=str,
            required=True,
            help='Invoice issue date (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--session-id',
            type=str,
            help='Academic session ID (optional)'
        )

    def handle(self, *args, **options):
        from students.models import Student
        from fees.models import StudentScholarship
        from django.utils import timezone
        
        student_id = options['student_id']
        issue_date_str = options['issue_date']
        
        # Parse issue date
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
        except ValueError:
            self.stdout.write(self.style.ERROR(
                f"Invalid date format: {issue_date_str}. Use YYYY-MM-DD"
            ))
            return
        
        # Find student
        try:
            # Try admission number first
            student = Student.objects.get(admission_number=student_id)
        except Student.DoesNotExist:
            # Try as UUID pk
            try:
                student = Student.objects.get(pk=student_id)
            except (Student.DoesNotExist, ValueError):
                self.stdout.write(self.style.ERROR(
                    f"Student not found: {student_id}\n"
                    f"Please use the student's admission number (e.g., '24/ANPS/0177')"
                ))
                return
        except Student.MultipleObjectsReturned:
            self.stdout.write(self.style.ERROR(
                f"Multiple students found with admission number: {student_id}"
            ))
            return
        
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*80}\n"
            f"SCHOLARSHIP DIAGNOSIS FOR: {student.get_full_name()}\n"
            f"Student ID: {student.admission_number}\n"
            f"Invoice Issue Date: {issue_date}\n"
            f"{'='*80}\n"
        ))
        
        # =====================================================================
        # STEP 1: Show ALL scholarships for this student
        # =====================================================================
        
        all_scholarships = StudentScholarship.objects.filter(
            student=student
        ).select_related('scholarship_program').order_by('-awarded_date')
        
        self.stdout.write(self.style.WARNING(
            f"\n📋 ALL SCHOLARSHIPS FOR THIS STUDENT ({all_scholarships.count()}):\n"
        ))
        
        if not all_scholarships.exists():
            self.stdout.write(self.style.ERROR(
                "   ❌ NO SCHOLARSHIPS FOUND FOR THIS STUDENT\n"
                "   \n"
                "   Possible reasons:\n"
                "   1. Student has never been awarded a scholarship\n"
                "   2. Wrong student ID\n"
                "   \n"
                "   ACTION: Check admin panel → Fees → Student Scholarships\n"
            ))
            return
        
        for idx, scholarship in enumerate(all_scholarships, 1):
            program = scholarship.scholarship_program
            
            self.stdout.write(
                f"\n   {idx}. {program.name}\n"
                f"      Program Type: {program.get_program_type_display()}\n"
                f"      Discount Type: {program.get_discount_type_display()}\n"
                f"      Status: {scholarship.get_status_display()}\n"
                f"      Start Date: {scholarship.start_date}\n"
                f"      End Date: {scholarship.end_date or 'No end date'}\n"
                f"      Amount Awarded: {scholarship.amount_awarded:,.2f}\n"
                f"      Amount Used: {scholarship.total_amount_used:,.2f}\n"
            )
            
            if scholarship.use_category_specific_discounts:
                self.stdout.write(
                    f"      Category-Specific: YES\n"
                    f"      Categories: {list(scholarship.category_discounts.keys())}\n"
                )
            else:
                if program.discount_type == 'PERCENTAGE':
                    self.stdout.write(
                        f"      Global Discount: {program.discount_percentage}%\n"
                    )
                elif program.discount_type == 'FIXED_AMOUNT':
                    self.stdout.write(
                        f"      Fixed Amount: {program.fixed_discount_amount:,.2f}\n"
                    )
                elif program.discount_type == 'FULL_WAIVER':
                    self.stdout.write(
                        f"      Full Waiver: 100%\n"
                    )
        
        # =====================================================================
        # STEP 2: Check which scholarships SHOULD be active for issue_date
        # =====================================================================
        
        self.stdout.write(self.style.WARNING(
            f"\n\n🔍 FILTERING FOR ISSUE DATE: {issue_date}\n"
        ))
        
        # Replicate the exact query from _auto_apply_scholarships
        active_scholarships = StudentScholarship.objects.filter(
            student=student,
            status='ACTIVE',
            start_date__lte=issue_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=issue_date)
        ).select_related('scholarship_program')
        
        self.stdout.write(
            f"\n   Query Filters:\n"
            f"   - status = 'ACTIVE'\n"
            f"   - start_date <= {issue_date}\n"
            f"   - end_date IS NULL OR end_date >= {issue_date}\n"
            f"\n   Result: {active_scholarships.count()} scholarship(s) match\n"
        )
        
        if active_scholarships.count() == 0:
            self.stdout.write(self.style.ERROR(
                "\n   ❌ NO ACTIVE SCHOLARSHIPS FOR THIS DATE\n"
            ))
            
            # Diagnose why each scholarship is excluded
            for scholarship in all_scholarships:
                reasons = []
                
                if scholarship.status != 'ACTIVE':
                    reasons.append(f"Status is {scholarship.status} (not ACTIVE)")
                
                if scholarship.start_date > issue_date:
                    reasons.append(
                        f"Start date {scholarship.start_date} is after issue date {issue_date}"
                    )
                
                if scholarship.end_date and scholarship.end_date < issue_date:
                    reasons.append(
                        f"End date {scholarship.end_date} is before issue date {issue_date}"
                    )
                
                if reasons:
                    self.stdout.write(
                        f"\n   {scholarship.scholarship_program.name}:\n"
                    )
                    for reason in reasons:
                        self.stdout.write(f"      ❌ {reason}\n")
            
            self.stdout.write(self.style.WARNING(
                "\n   ACTION REQUIRED:\n"
                "   1. Check scholarship status (must be ACTIVE)\n"
                "   2. Check start_date (must be <= issue_date)\n"
                "   3. Check end_date (must be NULL or >= issue_date)\n"
                "   \n"
                "   Fix in: Admin → Fees → Student Scholarships\n"
            ))
            return
        
        # =====================================================================
        # STEP 3: Test discount calculation for active scholarships
        # =====================================================================
        
        self.stdout.write(self.style.SUCCESS(
            f"\n\n✅ ACTIVE SCHOLARSHIPS ({active_scholarships.count()}):\n"
        ))
        
        test_amount = Decimal('1000000.00')  # Test with 1M UGX
        
        for idx, scholarship in enumerate(active_scholarships, 1):
            program = scholarship.scholarship_program
            
            self.stdout.write(
                f"\n   {idx}. {program.name}\n"
                f"      Program Type: {program.get_program_type_display()}\n"
                f"      Discount Type: {program.get_discount_type_display()}\n"
            )
            
            # Calculate what discount would be applied
            if scholarship.use_category_specific_discounts:
                self.stdout.write(
                    f"      Mode: CATEGORY-SPECIFIC\n"
                    f"      Categories configured:\n"
                )
                for cat_code, config in scholarship.category_discounts.items():
                    disc_type = config.get('type')
                    disc_value = config.get('value', 0)
                    
                    # Calculate discount for this category
                    if disc_type == 'percentage':
                        cat_discount = test_amount * Decimal(str(disc_value)) / Decimal('100')
                        self.stdout.write(
                            f"         - {cat_code}: {disc_value}% = {cat_discount:,.2f} UGX\n"
                        )
                    elif disc_type == 'fixed_amount':
                        self.stdout.write(
                            f"         - {cat_code}: {disc_value:,.2f} UGX per invoice\n"
                        )
                    elif disc_type == 'full_waiver':
                        self.stdout.write(
                            f"         - {cat_code}: 100% waiver = {test_amount:,.2f} UGX\n"
                        )
                    elif disc_type == 'none':
                        self.stdout.write(
                            f"         - {cat_code}: No discount\n"
                        )
            
            else:
                # Global discount
                if program.discount_type == 'PERCENTAGE':
                    discount = test_amount * program.discount_percentage / Decimal('100')
                    self.stdout.write(
                        f"      Global Discount: {program.discount_percentage}%\n"
                        f"      Test: {test_amount:,.2f} × {program.discount_percentage}% = {discount:,.2f} UGX\n"
                    )
                
                elif program.discount_type == 'FIXED_AMOUNT':
                    remaining = scholarship.get_remaining_balance()
                    self.stdout.write(
                        f"      Fixed Amount Scholarship\n"
                        f"      Remaining Balance: {remaining:,.2f if remaining else 'N/A'} UGX\n"
                    )
                    
                    if remaining and remaining > 0:
                        discount = min(remaining, test_amount)
                        self.stdout.write(
                            f"      Test: min({remaining:,.2f}, {test_amount:,.2f}) = {discount:,.2f} UGX\n"
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f"      ❌ BUDGET EXHAUSTED - No discount will be applied!\n"
                            )
                        )
                
                elif program.discount_type == 'FULL_WAIVER':
                    self.stdout.write(
                        f"      Full Waiver: 100%\n"
                        f"      Test: {test_amount:,.2f} × 100% = {test_amount:,.2f} UGX\n"
                    )
        
        # =====================================================================
        # STEP 4: Summary and recommendations
        # =====================================================================
        
        self.stdout.write(self.style.SUCCESS(
            f"\n\n{'='*80}\n"
            f"DIAGNOSIS SUMMARY\n"
            f"{'='*80}\n"
        ))
        
        if active_scholarships.count() > 0:
            self.stdout.write(self.style.SUCCESS(
                f"✅ {active_scholarships.count()} scholarship(s) should be applied\n"
                f"\n"
                f"If scholarships are still not being applied during invoice generation:\n"
                f"\n"
                f"1. Check if auto_apply_scholarships is enabled in the form\n"
                f"2. Check invoice generator logs for errors\n"
                f"3. Verify fee categories in invoice match scholarship categories\n"
                f"4. For budget-based scholarships, ensure sufficient balance\n"
                f"\n"
                f"To test actual invoice generation:\n"
                f"   python manage.py shell\n"
                f"   >>> from fees.invoice_generators import UnifiedStudentInvoiceGenerator\n"
                f"   >>> from academics.models import StudentClassEnrollment\n"
                f"   >>> enrollment = StudentClassEnrollment.objects.filter(\n"
                f"   ...     student_id={student.pk},\n"
                f"   ...     is_active=True\n"
                f"   ... ).first()\n"
                f"   >>> invoice = UnifiedStudentInvoiceGenerator.generate(\n"
                f"   ...     enrollment,\n"
                f"   ...     issue_date='{issue_date}',\n"
                f"   ...     auto_apply_scholarships=True,\n"
                f"   ...     force=True\n"
                f"   ... )\n"
                f"   >>> print(invoice.scholarship_discount_amount)\n"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"❌ No scholarships will be applied\n"
                f"\n"
                f"See details above for why each scholarship is excluded.\n"
            ))
        
        self.stdout.write(f"\n{'='*80}\n")