# students/utils.py

from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from datetime import date

# =============================================================================
# CENTURY-SAFE YEAR UTILITIES
# =============================================================================

def get_century_safe_year_suffix(year):
    """
    Convert year to century-safe format
    
    Args:
        year (int): Full year (e.g., 2024, 2125)
        
    Returns:
        str: Century-safe year suffix
        
    Examples:
        2024 → "24"
        2099 → "99" 
        2100 → "A00"
        2125 → "A25"
        2200 → "B00"
        2350 → "C50"
    """
    if year < 2000:
        # Handle years before 2000 (unlikely but safe)
        return f"{year % 100:02d}"
    elif year < 2100:
        # 21st century: 2000-2099 → 00-99
        return f"{year % 100:02d}"
    else:
        # 22nd century and beyond: use letter prefix
        century = year // 100
        century_offset = century - 20  # 21st century = 0, 22nd = 1, etc.
        century_letter = chr(ord('A') + century_offset - 1)
        year_part = year % 100
        return f"{century_letter}{year_part:02d}"


def parse_admission_year_from_number(admission_number):
    """
    Parse the actual year from a century-safe admission number
    
    Args:
        admission_number (str): Admission number (e.g., "24/SCH/0001", "B25/SCH/0001")
        
    Returns:
        int: The actual year (e.g., 2024, 2225) or None if parsing fails
        
    Examples:
        "24/SCH/0001" → 2024
        "A25/SCH/0001" → 2125
        "B00/SCH/0001" → 2200
    """
    try:
        year_part = admission_number.split('/')[0]
        
        if year_part.isdigit():
            # Standard 2-digit format (21st century)
            year_suffix = int(year_part)
            if year_suffix >= 0 and year_suffix <= 99:
                return 2000 + year_suffix
        else:
            # Century prefix format
            century_letter = year_part[0]
            year_suffix = int(year_part[1:])
            
            # Calculate century offset
            century_offset = ord(century_letter.upper()) - ord('A') + 1
            century = 20 + century_offset  # 21st=20, 22nd=21, etc.
            
            return (century * 100) + year_suffix
            
    except (ValueError, IndexError):
        pass
    
    return None


# =============================================================================
# ADMISSION NUMBER GENERATION (CENTURY-SAFE)
# =============================================================================

def generate_student_admission_number(
    *,
    school=None,
    user=None,
    admission_year=None
):
    """
    Generate a unique century-safe admission number.

    Format:
        YY/ABBR/NNNN
        AYY/ABBR/NNNN
    """

    from .models import Student
    from accounts.models import UserProfile

    current_year = admission_year or timezone.now().year
    year_suffix = get_century_safe_year_suffix(current_year)

    # -----------------------------
    # Resolve school abbreviation
    # -----------------------------
    school_abbrev = "SCH"

    if school and school.abbreviation:
        school_abbrev = school.abbreviation

    elif user:
        try:
            profile = UserProfile.objects.select_related("school").get(user=user)
            if profile.school and profile.school.abbreviation:
                school_abbrev = profile.school.abbreviation
        except UserProfile.DoesNotExist:
            pass

    prefix = f"{year_suffix}/{school_abbrev}/"

    # -----------------------------
    # Generate sequential number
    # -----------------------------
    while True:
        with transaction.atomic():
            last_student = (
                Student.objects
                .select_for_update()
                .filter(admission_number__startswith=prefix)
                .order_by("-admission_number")
                .first()
            )

            if last_student:
                try:
                    last_seq = int(last_student.admission_number.split("/")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = (
                        Student.objects
                        .filter(admission_number__startswith=prefix)
                        .count() + 1
                    )
            else:
                next_seq = 1

            admission_number = f"{prefix}{next_seq:04d}"

            if not Student.objects.filter(admission_number=admission_number).exists():
                return admission_number



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