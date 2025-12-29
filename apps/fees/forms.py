# fees/forms.py

"""
Fee Management Forms

Comprehensive form classes for:
- Student Accounts and Transactions
- Display Groups and Fee Categories
- Fee Structures and Items
- Invoices and Payments
- Scholarship Programs and Applications
- Discounts and Refunds

All forms include proper validation and user-friendly widgets
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q, Sum
from decimal import Decimal
import json
import logging

from .models import (
    StudentAccount,
    AccountTransaction,
    DisplayGroup,
    FeesCategory,
    FeesStructure,
    FeesStructureItem,
    FeeInvoice,
    FeeInvoiceItem,
    Payment,
    ScholarshipProgram,
    StudentScholarshipApplication,
    StudentScholarship,
    ScholarshipApplicationLog,
    FeesDiscount,
    DiscountApplication,
    Refund
)
from students.models import Student
from academics.models import AcademicLevel, Class, AcademicSession
from core.models import PaymentMethod, FiscalYear, FiscalPeriod

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT ACCOUNT FORMS
# =============================================================================

class StudentAccountForm(forms.ModelForm):
    """Form for creating/updating student accounts"""
    
    class Meta:
        model = StudentAccount
        fields = ['student', 'credit_limit', 'status']
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Maximum negative balance allowed'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active students only
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        self.fields['credit_limit'].required = False
    
    def clean_student(self):
        student = self.cleaned_data.get('student')
        
        # Check if account already exists for this student (when creating new)
        if not self.instance.pk and student:
            if StudentAccount.objects.filter(student=student).exists():
                raise ValidationError(
                    f'A financial account already exists for {student.get_full_name()}.'
                )
        
        return student


class AccountTransactionForm(forms.ModelForm):
    """Form for creating account transactions"""
    
    class Meta:
        model = AccountTransaction
        fields = [
            'student_account', 'transaction_type', 'amount',
            'description', 'reference_number', 'academic_session',
            'fiscal_period'
        ]
        widgets = {
            'student_account': forms.Select(attrs={'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Transaction description'
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional reference number'
            }),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active accounts
        self.fields['student_account'].queryset = StudentAccount.objects.filter(
            status='ACTIVE'
        ).select_related('student').order_by('student__first_name')
        
        # Filter open fiscal periods
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
            status='OPEN'
        ).order_by('-start_date')
        
        self.fields['reference_number'].required = False
        self.fields['academic_session'].required = False
        self.fields['fiscal_period'].required = False
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        
        if amount and amount <= 0:
            raise ValidationError('Amount must be greater than zero.')
        
        return amount


# =============================================================================
# DISPLAY GROUP FORMS
# =============================================================================

class DisplayGroupForm(forms.ModelForm):
    """Form for creating and editing display groups"""
    
    class Meta:
        model = DisplayGroup
        fields = [
            'name', 'description', 'display_order', 'color_code',
            'show_as_group', 'show_group_subtotal', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Display Group Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 1
            }),
            'color_code': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color',
                'placeholder': '#6f42c1'
            }),
            'show_as_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_group_subtotal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False


# =============================================================================
# FEE CATEGORY FORMS
# =============================================================================

class FeesCategoryForm(forms.ModelForm):
    """Form for creating and editing fee categories"""
    
    class Meta:
        model = FeesCategory
        fields = [
            'name', 'code', 'description', 'category_type',
            'is_recurring', 'frequency', 'applicability',
            'applicable_levels', 'display_group', 'display_order',
            'is_mandatory', 'is_refundable', 'allows_partial_payment',
            'is_taxable', 'default_tax_rate', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fee Name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'TUI001'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'category_type': forms.Select(attrs={'class': 'form-control'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'frequency': forms.Select(attrs={'class': 'form-control'}),
            'applicability': forms.Select(attrs={'class': 'form-control'}),
            'applicable_levels': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'display_group': forms.Select(attrs={'class': 'form-control'}),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 1
            }),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_refundable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allows_partial_payment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active display groups
        self.fields['display_group'].queryset = DisplayGroup.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')
        
        # Filter active academic levels
        self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('level_order')
        
        self.fields['description'].required = False
        self.fields['applicable_levels'].required = False
        self.fields['display_group'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate tax settings
        is_taxable = cleaned_data.get('is_taxable')
        default_tax_rate = cleaned_data.get('default_tax_rate')
        
        if is_taxable and not default_tax_rate:
            raise ValidationError({
                'default_tax_rate': 'Tax rate is required for taxable fees.'
            })
        
        return cleaned_data


# =============================================================================
# FEE STRUCTURE FORMS
# =============================================================================

class FeesStructureForm(forms.ModelForm):
    """Form for creating and editing fee structures"""
    
    class Meta:
        model = FeesStructure
        fields = [
            'name', 'description', 'structure_type',
            'applicable_sessions', 'academic_levels', 'applicable_classes',
            'boarding_type_filter', 'student_type_filter',
            'payment_terms_days', 'charges_late_fee',
            'late_fee_amount', 'late_fee_percentage', 'grace_period_days',
            'priority', 'is_active', 'effective_date', 'expiry_date'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Structure Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'structure_type': forms.Select(attrs={'class': 'form-control'}),
            'applicable_sessions': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'academic_levels': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'applicable_classes': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'boarding_type_filter': forms.Select(attrs={'class': 'form-control'}),
            'student_type_filter': forms.Select(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 30
            }),
            'charges_late_fee': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'late_fee_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'late_fee_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'grace_period_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 7
            }),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 100
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'effective_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active sessions
        self.fields['applicable_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Filter active academic levels
        self.fields['academic_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('level_order')
        
        # Filter active classes
        self.fields['applicable_classes'].queryset = Class.objects.filter(
            is_active=True
        ).order_by('name')
        
        self.fields['description'].required = False
        self.fields['applicable_classes'].required = False
        self.fields['expiry_date'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate date range
        effective_date = cleaned_data.get('effective_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        if effective_date and expiry_date and expiry_date <= effective_date:
            raise ValidationError({
                'expiry_date': 'Expiry date must be after effective date.'
            })
        
        # Validate late fee settings
        charges_late_fee = cleaned_data.get('charges_late_fee')
        late_fee_amount = cleaned_data.get('late_fee_amount')
        late_fee_percentage = cleaned_data.get('late_fee_percentage')
        
        if charges_late_fee and not (late_fee_amount or late_fee_percentage):
            raise ValidationError(
                'Please specify either late fee amount or percentage.'
            )
        
        return cleaned_data


class FeesStructureItemForm(forms.ModelForm):
    """Form for adding items to fee structures"""
    
    class Meta:
        model = FeesStructureItem
        fields = [
            'fee_structure', 'fee_category', 'amount',
            'tax_percentage', 'discount_percentage',
            'scholarship_eligible', 'max_scholarship_discount',
            'is_conditional', 'condition_description',
            'is_payable_in_installments', 'number_of_installments'
        ]
        widgets = {
            'fee_structure': forms.Select(attrs={'class': 'form-control'}),
            'fee_category': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'value': '0.00'
            }),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'value': '0.00'
            }),
            'scholarship_eligible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_scholarship_discount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'is_conditional': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'condition_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'is_payable_in_installments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'number_of_installments': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 1
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active fee structures
        self.fields['fee_structure'].queryset = FeesStructure.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Filter active fee categories
        self.fields['fee_category'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).order_by('name')
        
        self.fields['max_scholarship_discount'].required = False
        self.fields['condition_description'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate conditional settings
        is_conditional = cleaned_data.get('is_conditional')
        condition_description = cleaned_data.get('condition_description')
        
        if is_conditional and not condition_description:
            raise ValidationError({
                'condition_description': 'Condition description is required for conditional items.'
            })
        
        # Validate installment settings
        is_payable_in_installments = cleaned_data.get('is_payable_in_installments')
        number_of_installments = cleaned_data.get('number_of_installments')
        
        if is_payable_in_installments and number_of_installments < 2:
            raise ValidationError({
                'number_of_installments': 'Number of installments must be at least 2.'
            })
        
        return cleaned_data
    
# =============================================================================
# FEE INVOICE FORMS
# =============================================================================

class FeeInvoiceForm(forms.ModelForm):
    """Form for creating and editing fee invoices"""
    
    class Meta:
        model = FeeInvoice
        fields = [
            'student', 'academic_session', 'fiscal_period',
            'fee_structure', 'issue_date', 'due_date',
            'payment_terms', 'notes', 'internal_notes'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'fiscal_period': forms.Select(attrs={'class': 'form-control'}),
            'fee_structure': forms.Select(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'payment_terms': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Payment terms and conditions'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'internal_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        # Filter active sessions
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Filter open fiscal periods
        self.fields['fiscal_period'].queryset = FiscalPeriod.objects.filter(
            status='OPEN'
        ).order_by('-start_date')
        
        # Filter active fee structures
        self.fields['fee_structure'].queryset = FeesStructure.objects.filter(
            is_active=True
        ).order_by('name')
        
        self.fields['payment_terms'].required = False
        self.fields['notes'].required = False
        self.fields['internal_notes'].required = False
        
        # Set default dates
        self.fields['issue_date'].initial = timezone.now().date()
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate dates
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        
        if issue_date and due_date and due_date < issue_date:
            raise ValidationError({
                'due_date': 'Due date cannot be before issue date.'
            })
        
        # Validate fiscal period contains issue date
        fiscal_period = cleaned_data.get('fiscal_period')
        
        if issue_date and fiscal_period:
            if not (fiscal_period.start_date <= issue_date <= fiscal_period.end_date):
                raise ValidationError({
                    'fiscal_period': 'Issue date must fall within the selected fiscal period.'
                })
        
        return cleaned_data


class FeeInvoiceItemForm(forms.ModelForm):
    """Form for adding items to invoices"""
    
    class Meta:
        model = FeeInvoiceItem
        fields = [
            'invoice', 'fee_category', 'description',
            'quantity', 'unit_amount', 'tax_percentage',
            'discount_percentage'
        ]
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-control'}),
            'fee_category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional description override'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'value': '1.00'
            }),
            'unit_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'tax_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'value': '0.00'
            }),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'value': '0.00'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter draft invoices only
        self.fields['invoice'].queryset = FeeInvoice.objects.filter(
            status='DRAFT'
        ).order_by('-issue_date')
        
        # Filter active fee categories
        self.fields['fee_category'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).order_by('name')
        
        self.fields['description'].required = False


# =============================================================================
# PAYMENT FORMS
# =============================================================================

class PaymentForm(forms.ModelForm):
    """Form for recording student payments"""
    
    class Meta:
        model = Payment
        fields = [
            'invoice', 'student', 'amount', 'payment_date',
            'payment_method', 'reference_number', 'transaction_id',
            'bank_name', 'account_number', 'cheque_number', 'cheque_date',
            'mobile_money_provider', 'mobile_number',
            'paid_by_name', 'paid_by_phone', 'paid_by_email',
            'paid_by_relationship', 'remarks'
        ]
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-control'}),
            'student': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Payment reference number'
            }),
            'transaction_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Transaction ID'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Bank name'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Account number (last 4 digits)'
            }),
            'cheque_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Cheque number'
            }),
            'cheque_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'mobile_money_provider': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'MTN, Airtel, etc.'
            }),
            'mobile_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Mobile money number'
            }),
            'paid_by_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Name of person making payment'
            }),
            'paid_by_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone number'
            }),
            'paid_by_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email address'
            }),
            'paid_by_relationship': forms.Select(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter unpaid/partially paid invoices
        self.fields['invoice'].queryset = FeeInvoice.objects.filter(
            status__in=['PENDING', 'PARTIALLY_PAID', 'OVERDUE']
        ).order_by('-issue_date')
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        # Filter active payment methods
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Make optional fields
        self.fields['reference_number'].required = False
        self.fields['transaction_id'].required = False
        self.fields['bank_name'].required = False
        self.fields['account_number'].required = False
        self.fields['cheque_number'].required = False
        self.fields['cheque_date'].required = False
        self.fields['mobile_money_provider'].required = False
        self.fields['mobile_number'].required = False
        self.fields['paid_by_name'].required = False
        self.fields['paid_by_phone'].required = False
        self.fields['paid_by_email'].required = False
        self.fields['paid_by_relationship'].required = False
        self.fields['remarks'].required = False
        
        # Set default payment date
        self.fields['payment_date'].initial = timezone.now().date()
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate amount against invoice balance
        invoice = cleaned_data.get('invoice')
        amount = cleaned_data.get('amount')
        
        if invoice and amount:
            if amount > invoice.balance:
                self.add_error(
                    'amount',
                    f'Payment amount ({amount}) exceeds invoice balance ({invoice.balance}).'
                )
        
        # Validate cheque-specific fields
        payment_method = cleaned_data.get('payment_method')
        cheque_number = cleaned_data.get('cheque_number')
        
        if payment_method and 'CHEQUE' in payment_method.name.upper():
            if not cheque_number:
                raise ValidationError({
                    'cheque_number': 'Cheque number is required for cheque payments.'
                })
        
        # Validate mobile money fields
        if payment_method and 'MOBILE' in payment_method.name.upper():
            if not cleaned_data.get('mobile_money_provider'):
                raise ValidationError({
                    'mobile_money_provider': 'Mobile money provider is required.'
                })
            if not cleaned_data.get('mobile_number'):
                raise ValidationError({
                    'mobile_number': 'Mobile number is required for mobile money payments.'
                })
        
        return cleaned_data


class PaymentVerificationForm(forms.ModelForm):
    """Form for verifying payments"""
    
    class Meta:
        model = Payment
        fields = ['is_verified', 'verification_date']
        widgets = {
            'is_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'verification_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['verification_date'].initial = timezone.now().date()

# =============================================================================
# SCHOLARSHIP PROGRAM FORMS
# =============================================================================

class ScholarshipProgramForm(forms.ModelForm):
    """Form for creating and editing scholarship programs"""
    
    class Meta:
        model = ScholarshipProgram
        fields = [
            'name', 'code', 'scholarship_type', 'description',
            'discount_type', 'discount_percentage', 'fixed_discount_amount',
            'maximum_award_amount', 'applicable_fee_categories',
            'minimum_gpa', 'minimum_attendance_percentage',
            'family_income_threshold', 'applicable_levels',
            'total_budget_amount', 'maximum_recipients',
            'renewal_policy', 'maximum_duration_years',
            'application_start_date', 'application_end_date',
            'award_announcement_date', 'sponsor_name', 'sponsor_contact',
            'external_funding_source', 'is_active',
            'is_accepting_applications', 'valid_sessions'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Scholarship Program Name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SCHOL001'
            }),
            'scholarship_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4
            }),
            'discount_type': forms.Select(attrs={'class': 'form-control'}),
            'discount_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'fixed_discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'maximum_award_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'applicable_fee_categories': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'minimum_gpa': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'e.g., 3.5'
            }),
            'minimum_attendance_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'e.g., 85.00'
            }),
            'family_income_threshold': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'applicable_levels': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'total_budget_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'maximum_recipients': forms.NumberInput(attrs={
                'class': 'form-control'
            }),
            'renewal_policy': forms.Select(attrs={'class': 'form-control'}),
            'maximum_duration_years': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 1
            }),
            'application_start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'application_end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'award_announcement_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'sponsor_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Sponsor organization or individual'
            }),
            'sponsor_contact': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
            'external_funding_source': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_accepting_applications': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'valid_sessions': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active fee categories
        self.fields['applicable_fee_categories'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Filter active academic levels
        self.fields['applicable_levels'].queryset = AcademicLevel.objects.filter(
            is_active=True
        ).order_by('level_order')
        
        # Filter active sessions
        self.fields['valid_sessions'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Make optional fields
        for field in ['discount_percentage', 'fixed_discount_amount', 'maximum_award_amount',
                     'applicable_fee_categories', 'minimum_gpa', 'minimum_attendance_percentage',
                     'family_income_threshold', 'applicable_levels', 'total_budget_amount',
                     'maximum_recipients', 'application_start_date', 'application_end_date',
                     'award_announcement_date', 'sponsor_name', 'sponsor_contact',
                     'external_funding_source', 'valid_sessions']:
            self.fields[field].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate discount settings
        discount_type = cleaned_data.get('discount_type')
        discount_percentage = cleaned_data.get('discount_percentage')
        fixed_discount_amount = cleaned_data.get('fixed_discount_amount')
        
        if discount_type == 'PERCENTAGE' and not discount_percentage:
            raise ValidationError({
                'discount_percentage': 'Discount percentage is required for percentage-based scholarships.'
            })
        
        if discount_type == 'FIXED_AMOUNT' and not fixed_discount_amount:
            raise ValidationError({
                'fixed_discount_amount': 'Fixed amount is required for fixed amount scholarships.'
            })
        
        # Validate application dates
        start_date = cleaned_data.get('application_start_date')
        end_date = cleaned_data.get('application_end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'application_end_date': 'Application end date must be after start date.'
            })
        
        return cleaned_data


class StudentScholarshipApplicationForm(forms.ModelForm):
    """Form for students to apply for scholarships"""
    
    class Meta:
        model = StudentScholarshipApplication
        fields = [
            'student', 'scholarship_program', 'academic_session',
            'requested_amount', 'essay', 'family_income',
            'number_of_dependents', 'special_circumstances',
            'current_gpa', 'attendance_percentage'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'scholarship_program': forms.Select(attrs={'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'requested_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'essay': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Please explain why you deserve this scholarship...'
            }),
            'family_income': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Monthly family income'
            }),
            'number_of_dependents': forms.NumberInput(attrs={
                'class': 'form-control'
            }),
            'special_circumstances': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any special circumstances we should consider...'
            }),
            'current_gpa': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'attendance_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        # Filter active, accepting programs
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True,
            is_accepting_applications=True
        ).order_by('name')
        
        # Filter active sessions
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Make optional fields
        for field in ['requested_amount', 'essay', 'family_income', 'number_of_dependents',
                     'special_circumstances', 'current_gpa', 'attendance_percentage']:
            self.fields[field].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Check if student already has application for this program/session
        student = cleaned_data.get('student')
        program = cleaned_data.get('scholarship_program')
        session = cleaned_data.get('academic_session')
        
        if not self.instance.pk and student and program and session:
            existing = StudentScholarshipApplication.objects.filter(
                student=student,
                scholarship_program=program,
                academic_session=session
            ).exists()
            
            if existing:
                raise ValidationError(
                    'An application already exists for this student, program, and session.'
                )
        
        # Validate requested amount against maximum
        requested_amount = cleaned_data.get('requested_amount')
        program = cleaned_data.get('scholarship_program')
        
        if requested_amount and program and program.maximum_award_amount:
            if requested_amount > program.maximum_award_amount:
                raise ValidationError({
                    'requested_amount': f'Requested amount exceeds maximum award of {program.maximum_award_amount}.'
                })
        
        return cleaned_data


class ScholarshipApplicationReviewForm(forms.ModelForm):
    """Form for reviewing scholarship applications"""
    
    class Meta:
        model = StudentScholarshipApplication
        fields = ['status', 'approved_amount', 'decision_reason', 'review_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'approved_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'decision_reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'review_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit status choices to review-related
        self.fields['status'].choices = [
            ('UNDER_REVIEW', 'Under Review'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
            ('WAITLISTED', 'Waitlisted'),
        ]
        
        self.fields['approved_amount'].required = False
        self.fields['decision_reason'].required = False
        self.fields['review_notes'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Require approved amount for approved applications
        status = cleaned_data.get('status')
        approved_amount = cleaned_data.get('approved_amount')
        
        if status == 'APPROVED' and not approved_amount:
            raise ValidationError({
                'approved_amount': 'Approved amount is required for approved applications.'
            })
        
        return cleaned_data


class StudentScholarshipForm(forms.ModelForm):
    """Form for creating active student scholarships"""
    
    class Meta:
        model = StudentScholarship
        fields = [
            'student', 'scholarship_program', 'application',
            'amount_awarded', 'start_date', 'end_date',
            'distribution_method', 'amount_per_session',
            'amount_per_invoice', 'max_amount_per_session',
            'status', 'is_renewable', 'requires_renewal_verification',
            'notes'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'scholarship_program': forms.Select(attrs={'class': 'form-control'}),
            'application': forms.Select(attrs={'class': 'form-control'}),
            'amount_awarded': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'distribution_method': forms.Select(attrs={'class': 'form-control'}),
            'amount_per_session': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'amount_per_invoice': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'max_amount_per_session': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'is_renewable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_renewal_verification': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        # Filter active programs
        self.fields['scholarship_program'].queryset = ScholarshipProgram.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Filter approved applications
        self.fields['application'].queryset = StudentScholarshipApplication.objects.filter(
            status='APPROVED'
        ).order_by('-application_date')
        
        # Make optional fields
        for field in ['application', 'end_date', 'amount_per_session', 
                     'amount_per_invoice', 'max_amount_per_session', 'notes']:
            self.fields[field].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate date range
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        # Validate distribution settings
        distribution_method = cleaned_data.get('distribution_method')
        amount_per_session = cleaned_data.get('amount_per_session')
        amount_per_invoice = cleaned_data.get('amount_per_invoice')
        
        if distribution_method == 'EQUAL_PER_SESSION' and not amount_per_session:
            raise ValidationError({
                'amount_per_session': 'Amount per session is required for this distribution method.'
            })
        
        if distribution_method == 'EQUAL_PER_INVOICE' and not amount_per_invoice:
            raise ValidationError({
                'amount_per_invoice': 'Amount per invoice is required for this distribution method.'
            })
        
        return cleaned_data
    
# =============================================================================
# DISCOUNT FORMS
# =============================================================================

class FeesDiscountForm(forms.ModelForm):
    """Form for creating and editing fee discounts"""
    
    class Meta:
        model = FeesDiscount
        fields = [
            'name', 'code', 'discount_type', 'discount_value',
            'description', 'eligibility_criteria',
            'applicable_categories', 'applicable_structures',
            'academic_session', 'start_date', 'end_date',
            'max_usage_count', 'budget_limit',
            'auto_apply', 'requires_approval', 'priority',
            'can_combine_with_other_discounts', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Discount Name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'DISC001'
            }),
            'discount_type': forms.Select(attrs={'class': 'form-control'}),
            'discount_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'eligibility_criteria': forms.Select(attrs={'class': 'form-control'}),
            'applicable_categories': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'applicable_structures': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'size': '5'
            }),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'max_usage_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Leave blank for unlimited'
            }),
            'budget_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Leave blank for unlimited'
            }),
            'auto_apply': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'value': 100
            }),
            'can_combine_with_other_discounts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active fee categories
        self.fields['applicable_categories'].queryset = FeesCategory.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Filter active fee structures
        self.fields['applicable_structures'].queryset = FeesStructure.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Filter active sessions
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Make optional fields
        self.fields['description'].required = False
        self.fields['applicable_categories'].required = False
        self.fields['applicable_structures'].required = False
        self.fields['max_usage_count'].required = False
        self.fields['budget_limit'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate date range
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        # Validate discount value
        discount_type = cleaned_data.get('discount_type')
        discount_value = cleaned_data.get('discount_value')
        
        if discount_type == 'PERCENTAGE' and discount_value > 100:
            raise ValidationError({
                'discount_value': 'Percentage discount cannot exceed 100%.'
            })
        
        return cleaned_data


class DiscountApplicationForm(forms.ModelForm):
    """Form for applying discounts to invoices"""
    
    class Meta:
        model = DiscountApplication
        fields = ['discount', 'invoice', 'student', 'notes']
        widgets = {
            'discount': forms.Select(attrs={'class': 'form-control'}),
            'invoice': forms.Select(attrs={'class': 'form-control'}),
            'student': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active discounts
        self.fields['discount'].queryset = FeesDiscount.objects.filter(
            is_active=True,
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        ).order_by('name')
        
        # Filter draft/pending invoices
        self.fields['invoice'].queryset = FeeInvoice.objects.filter(
            status__in=['DRAFT', 'PENDING', 'PARTIALLY_PAID']
        ).order_by('-issue_date')
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status='ACTIVE'
        ).order_by('first_name', 'last_name')
        
        self.fields['notes'].required = False


# =============================================================================
# REFUND FORMS
# =============================================================================

class RefundForm(forms.ModelForm):
    """Form for creating refund requests"""
    
    class Meta:
        model = Refund
        fields = [
            'student', 'refund_type', 'amount', 'reason',
            'invoice', 'payment', 'academic_session',
            'payment_method', 'supporting_documents'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'refund_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Please explain the reason for this refund...'
            }),
            'invoice': forms.Select(attrs={'class': 'form-control'}),
            'payment': forms.Select(attrs={'class': 'form-control'}),
            'academic_session': forms.Select(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'supporting_documents': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'List supporting documents or upload references'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter active students
        self.fields['student'].queryset = Student.objects.filter(
            enrollment_status__in=['ACTIVE', 'WITHDRAWN', 'TRANSFERRED']
        ).order_by('first_name', 'last_name')
        
        # Filter sessions
        self.fields['academic_session'].queryset = AcademicSession.objects.filter(
            is_active=True
        ).order_by('-start_date')
        
        # Filter active payment methods
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by('name')
        
        # Make optional fields
        self.fields['invoice'].required = False
        self.fields['payment'].required = False
        self.fields['academic_session'].required = False
        self.fields['supporting_documents'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate amount
        amount = cleaned_data.get('amount')
        student = cleaned_data.get('student')
        
        if amount and student:
            try:
                account = StudentAccount.objects.get(student=student)
                # For overpayment refunds, check account has sufficient credit
                if cleaned_data.get('refund_type') == 'OVERPAYMENT':
                    if account.current_balance <= 0:
                        raise ValidationError({
                            'amount': 'Student account has no credit balance for refund.'
                        })
                    if amount > account.current_balance:
                        raise ValidationError({
                            'amount': f'Refund amount exceeds account credit balance of {account.current_balance}.'
                        })
            except StudentAccount.DoesNotExist:
                pass
        
        return cleaned_data


class RefundApprovalForm(forms.ModelForm):
    """Form for approving/rejecting refund requests"""
    
    class Meta:
        model = Refund
        fields = ['status', 'approved_amount', 'review_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'approved_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'review_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit status choices
        self.fields['status'].choices = [
            ('UNDER_REVIEW', 'Under Review'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
        ]
        
        self.fields['approved_amount'].required = False
        self.fields['review_notes'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        
        status = cleaned_data.get('status')
        approved_amount = cleaned_data.get('approved_amount')
        
        if status == 'APPROVED' and not approved_amount:
            raise ValidationError({
                'approved_amount': 'Approved amount is required for approved refunds.'
            })
        
        if status == 'REJECTED' and not cleaned_data.get('review_notes'):
            raise ValidationError({
                'review_notes': 'Please provide a reason for rejection.'
            })
        
        return cleaned_data


# =============================================================================
# BULK OPERATION FORMS
# =============================================================================

class BulkInvoiceGenerationForm(forms.Form):
    """Form for generating invoices in bulk"""
    
    academic_session = forms.ModelChoiceField(
        queryset=AcademicSession.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        label="Academic Session"
    )
    
    fee_structure = forms.ModelChoiceField(
        queryset=FeesStructure.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        label="Fee Structure"
    )
    
    student_filter = forms.ChoiceField(
        choices=[
            ('ALL', 'All Active Students'),
            ('BY_LEVEL', 'By Academic Level'),
            ('BY_CLASS', 'By Class'),
            ('BY_BOARDING', 'By Boarding Status'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True,
        initial='ALL',
        label="Filter Students"
    )
    
    academic_level = forms.ModelChoiceField(
        queryset=AcademicLevel.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        label="Academic Level"
    )
    
    student_class = forms.ModelChoiceField(
        queryset=Class.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        label="Class"
    )
    
    issue_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        initial=timezone.now().date,
        required=True,
        label="Issue Date"
    )
    
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        required=True,
        label="Due Date"
    )
    
    auto_apply_scholarships = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        required=False,
        initial=True,
        label="Auto-apply Active Scholarships"
    )
    
    auto_apply_discounts = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        required=False,
        initial=True,
        label="Auto-apply Eligible Discounts"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate dates
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        
        if issue_date and due_date and due_date < issue_date:
            raise ValidationError({
                'due_date': 'Due date cannot be before issue date.'
            })
        
        return cleaned_data


class BulkPaymentReconciliationForm(forms.Form):
    """Form for bulk payment reconciliation"""
    
    payment_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    action = forms.ChoiceField(
        choices=[
            ('VERIFY', 'Verify Selected Payments'),
            ('UNVERIFY', 'Unverify Selected Payments'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True
    )


class BulkScholarshipApplicationForm(forms.Form):
    """Form for bulk scholarship application to invoices"""
    
    scholarship = forms.ModelChoiceField(
        queryset=StudentScholarship.objects.filter(status='ACTIVE'),
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        label="Scholarship"
    )
    
    invoice_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    apply_method = forms.ChoiceField(
        choices=[
            ('AUTO', 'Apply Based on Distribution Method'),
            ('EQUAL', 'Apply Equal Amount to All'),
            ('PROPORTIONAL', 'Apply Proportionally to Invoice Amounts'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True,
        initial='AUTO'
    )