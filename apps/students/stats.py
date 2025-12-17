# students/stats.py

from django.db.models import Count
from datetime import date

# =============================================================================
# STUDENT STATISTICS UTILITIES
# =============================================================================

def get_student_statistics():
    """
    Get comprehensive statistics for all students
    Returns a dictionary with various student statistics
    
    Returns:
        dict: Dictionary containing student statistics including:
            - total_students: Total count of all students
            - male_count: Number of male students
            - female_count: Number of female students
            - male_percentage: Percentage of male students
            - female_percentage: Percentage of female students
            - active_students: Number of active students
            - avg_age: Average age of all students
            - status_counts: Dictionary with counts for each enrollment status
            - level_counts: List of academic levels with student counts
    """
    from .models import Student
    
    students = Student.objects.all()
    
    # Total counts
    total_students = students.count()
    male_count = students.filter(gender='M').count()
    female_count = students.filter(gender='F').count()
    
    # Active students
    active_students = students.filter(enrollment_status='active').count()
    
    # Calculate average age
    today = date.today()
    ages = []
    for student in students:
        if student.date_of_birth:
            age = today.year - student.date_of_birth.year - (
                (today.month, today.day) < (student.date_of_birth.month, student.date_of_birth.day)
            )
            ages.append(age)
    
    avg_age = sum(ages) / len(ages) if ages else 0
    
    # Status breakdown
    status_counts = {}
    for status_code, status_name in Student.ENROLLMENT_STATUS_CHOICES:
        status_counts[status_code] = students.filter(enrollment_status=status_code).count()
    
    # Academic level breakdown
    level_counts = students.values('current_academic_level__name').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Gender percentage
    male_percentage = (male_count / total_students * 100) if total_students > 0 else 0
    female_percentage = (female_count / total_students * 100) if total_students > 0 else 0
    
    return {
        'total_students': total_students,
        'male_count': male_count,
        'female_count': female_count,
        'male_percentage': round(male_percentage, 1),
        'female_percentage': round(female_percentage, 1),
        'active_students': active_students,
        'avg_age': round(avg_age, 1),
        'status_counts': status_counts,
        'level_counts': list(level_counts),
    }


def get_gender_count(gender):
    """
    Get count of students by gender
    
    Args:
        gender (str): Gender code ('M' or 'F')
        
    Returns:
        int: Number of students with specified gender
    """
    from .models import Student
    return Student.objects.filter(gender=gender).count()


def get_active_student_count():
    """
    Get count of active students
    
    Returns:
        int: Number of active students
    """
    from .models import Student
    return Student.objects.filter(enrollment_status='active').count()


def get_average_student_age():
    """
    Calculate average age of all students
    
    Returns:
        float: Average age rounded to 1 decimal place, or 0 if no students
    """
    from .models import Student
    
    today = date.today()
    students = Student.objects.all()
    ages = []
    
    for student in students:
        if student.date_of_birth:
            age = today.year - student.date_of_birth.year - (
                (today.month, today.day) < (student.date_of_birth.month, student.date_of_birth.day)
            )
            ages.append(age)
    
    return round(sum(ages) / len(ages), 1) if ages else 0


def get_birthday_students():
    """
    Get students whose birthday is today
    
    Returns:
        QuerySet: Students with birthday today
    """
    from .models import Student
    
    today = date.today()
    return Student.objects.filter(
        date_of_birth__month=today.month,
        date_of_birth__day=today.day
    )


def get_students_by_status(status):
    """
    Get count of students by enrollment status
    
    Args:
        status (str): Enrollment status code (e.g., 'active', 'suspended')
        
    Returns:
        int: Number of students with specified status
    """
    from .models import Student
    return Student.objects.filter(enrollment_status=status).count()


def get_students_by_health_condition(condition):
    """
    Get count of students by health condition
    
    Args:
        condition (str): Health condition code
        
    Returns:
        int: Number of students with specified health condition
    """
    from .models import Student
    return Student.objects.filter(health_condition=condition).count()


def get_special_needs_count():
    """
    Get count of students with special needs
    
    Returns:
        int: Number of students with special needs
    """
    from .models import Student
    return Student.objects.filter(has_special_needs=True).count()


def get_transport_required_count():
    """
    Get count of students requiring transportation
    
    Returns:
        int: Number of students requiring transportation
    """
    from .models import Student
    return Student.objects.filter(transportation_required=True).count()

# =============================================================================
# STUDENT INSTANCE UTILITIES
# =============================================================================

def get_days_until_birthday(student):
    """
    Calculate days until student's next birthday
    
    Args:
        student: Student instance
        
    Returns:
        int: Number of days until next birthday, or None if no birth date
    """
    if not student.date_of_birth:
        return None
    
    today = date.today()
    next_birthday = date(today.year, student.date_of_birth.month, student.date_of_birth.day)
    
    if next_birthday < today:
        next_birthday = date(today.year + 1, student.date_of_birth.month, student.date_of_birth.day)
    
    return (next_birthday - today).days


def is_birthday_today(student):
    """
    Check if today is student's birthday
    
    Args:
        student: Student instance
        
    Returns:
        bool: True if today is student's birthday, False otherwise
    """
    if not student.date_of_birth:
        return False
    
    today = date.today()
    return (student.date_of_birth.month == today.month and 
            student.date_of_birth.day == today.day)


def get_enrollment_duration(student):
    """
    Get how long student has been enrolled (in days)
    
    Args:
        student: Student instance
        
    Returns:
        int: Number of days enrolled, or None if no admission date
    """
    if not student.admission_date:
        return None
    
    if student.enrollment_status in ['graduated', 'withdrawn', 'transferred']:
        end_date = student.graduation_date or student.withdrawal_date or date.today()
    else:
        end_date = date.today()
    
    return (end_date - student.admission_date).days


def get_years_in_school(student):
    """
    Get how many years student has been in school
    
    Args:
        student: Student instance
        
    Returns:
        float: Number of years in school rounded to 1 decimal place
    """
    days = get_enrollment_duration(student)
    if days:
        return round(days / 365.25, 1)
    return 0