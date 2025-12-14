from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import StudentForm
from .models import Student, Guardian
from academics.models import AcademicLevel
from schoolara.managers import get_current_db
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.db import transaction
from formtools.wizard.views import SessionWizardView
from django.core.files.storage import FileSystemStorage
import os
from django.contrib.auth.decorators import login_required

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime
from django.db.models import Q

from .utils import get_student_statistics
from .forms import (
    STUDENT_WIZARD_FORMS,
    STUDENT_WIZARD_STEP_NAMES,
    StudentForm,
)

@login_required
def student_list(request):
    # Fixed: Use different variable name for queryset
    students_queryset = Student.objects.all().order_by('-created_at')
    academic_levels = AcademicLevel.objects.all()

    # Get statistics directly from utils
    stats = get_student_statistics()

    # Pagination
    paginator = Paginator(students_queryset, 10)
    page = request.GET.get('page', 1)

    try:
        students_page = paginator.page(page)
    except PageNotAnInteger:
        students_page = paginator.page(1)
    except EmptyPage:
        students_page = paginator.page(paginator.num_pages)

    context = {
        'students': students_page,
        'Student': Student,
        'academic_levels': academic_levels,
        'stats': stats,
    }
    return render(request, 'list.html', context)

class StudentWizardFileStorage(FileSystemStorage):
    """Custom storage for handling file uploads in wizard"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = os.path.join(self.location, 'wizard_temp')

class StudentCreateWizard(SessionWizardView):
    """
    Multi-step wizard for creating a student.

    NOTE:
    - Admission number is auto-generated internally
      (via generate_student_admission_number)
    - It is NOT exposed to any form or step
    """

    form_list = STUDENT_WIZARD_FORMS
    template_name = 'wizard.html'
    file_storage = StudentWizardFileStorage()

    def get_context_data(self, form, **kwargs):
        """Add step names and progress tracking"""
        context = super().get_context_data(form=form, **kwargs)

        total_steps = len(self.form_list)
        current_step = self.steps.step1  # 1-indexed

        context.update({
            'step_names': STUDENT_WIZARD_STEP_NAMES,
            'current_step_name': STUDENT_WIZARD_STEP_NAMES.get(
                self.steps.current, 'Step'
            ),
            'progress_percentage': (current_step / total_steps) * 100,
        })

        return context

    def get_form_kwargs(self, step=None):
        """Inject request/user only where needed"""
        kwargs = super().get_form_kwargs(step)

        if step == 'guardian_info':
            kwargs.update({
                'user': self.request.user,
                'request': self.request,
            })

        return kwargs

    @transaction.atomic
    def done(self, form_list, **kwargs):
        """Persist all wizard data and create student"""

        try:
            # Merge cleaned data from all steps
            form_data = {}
            for form in form_list:
                form_data.update(form.cleaned_data)

            # ------------------------------------------------------------------
            # Step 1: Create student instance (Basic Info form only)
            # ------------------------------------------------------------------
            basic_form = self.get_form_instance('basic_info')
            student = basic_form.save(commit=False)

            # ------------------------------------------------------------------
            # Step 2: Contact & logistics
            # ------------------------------------------------------------------
            student.personal_email = form_data.get('personal_email', '')
            student.phone_number = form_data.get('phone_number', '')
            student.home_address = form_data.get('home_address', '')
            student.mailing_address = form_data.get('mailing_address', '')
            student.district = form_data.get('district', '')
            student.region = form_data.get('region', '')
            student.country_of_residence = form_data.get(
                'country_of_residence', 'UG'
            )

            student.transportation_required = form_data.get(
                'transportation_required', False
            )
            student.transport_route = form_data.get('transport_route', '')
            student.pickup_point = form_data.get('pickup_point', '')
            student.pickup_time = form_data.get('pickup_time')

            # ------------------------------------------------------------------
            # Step 3: Academic information
            # ------------------------------------------------------------------
            student.admission_academic_level = form_data.get(
                'admission_academic_level'
            )
            student.current_academic_level = form_data.get(
                'current_academic_level'
            )
            student.enrollment_status = form_data.get(
                'enrollment_status', 'active'
            )

            student.previous_school = form_data.get('previous_school', '')
            student.previous_school_address = form_data.get(
                'previous_school_address', ''
            )
            student.previous_academic_level = form_data.get(
                'previous_academic_level'
            )
            student.transfer_certificate_number = form_data.get(
                'transfer_certificate_number', ''
            )
            student.previous_school_completion_date = form_data.get(
                'previous_school_completion_date'
            )
            student.transfer_reason = form_data.get('transfer_reason', '')

            # ------------------------------------------------------------------
            # Step 4: Health & special needs
            # ------------------------------------------------------------------
            student.health_condition = form_data.get('health_condition', '')
            student.blood_type = form_data.get('blood_type', 'Unknown')
            student.medical_conditions = form_data.get('medical_conditions', '')
            student.allergies = form_data.get('allergies', '')
            student.medications = form_data.get('medications', '')
            student.special_medical_needs = form_data.get('special_medical_needs', '')
            student.emergency_medical_contact = form_data.get('emergency_medical_contact', '')
            student.preferred_hospital = form_data.get('preferred_hospital', '')
            student.medical_insurance = form_data.get('medical_insurance', '')
            student.insurance_policy_number = form_data.get('insurance_policy_number', '')
            student.has_special_needs = form_data.get('has_special_needs', False)
            student.special_needs_description = form_data.get('special_needs_description', '')
            student.learning_disabilities = form_data.get('learning_disabilities', '')
            student.learning_accommodations = form_data.get('learning_accommodations', '')
            student.requires_special_diet = form_data.get('requires_special_diet', False)
            student.special_diet_details = form_data.get('special_diet_details', '')

            # ------------------------------------------------------------------
            # Save student (admission number generated automatically here)
            # ------------------------------------------------------------------
            student.save()

            # ------------------------------------------------------------------
            # Step 5: Guardian (existing or new)
            # ------------------------------------------------------------------
            guardian_option = form_data.get('guardian_option')
            relationship = form_data.get('relationship')

            if guardian_option == 'existing':
                guardian = form_data.get('existing_guardian')
            else:
                guardian = Guardian.objects.create(
                    first_name=form_data.get('guardian_first_name'),
                    last_name=form_data.get('guardian_last_name'),
                    primary_phone=form_data.get('guardian_phone'),
                    email=form_data.get('guardian_email', ''),
                    home_address=form_data.get('guardian_address', ''),
                    occupation=form_data.get('guardian_occupation', ''),
                    is_active=True,
                )

            student.guardians.add(guardian)

            # Optional pivot model
            try:
                from .models import StudentGuardian

                StudentGuardian.objects.create(
                    student=student,
                    guardian=guardian,
                    relationship=relationship,
                    is_primary=True,
                    is_financial_responsible=True,
                    can_pickup=True,
                )
            except ImportError:
                pass

            # ------------------------------------------------------------------
            # Success
            # ------------------------------------------------------------------
            messages.success(
                self.request,
                f"Student {student.get_full_name()} "
                f"(#{student.admission_number}) was created successfully!"
            )

            return redirect(
                'students:student_profile',
                pk=student.pk
            )

        except Exception as exc:
            messages.error(
                self.request,
                f"Error creating student: {exc}"
            )
            return redirect('students:student_list')

# View entry point
student_create = StudentCreateWizard.as_view()

def student_edit(request, pk):

    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            student = form.save()
            messages.success(request, f"Student {student} was updated successfully")
            return redirect("students:student_profile", pk=student.pk)
    else:
        form = StudentForm(instance=student)

    context = {
        'form': form,
        'title': 'Update Student',
    }

    return render(request, 'form.html', context)

def student_delete(request, pk):

    student = get_object_or_404(Student, pk=pk)

    if request.method == "POST":
        student.delete()
        messages.success(request, f"Student {student} was deleted successfully")
        return redirect("students:student_list")
    
def student_profile(request, pk):

    student = get_object_or_404(Student, pk=pk)

    context = {
        'student': student,
    }
    
    return render(request, "profile.html", context)

@login_required
def export_students_excel(request):
    """Export students to Excel with filters applied"""
    
    # Get filter parameters (same as student_search)
    query = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    level = request.GET.get('current_academic_level', '')
    status = request.GET.get('enrollment_status', '')
    min_age = request.GET.get('min_age', '')
    max_age = request.GET.get('max_age', '')
    
    # Apply filters
    students = Student.objects.all().order_by('admission_number')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(admission_number__icontains=term) |
                Q(current_academic_level__name__icontains=term)
            )
        students = students.filter(q_objects)
    
    if gender:
        students = students.filter(gender=gender)
    
    if level:
        students = students.filter(current_academic_level_id=level)
    
    if status:
        students = students.filter(enrollment_status=status)
    
    if min_age:
        try:
            from datetime import date, timedelta
            min_age = int(min_age)
            max_birth_date = date.today() - timedelta(days=min_age * 365.25)
            students = students.filter(date_of_birth__lte=max_birth_date)
        except ValueError:
            pass
    
    if max_age:
        try:
            from datetime import date, timedelta
            max_age = int(max_age)
            min_birth_date = date.today() - timedelta(days=(max_age + 1) * 365.25)
            students = students.filter(date_of_birth__gte=min_birth_date)
        except ValueError:
            pass
    
    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    
    # Define styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    border_style = Border(
        left=Side(style='thin', color='000000'),
        right=Side(style='thin', color='000000'),
        top=Side(style='thin', color='000000'),
        bottom=Side(style='thin', color='000000')
    )
    
    # Title row
    ws.merge_cells('A1:L1')
    title_cell = ws['A1']
    title_cell.value = "Student Directory Report"
    title_cell.font = Font(bold=True, size=16, color="4472C4")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Subtitle with date and filters
    ws.merge_cells('A2:L2')
    subtitle_cell = ws['A2']
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if gender:
        filter_text += f" | Gender: {dict(Student.GENDER_CHOICES).get(gender)}"
    if status:
        filter_text += f" | Status: {dict(Student.ENROLLMENT_STATUS_CHOICES).get(status)}"
    subtitle_cell.value = filter_text
    subtitle_cell.font = Font(size=10, italic=True)
    subtitle_cell.alignment = Alignment(horizontal="center")
    
    ws.append([])  # Empty row
    
    # Headers
    headers = [
        '#', 'Admission No.', 'Full Name', 'Gender', 'Date of Birth', 'Age',
        'Academic Level', 'Status', 'Phone', 'Email', 'District', 'Guardian Contact'
    ]
    
    ws.append(headers)
    header_row = ws[4]
    
    for cell in header_row:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border_style
    
    # Data rows
    for idx, student in enumerate(students, start=1):
        # Get primary guardian contact
        guardian_contact = ''
        if student.guardians.exists():
            guardian = student.guardians.first()
            guardian_contact = guardian.primary_phone if hasattr(guardian, 'primary_phone') else ''
        
        row_data = [
            idx,
            student.admission_number,
            student.get_full_name(),
            student.get_gender_display(),
            student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '',
            student.get_age(),
            str(student.current_academic_level) if student.current_academic_level else 'Not Assigned',
            student.get_enrollment_status_display(),
            student.phone_number or '',
            student.personal_email or '',
            student.district or '',
            guardian_contact
        ]
        
        ws.append(row_data)
        
        # Style data rows
        current_row = ws.max_row
        for cell in ws[current_row]:
            cell.border = border_style
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    
    # Adjust column widths
    column_widths = {
        'A': 5, 'B': 15, 'C': 25, 'D': 10, 'E': 12, 'F': 8,
        'G': 20, 'H': 12, 'I': 15, 'J': 25, 'K': 15, 'L': 15
    }
    
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Summary at bottom
    summary_row = ws.max_row + 2
    ws[f'A{summary_row}'] = 'Total Students:'
    ws[f'B{summary_row}'] = students.count()
    ws[f'A{summary_row}'].font = Font(bold=True)
    ws[f'B{summary_row}'].font = Font(bold=True)
    
    # Freeze panes (header row)
    ws.freeze_panes = 'A5'
    
    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"students_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@login_required
def export_students_pdf(request):
    """Export students to PDF with filters applied"""
    
    # Get filter parameters (same as Excel export)
    query = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    level = request.GET.get('current_academic_level', '')
    status = request.GET.get('enrollment_status', '')
    min_age = request.GET.get('min_age', '')
    max_age = request.GET.get('max_age', '')
    
    # Apply filters
    students = Student.objects.all().order_by('admission_number')
    
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(admission_number__icontains=term) |
                Q(current_academic_level__name__icontains=term)
            )
        students = students.filter(q_objects)
    
    if gender:
        students = students.filter(gender=gender)
    
    if level:
        students = students.filter(current_academic_level_id=level)
    
    if status:
        students = students.filter(enrollment_status=status)
    
    if min_age:
        try:
            from datetime import date, timedelta
            min_age = int(min_age)
            max_birth_date = date.today() - timedelta(days=min_age * 365.25)
            students = students.filter(date_of_birth__lte=max_birth_date)
        except ValueError:
            pass
    
    if max_age:
        try:
            from datetime import date, timedelta
            max_age = int(max_age)
            min_birth_date = date.today() - timedelta(days=(max_age + 1) * 365.25)
            students = students.filter(date_of_birth__gte=min_birth_date)
        except ValueError:
            pass
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=18,
    )
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#4472C4'),
        spaceAfter=12,
        alignment=TA_CENTER,
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=20,
        alignment=TA_CENTER,
    )
    
    # Title
    title = Paragraph("Student Directory Report", title_style)
    elements.append(title)
    
    # Subtitle with filters
    filter_text = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if query:
        filter_text += f" | Search: {query}"
    if gender:
        filter_text += f" | Gender: {dict(Student.GENDER_CHOICES).get(gender)}"
    if status:
        filter_text += f" | Status: {dict(Student.ENROLLMENT_STATUS_CHOICES).get(status)}"
    
    subtitle = Paragraph(filter_text, subtitle_style)
    elements.append(subtitle)
    elements.append(Spacer(1, 0.2*inch))
    
    # Table data
    data = [['#', 'Admission No.', 'Full Name', 'Gender', 'Age', 'Level', 'Status', 'Phone']]
    
    for idx, student in enumerate(students, start=1):
        row = [
            str(idx),
            student.admission_number,
            student.get_full_name()[:30],  # Truncate long names
            student.get_gender_display(),
            str(student.get_age()),
            str(student.current_academic_level)[:25] if student.current_academic_level else 'N/A',
            student.get_enrollment_status_display()[:15],
            student.phone_number[:15] if student.phone_number else ''
        ]
        data.append(row)
    
    # Create table
    table = Table(data, colWidths=[0.5*inch, 1*inch, 2*inch, 0.8*inch, 0.6*inch, 1.5*inch, 1*inch, 1*inch])
    
    # Table style
    table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Data rows
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # # column
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Age column
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    
    # Summary
    elements.append(Spacer(1, 0.3*inch))
    summary_text = f"<b>Total Students:</b> {students.count()}"
    summary = Paragraph(summary_text, styles['Normal'])
    elements.append(summary)
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF value
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    filename = f"students_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(pdf)
    
    return response