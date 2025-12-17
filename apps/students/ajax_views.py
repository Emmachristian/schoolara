# students/ajax_views.py

from .models import Student, Guardian, StudentGuardian, Dormitory, BoardingEnrollment
import json
import base64
import os
from datetime import date, timedelta
from django.db.models import Q, Count, F
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# STUDENT PROFILE PICTURE UPDATE
# =============================================================================

@csrf_exempt
def update_student_profile_picture(request):
    """
    AJAX endpoint to update student profile picture via base64 image data
    """
    try:
        # Parse the JSON body
        data = json.loads(request.body)

        student_id = data.get("student_id")
        image_data = data.get("image")

        if not student_id or not image_data:
            return JsonResponse(
                {"success": False, "message": "Invalid data."},
                status=400
            )
        
        # Find the student by ID (UUID)
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Student not found."},
                status=404  
            )
        
        extension = None

        # Handle base64 prefix and determine extension
        if image_data.startswith("data:image/jpeg;base64,"):
            image_data = image_data[len("data:image/jpeg;base64,"):]
            extension = ".jpg"
        elif image_data.startswith("data:image/png;base64,"):
            image_data = image_data[len("data:image/png;base64,"):]
            extension = ".png"
        else:
            return JsonResponse(
                {"success": False, "message": "Unsupported image format. Only JPG and PNG are allowed"},
                status=400  
            )
        
        # Decode base64 string
        try:
            image_data_decoded = base64.b64decode(image_data)
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid image data."},
                status=400  
            )   

        # Generate the file name
        file_name = f"{student.id}{extension}" 

        # Delete old photo file if exists 
        if student.photo:
            old_file_path = student.photo.path
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception as e:
                    logger.warning(f"Could not delete old file: {e}")

        # Wrap decoded bytes in ContentFile and save to ImageField
        profile_picture = ContentFile(image_data_decoded)
        student.photo.save(file_name, profile_picture, save=True)

        # Redirect back to student profile
        redirect_url = reverse("students:student_profile", args=[student.id])

        return JsonResponse(
            {"success": True, "message": "Profile picture updated successfully", "redirect_url": redirect_url}
        )
    
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400 
        )
    
    except Exception as e:
        logger.error(f"Error updating student profile picture: {e}")
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"},
            status=500  
        )


# =============================================================================
# STUDENT SEARCH
# =============================================================================

def student_search(request):
    """
    AJAX view to return filtered students as JSON with statistics.
    Supports pagination OR returning all results when page='all'
    """
    query = request.GET.get('q', '').strip()
    gender = request.GET.get('gender', '')
    level = request.GET.get('current_academic_level', '')
    status = request.GET.get('enrollment_status', '')
    min_age = request.GET.get('min_age', '')
    max_age = request.GET.get('max_age', '')
    has_special_needs = request.GET.get('has_special_needs', '')
    transportation_required = request.GET.get('transportation_required', '')
    page = request.GET.get('page', 1)

    students = Student.objects.all().select_related('current_academic_level').order_by('-created_at')

    # Apply text search filter
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(admission_number__icontains=term) |
                Q(current_academic_level__name__icontains=term) |
                Q(personal_email__icontains=term) |
                Q(phone_number__icontains=term)
            )
        students = students.filter(q_objects)

    # Apply filters
    if gender:
        students = students.filter(gender=gender)

    if level:
        students = students.filter(current_academic_level_id=level)

    if status:
        students = students.filter(enrollment_status=status)

    if has_special_needs != '':
        students = students.filter(has_special_needs=(has_special_needs.lower() == 'true'))

    if transportation_required != '':
        students = students.filter(transportation_required=(transportation_required.lower() == 'true'))

    # Age filtering
    today = date.today()
    if min_age:
        try:
            min_age_int = int(min_age)
            max_birth_date = today - timedelta(days=min_age_int * 365.25)
            students = students.filter(date_of_birth__lte=max_birth_date)
        except ValueError:
            pass

    if max_age:
        try:
            max_age_int = int(max_age)
            min_birth_date = today - timedelta(days=(max_age_int + 1) * 365.25)
            students = students.filter(date_of_birth__gte=min_birth_date)
        except ValueError:
            pass

    # Calculate statistics
    total_students = students.count()
    male_count = students.filter(gender='M').count()
    female_count = students.filter(gender='F').count()
    active_students = students.filter(enrollment_status='active').count()
    
    male_percentage = (male_count / total_students * 100) if total_students > 0 else 0
    female_percentage = (female_count / total_students * 100) if total_students > 0 else 0
    
    students_with_dob = students.filter(date_of_birth__isnull=False)
    ages = []
    for s in students_with_dob:
        age = today.year - s.date_of_birth.year - (
            (today.month, today.day) < (s.date_of_birth.month, s.date_of_birth.day)
        )
        ages.append(age)
    avg_age = sum(ages) / len(ages) if ages else 0

    stats = {
        'total_students': total_students,
        'male_count': male_count,
        'female_count': female_count,
        'male_percentage': round(male_percentage, 1),
        'female_percentage': round(female_percentage, 1),
        'active_students': active_students,
        'avg_age': round(avg_age, 1),
    }

    # Check if requesting all results (for print/export)
    if page == 'all':
        student_list = []
        for s in students:
            student_list.append({
                'id': str(s.id),
                'full_name': s.get_full_name(),
                'admission_number': s.admission_number,
                'gender': s.get_gender_display(),
                'level': s.current_academic_level.name if s.current_academic_level else '',
                'status': s.get_enrollment_status_display(),
                'age': s.get_age(),
                'photo': s.photo.url if s.photo else '',
                'phone': s.phone_number or '',
                'email': s.personal_email or '',
                'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
                'admission_date': s.admission_date.isoformat() if s.admission_date else None,
                'has_special_needs': s.has_special_needs,
                'transportation_required': s.transportation_required,
            })

        return JsonResponse({
            'students': student_list,
            'total_count': total_students,
            'stats': stats,
        })

    # Regular pagination
    paginator = Paginator(students, 10)
    try:
        students_page = paginator.page(page)
    except PageNotAnInteger:
        students_page = paginator.page(1)
    except EmptyPage:
        students_page = paginator.page(paginator.num_pages)

    student_list = []
    for s in students_page:
        student_list.append({
            'id': str(s.id),
            'full_name': s.get_full_name(),
            'admission_number': s.admission_number,
            'gender': s.get_gender_display(),
            'level': s.current_academic_level.name if s.current_academic_level else '',
            'status': s.get_enrollment_status_display(),
            'age': s.get_age(),
            'photo': s.photo.url if s.photo else '',
            'phone': s.phone_number or '',
            'email': s.personal_email or '',
            'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
            'admission_date': s.admission_date.isoformat() if s.admission_date else None,
            'has_special_needs': s.has_special_needs,
            'transportation_required': s.transportation_required,
        })

    return JsonResponse({
        'students': student_list,
        'has_previous': students_page.has_previous(),
        'has_next': students_page.has_next(),
        'current_page': students_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'start_index': students_page.start_index(),
        'end_index': students_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# GUARDIAN PROFILE PICTURE UPDATE
# =============================================================================

@csrf_exempt
def update_guardian_profile_picture(request):
    """
    AJAX endpoint to update guardian profile picture via base64 image data
    """
    try:
        data = json.loads(request.body)
        guardian_id = data.get("guardian_id")
        image_data = data.get("image")

        if not guardian_id or not image_data:
            return JsonResponse(
                {"success": False, "message": "Invalid data."},
                status=400
            )
        
        try:
            guardian = Guardian.objects.get(id=guardian_id)
        except Guardian.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Guardian not found."},
                status=404  
            )
        
        extension = None
        if image_data.startswith("data:image/jpeg;base64,"):
            image_data = image_data[len("data:image/jpeg;base64,"):]
            extension = ".jpg"
        elif image_data.startswith("data:image/png;base64,"):
            image_data = image_data[len("data:image/png;base64,"):]
            extension = ".png"
        else:
            return JsonResponse(
                {"success": False, "message": "Unsupported image format. Only JPG and PNG are allowed"},
                status=400  
            )
        
        try:
            image_data_decoded = base64.b64decode(image_data)
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid image data."},
                status=400  
            )   

        file_name = f"{guardian.id}{extension}" 

        if guardian.photo:
            old_file_path = guardian.photo.path
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception as e:
                    logger.warning(f"Could not delete old file: {e}")

        profile_picture = ContentFile(image_data_decoded)
        guardian.photo.save(file_name, profile_picture, save=True)

        redirect_url = reverse("students:guardian_profile", args=[guardian.id])

        return JsonResponse(
            {"success": True, "message": "Profile picture updated successfully", "redirect_url": redirect_url}
        )
    
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400 
        )
    
    except Exception as e:
        logger.error(f"Error updating guardian profile picture: {e}")
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"},
            status=500  
        )


# =============================================================================
# GUARDIAN SEARCH
# =============================================================================

def guardian_search(request):
    """
    AJAX view to return filtered guardians as JSON
    """
    query = request.GET.get('q', '').strip()
    guardian_type = request.GET.get('guardian_type', '')
    gender = request.GET.get('gender', '')
    is_active = request.GET.get('is_active', '')
    page = request.GET.get('page', 1)

    guardians = Guardian.objects.all().order_by('last_name', 'first_name')

    # Apply text search
    if query:
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= (
                Q(first_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(primary_phone__icontains=term) |
                Q(email__icontains=term) |
                Q(national_id__icontains=term)
            )
        guardians = guardians.filter(q_objects)

    # Apply filters
    if guardian_type:
        guardians = guardians.filter(guardian_type=guardian_type)

    if gender:
        guardians = guardians.filter(gender=gender)

    if is_active != '':
        guardians = guardians.filter(is_active=(is_active.lower() == 'true'))

    total_guardians = guardians.count()
    active_guardians = guardians.filter(is_active=True).count()

    stats = {
        'total_guardians': total_guardians,
        'active_guardians': active_guardians,
    }

    # Check if requesting all results
    if page == 'all':
        guardian_list = []
        for g in guardians:
            # Get count of students
            student_count = g.student_relationships.filter(is_active=True).count()
            
            guardian_list.append({
                'id': str(g.id),
                'full_name': g.get_full_name(),
                'guardian_type': g.get_guardian_type_display(),
                'primary_phone': g.primary_phone,
                'email': g.email or '',
                'occupation': g.occupation or '',
                'photo': g.photo.url if g.photo else '',
                'is_active': g.is_active,
                'student_count': student_count,
            })

        return JsonResponse({
            'guardians': guardian_list,
            'total_count': total_guardians,
            'stats': stats,
        })

    # Regular pagination
    paginator = Paginator(guardians, 10)
    try:
        guardians_page = paginator.page(page)
    except PageNotAnInteger:
        guardians_page = paginator.page(1)
    except EmptyPage:
        guardians_page = paginator.page(paginator.num_pages)

    guardian_list = []
    for g in guardians_page:
        # Get count of students
        student_count = g.student_relationships.filter(is_active=True).count()
        
        guardian_list.append({
            'id': str(g.id),
            'full_name': g.get_full_name(),
            'guardian_type': g.get_guardian_type_display(),
            'primary_phone': g.primary_phone,
            'email': g.email or '',
            'occupation': g.occupation or '',
            'photo': g.photo.url if g.photo else '',
            'is_active': g.is_active,
            'student_count': student_count,
        })

    return JsonResponse({
        'guardians': guardian_list,
        'current_page': guardians_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': guardians_page.has_previous(),
        'has_next': guardians_page.has_next(),
        'start_index': guardians_page.start_index(),
        'end_index': guardians_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# DORMITORY SEARCH
# =============================================================================

def dormitory_search(request):
    """
    AJAX view to return filtered dormitories as JSON
    """
    query = request.GET.get('q', '').strip()
    dormitory_type = request.GET.get('dormitory_type', '')
    is_active = request.GET.get('is_active', '')
    maintenance_status = request.GET.get('maintenance_status', '')
    has_availability = request.GET.get('has_availability', '')
    page = request.GET.get('page', 1)

    dormitories = Dormitory.objects.all().select_related(
        'dormitory_master', 'assistant_dormitory_master'
    ).order_by('dormitory_type', 'name')

    # Apply text search
    if query:
        dormitories = dormitories.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(building__icontains=query)
        )

    # Apply filters
    if dormitory_type:
        dormitories = dormitories.filter(dormitory_type=dormitory_type)

    if is_active != '':
        dormitories = dormitories.filter(is_active=(is_active.lower() == 'true'))

    if maintenance_status:
        dormitories = dormitories.filter(maintenance_status=maintenance_status)

    if has_availability and has_availability.lower() == 'true':
        dormitories = dormitories.filter(current_occupancy__lt=F('total_capacity'))

    total_dormitories = dormitories.count()
    active_dormitories = dormitories.filter(is_active=True).count()
    total_capacity = sum([d.total_capacity for d in dormitories])
    total_occupancy = sum([d.current_occupancy for d in dormitories])

    stats = {
        'total_dormitories': total_dormitories,
        'active_dormitories': active_dormitories,
        'total_capacity': total_capacity,
        'total_occupancy': total_occupancy,
        'overall_occupancy_percentage': round((total_occupancy / total_capacity * 100), 1) if total_capacity > 0 else 0,
    }

    # Check if requesting all results
    if page == 'all':
        dormitory_list = []
        for d in dormitories:
            dormitory_list.append({
                'id': str(d.id),
                'name': d.name,
                'code': d.code,
                'dormitory_type': d.get_dormitory_type_display(),
                'total_capacity': d.total_capacity,
                'current_occupancy': d.current_occupancy,
                'available_capacity': d.get_available_capacity(),
                'occupancy_percentage': d.get_occupancy_percentage(),
                'occupancy_level': d.get_occupancy_level(),
                'room_count': d.room_count,
                'beds_per_room': d.beds_per_room,
                'maintenance_status': d.get_maintenance_status_display(),
                'dormitory_master': d.dormitory_master.full_name() if d.dormitory_master else None,
                'is_active': d.is_active,
                'is_available_for_new_admissions': d.is_available_for_new_admissions,
                'full_location': d.get_full_location(),
            })

        return JsonResponse({
            'dormitories': dormitory_list,
            'total_count': total_dormitories,
            'stats': stats,
        })

    # Regular pagination
    paginator = Paginator(dormitories, 10)
    try:
        dormitories_page = paginator.page(page)
    except PageNotAnInteger:
        dormitories_page = paginator.page(1)
    except EmptyPage:
        dormitories_page = paginator.page(paginator.num_pages)

    dormitory_list = []
    for d in dormitories_page:
        dormitory_list.append({
            'id': str(d.id),
            'name': d.name,
            'code': d.code,
            'dormitory_type': d.get_dormitory_type_display(),
            'total_capacity': d.total_capacity,
            'current_occupancy': d.current_occupancy,
            'available_capacity': d.get_available_capacity(),
            'occupancy_percentage': d.get_occupancy_percentage(),
            'occupancy_level': d.get_occupancy_level(),
            'room_count': d.room_count,
            'beds_per_room': d.beds_per_room,
            'maintenance_status': d.get_maintenance_status_display(),
            'dormitory_master': d.dormitory_master.full_name() if d.dormitory_master else None,
            'is_active': d.is_active,
            'is_available_for_new_admissions': d.is_available_for_new_admissions,
            'full_location': d.get_full_location(),
        })

    return JsonResponse({
        'dormitories': dormitory_list,
        'current_page': dormitories_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': dormitories_page.has_previous(),
        'has_next': dormitories_page.has_next(),
        'start_index': dormitories_page.start_index(),
        'end_index': dormitories_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# BOARDING ENROLLMENT SEARCH
# =============================================================================

def boarding_enrollment_search(request):
    """
    AJAX view to return filtered boarding enrollments as JSON
    """
    query = request.GET.get('q', '').strip()
    dormitory = request.GET.get('dormitory', '')
    boarding_type = request.GET.get('boarding_type', '')
    status = request.GET.get('status', '')
    academic_session = request.GET.get('academic_session', '')
    page = request.GET.get('page', 1)

    enrollments = BoardingEnrollment.objects.all().select_related(
        'student', 'dormitory', 'academic_session', 'consenting_guardian'
    ).order_by('-enrollment_date')

    # Apply text search
    if query:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__admission_number__icontains=query) |
            Q(boarding_roll_number__icontains=query) |
            Q(room_number__icontains=query)
        )

    # Apply filters
    if dormitory:
        enrollments = enrollments.filter(dormitory_id=dormitory)

    if boarding_type:
        enrollments = enrollments.filter(boarding_type=boarding_type)

    if status:
        enrollments = enrollments.filter(status=status)

    if academic_session:
        enrollments = enrollments.filter(academic_session_id=academic_session)

    total_enrollments = enrollments.count()
    active_enrollments = enrollments.filter(status='ACTIVE').count()
    pending_enrollments = enrollments.filter(status='PENDING').count()

    stats = {
        'total_enrollments': total_enrollments,
        'active_enrollments': active_enrollments,
        'pending_enrollments': pending_enrollments,
    }

    # Check if requesting all results
    if page == 'all':
        enrollment_list = []
        for e in enrollments:
            enrollment_list.append({
                'id': str(e.id),
                'student_name': e.student.get_full_name(),
                'student_admission_number': e.student.admission_number,
                'dormitory': e.dormitory.name,
                'boarding_type': e.get_boarding_type_display(),
                'status': e.get_status_display(),
                'academic_session': e.academic_session.name,
                'room_number': e.room_number,
                'bed_number': e.bed_number,
                'boarding_roll_number': e.boarding_roll_number,
                'enrollment_date': e.enrollment_date.isoformat(),
                'effective_start_date': e.effective_start_date.isoformat(),
                'effective_end_date': e.effective_end_date.isoformat() if e.effective_end_date else None,
                'guardian_consent': e.guardian_consent,
                'boarding_schedule': e.get_boarding_schedule_display(),
            })

        return JsonResponse({
            'enrollments': enrollment_list,
            'total_count': total_enrollments,
            'stats': stats,
        })

    # Regular pagination
    paginator = Paginator(enrollments, 10)
    try:
        enrollments_page = paginator.page(page)
    except PageNotAnInteger:
        enrollments_page = paginator.page(1)
    except EmptyPage:
        enrollments_page = paginator.page(paginator.num_pages)

    enrollment_list = []
    for e in enrollments_page:
        enrollment_list.append({
            'id': str(e.id),
            'student_name': e.student.get_full_name(),
            'student_admission_number': e.student.admission_number,
            'dormitory': e.dormitory.name,
            'boarding_type': e.get_boarding_type_display(),
            'status': e.get_status_display(),
            'academic_session': e.academic_session.name,
            'room_number': e.room_number,
            'bed_number': e.bed_number,
            'boarding_roll_number': e.boarding_roll_number,
            'enrollment_date': e.enrollment_date.isoformat(),
            'effective_start_date': e.effective_start_date.isoformat(),
            'effective_end_date': e.effective_end_date.isoformat() if e.effective_end_date else None,
            'guardian_consent': e.guardian_consent,
            'boarding_schedule': e.get_boarding_schedule_display(),
        })

    return JsonResponse({
        'enrollments': enrollment_list,
        'current_page': enrollments_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
        'has_previous': enrollments_page.has_previous(),
        'has_next': enrollments_page.has_next(),
        'start_index': enrollments_page.start_index(),
        'end_index': enrollments_page.end_index(),
        'stats': stats,
    })


# =============================================================================
# STUDENT GUARDIANS VIEW
# =============================================================================

def get_student_guardians(request, student_id):
    """
    Get all guardians for a specific student with relationship details
    """
    try:
        student = Student.objects.get(id=student_id)
        
        relationships = StudentGuardian.objects.filter(
            student=student,
            is_active=True
        ).select_related('guardian').order_by('emergency_contact_priority')
        
        guardian_list = []
        for rel in relationships:
            guardian_list.append({
                'id': str(rel.guardian.id),
                'relationship_id': str(rel.id),
                'full_name': rel.guardian.get_full_name(),
                'relationship': rel.get_relationship_display(),
                'is_primary': rel.is_primary,
                'is_financial_responsible': rel.is_financial_responsible,
                'can_pickup': rel.can_pickup,
                'can_authorize_medical': rel.can_authorize_medical,
                'emergency_contact_priority': rel.emergency_contact_priority,
                'emergency_priority_display': rel.get_emergency_priority_display(),
                'primary_phone': rel.guardian.primary_phone,
                'email': rel.guardian.email or '',
                'photo': rel.guardian.photo.url if rel.guardian.photo else '',
            })
        
        return JsonResponse({
            'success': True,
            'student_name': student.get_full_name(),
            'guardians': guardian_list,
            'total_guardians': len(guardian_list),
        })
        
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Student not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting student guardians: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)