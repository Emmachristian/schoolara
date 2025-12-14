from .models import Student
import json
import base64
import os
from datetime import date, timedelta
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

@csrf_exempt
def update_student_profile_picture(request):
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
                status=404  
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
                    # Log the error but continue
                    print(f"Could not delete old file: {e}")

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
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"},
            status=500  
        )

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
    page = request.GET.get('page', 1)

    students = Student.objects.all().order_by('-created_at')

    # Apply filters (same as before)
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
        'avg_age': round(avg_age, 1),
    }

    # Check if requesting all results (for print/export)
    if page == 'all':
        # Return ALL students without pagination
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
                'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
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
            'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
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
