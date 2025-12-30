# students/stats.py

from django.db.models import Count, Avg, Q, Max, Min
from django.db.models.functions import TruncMonth
from datetime import date, timedelta

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
    active_students = students.filter(enrollment_status='ACTIVE').count()
    
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
    return Student.objects.filter(enrollment_status='ACTIVE').count()


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
        status (str): Enrollment status code (e.g., 'ACTIVE', 'SUSPENDED')
        
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
# GUARDIAN STATISTICS UTILITIES
# =============================================================================

def get_guardian_statistics():
    """
    Get comprehensive statistics for all guardians
    
    Returns:
        dict: Dictionary containing guardian statistics including:
            - total_guardians: Total count of all guardians
            - active_guardians: Number of active guardians
            - male_count: Number of male guardians
            - female_count: Number of female guardians
            - male_percentage: Percentage of male guardians
            - female_percentage: Percentage of female guardians
            - avg_age: Average age of guardians
            - guardian_type_counts: Counts by guardian type
            - guardians_with_multiple_students: Count of guardians with 2+ students
            - avg_students_per_guardian: Average number of students per guardian
            - primary_guardians: Number of primary guardians
            - financial_guardians: Number of financial responsible guardians
            - guardians_by_relationship: Breakdown by relationship type
    """
    from .models import Guardian, StudentGuardian
    
    guardians = Guardian.objects.all()
    active_guardians = guardians.filter(is_active=True)
    
    # Total counts
    total_guardians = guardians.count()
    active_count = active_guardians.count()
    male_count = guardians.filter(gender='M').count()
    female_count = guardians.filter(gender='F').count()
    
    # Calculate average age
    today = date.today()
    ages = []
    for guardian in guardians:
        if guardian.date_of_birth:
            age = today.year - guardian.date_of_birth.year - (
                (today.month, today.day) < (guardian.date_of_birth.month, guardian.date_of_birth.day)
            )
            ages.append(age)
    
    avg_age = sum(ages) / len(ages) if ages else 0
    
    # Guardian type breakdown
    guardian_type_counts = {}
    for type_code, type_name in Guardian.GUARDIAN_TYPE_CHOICES:
        guardian_type_counts[type_code] = guardians.filter(guardian_type=type_code).count()
    
    # Students per guardian statistics
    guardian_student_counts = guardians.annotate(
        student_count=Count('student_relationships', filter=Q(student_relationships__is_active=True))
    )
    
    guardians_with_multiple = guardian_student_counts.filter(student_count__gte=2).count()
    total_student_connections = guardian_student_counts.aggregate(total=Count('student_relationships'))['total'] or 0
    avg_students = total_student_connections / total_guardians if total_guardians > 0 else 0
    
    # Role-specific counts
    primary_guardians = StudentGuardian.objects.filter(is_primary=True, is_active=True).values('guardian').distinct().count()
    financial_guardians = StudentGuardian.objects.filter(is_financial_responsible=True, is_active=True).values('guardian').distinct().count()
    
    # Relationship breakdown
    relationship_counts = {}
    for rel_code, rel_name in StudentGuardian.RELATIONSHIP_CHOICES:
        relationship_counts[rel_code] = StudentGuardian.objects.filter(
            relationship=rel_code,
            is_active=True
        ).count()
    
    # Gender percentages
    male_percentage = (male_count / total_guardians * 100) if total_guardians > 0 else 0
    female_percentage = (female_count / total_guardians * 100) if total_guardians > 0 else 0
    
    return {
        'total_guardians': total_guardians,
        'active_guardians': active_count,
        'male_count': male_count,
        'female_count': female_count,
        'male_percentage': round(male_percentage, 1),
        'female_percentage': round(female_percentage, 1),
        'avg_age': round(avg_age, 1),
        'guardian_type_counts': guardian_type_counts,
        'guardians_with_multiple_students': guardians_with_multiple,
        'avg_students_per_guardian': round(avg_students, 2),
        'primary_guardians': primary_guardians,
        'financial_guardians': financial_guardians,
        'guardians_by_relationship': relationship_counts,
    }


def get_guardians_by_type(guardian_type):
    """
    Get count of guardians by type
    
    Args:
        guardian_type (str): Guardian type code (e.g., 'PRIMARY', 'SECONDARY')
        
    Returns:
        int: Number of guardians of specified type
    """
    from .models import Guardian
    return Guardian.objects.filter(guardian_type=guardian_type).count()


def get_active_guardian_count():
    """
    Get count of active guardians
    
    Returns:
        int: Number of active guardians
    """
    from .models import Guardian
    return Guardian.objects.filter(is_active=True).count()


def get_guardians_with_multiple_students():
    """
    Get guardians who are responsible for multiple students
    
    Returns:
        QuerySet: Guardians with 2 or more students
    """
    from .models import Guardian
    return Guardian.objects.annotate(
        student_count=Count('student_relationships', filter=Q(student_relationships__is_active=True))
    ).filter(student_count__gte=2)


def get_guardians_by_relationship(relationship_type):
    """
    Get count of guardian relationships by type
    
    Args:
        relationship_type (str): Relationship code (e.g., 'FATHER', 'MOTHER')
        
    Returns:
        int: Number of relationships of specified type
    """
    from .models import StudentGuardian
    return StudentGuardian.objects.filter(
        relationship=relationship_type,
        is_active=True
    ).count()


def get_primary_guardian_count():
    """
    Get count of unique primary guardians
    
    Returns:
        int: Number of guardians marked as primary for at least one student
    """
    from .models import StudentGuardian
    return StudentGuardian.objects.filter(
        is_primary=True,
        is_active=True
    ).values('guardian').distinct().count()


def get_financial_guardian_count():
    """
    Get count of unique financially responsible guardians
    
    Returns:
        int: Number of guardians responsible for fees
    """
    from .models import StudentGuardian
    return StudentGuardian.objects.filter(
        is_financial_responsible=True,
        is_active=True
    ).values('guardian').distinct().count()


def get_emergency_contact_count():
    """
    Get count of active emergency contacts
    
    Returns:
        int: Number of guardian relationships marked as emergency contacts
    """
    from .models import StudentGuardian
    return StudentGuardian.objects.filter(
        emergency_contact_priority__lte=5,
        is_active=True
    ).count()


def get_guardians_without_students():
    """
    Get guardians who don't have any active student relationships
    
    Returns:
        QuerySet: Guardians with no active students
    """
    from .models import Guardian
    return Guardian.objects.annotate(
        student_count=Count('student_relationships', filter=Q(student_relationships__is_active=True))
    ).filter(student_count=0)


def get_guardian_occupation_stats():
    """
    Get statistics on guardian occupations
    
    Returns:
        dict: Dictionary with occupation distribution
    """
    from .models import Guardian
    
    # Get top 10 most common occupations
    occupation_counts = Guardian.objects.filter(
        is_active=True,
        occupation__isnull=False
    ).exclude(
        occupation=''
    ).values('occupation').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Count guardians with/without occupation info
    with_occupation = Guardian.objects.filter(is_active=True).exclude(Q(occupation='') | Q(occupation__isnull=True)).count()
    without_occupation = Guardian.objects.filter(is_active=True).filter(Q(occupation='') | Q(occupation__isnull=True)).count()
    
    return {
        'top_occupations': list(occupation_counts),
        'with_occupation': with_occupation,
        'without_occupation': without_occupation,
    }


# =============================================================================
# SIBLING STATISTICS UTILITIES
# =============================================================================

def get_sibling_statistics():
    """
    Get comprehensive statistics for sibling relationships
    
    Returns:
        dict: Dictionary containing sibling statistics including:
            - total_sibling_relationships: Total count of sibling relationships
            - verified_relationships: Number of verified relationships
            - unverified_relationships: Number of unverified relationships
            - relationship_type_counts: Breakdown by relationship type
            - students_with_siblings: Count of students who have siblings
            - students_without_siblings: Count of students with no siblings
            - avg_siblings_per_student: Average number of siblings per student
            - largest_sibling_group: Largest group of siblings
    """
    from .models import Student, SiblingRelationship
    
    # Total relationships
    total_relationships = SiblingRelationship.objects.count()
    verified = SiblingRelationship.objects.filter(is_verified=True).count()
    unverified = total_relationships - verified
    
    # Relationship type breakdown
    relationship_type_counts = {}
    for type_code, type_name in SiblingRelationship.RELATIONSHIP_TYPES:
        relationship_type_counts[type_code] = SiblingRelationship.objects.filter(
            relationship_type=type_code
        ).count()
    
    # Students with/without siblings
    students_with_siblings = Student.objects.filter(
        Q(sibling_relationships__isnull=False) | Q(reverse_sibling_relationships__isnull=False)
    ).distinct().count()
    
    total_students = Student.objects.count()
    students_without_siblings = total_students - students_with_siblings
    
    # Average siblings calculation
    student_sibling_counts = Student.objects.annotate(
        sibling_count=Count('sibling_relationships') + Count('reverse_sibling_relationships')
    )
    
    total_sibling_connections = sum(s.sibling_count for s in student_sibling_counts)
    avg_siblings = total_sibling_connections / total_students if total_students > 0 else 0
    
    # Find largest sibling group
    largest_group = 0
    if students_with_siblings > 0:
        largest_group = student_sibling_counts.aggregate(
            Max('sibling_count')
        )['sibling_count__max'] or 0
    
    return {
        'total_sibling_relationships': total_relationships,
        'verified_relationships': verified,
        'unverified_relationships': unverified,
        'relationship_type_counts': relationship_type_counts,
        'students_with_siblings': students_with_siblings,
        'students_without_siblings': students_without_siblings,
        'avg_siblings_per_student': round(avg_siblings, 2),
        'largest_sibling_group': largest_group,
    }


def get_students_with_siblings():
    """
    Get students who have sibling relationships
    
    Returns:
        QuerySet: Students with at least one sibling relationship
    """
    from .models import Student
    return Student.objects.filter(
        Q(sibling_relationships__isnull=False) | Q(reverse_sibling_relationships__isnull=False)
    ).distinct()


def get_students_without_siblings():
    """
    Get students who don't have any sibling relationships
    
    Returns:
        QuerySet: Students with no siblings in the system
    """
    from .models import Student
    return Student.objects.exclude(
        Q(sibling_relationships__isnull=False) | Q(reverse_sibling_relationships__isnull=False)
    )


def get_sibling_count_for_student(student):
    """
    Get the total number of siblings for a specific student
    
    Args:
        student: Student instance
        
    Returns:
        int: Total number of siblings
    """
    from django.db.models import Count
    
    forward_count = student.sibling_relationships.count()
    reverse_count = student.reverse_sibling_relationships.count()
    
    return forward_count + reverse_count


def get_verified_sibling_relationships():
    """
    Get all verified sibling relationships
    
    Returns:
        QuerySet: Verified sibling relationships
    """
    from .models import SiblingRelationship
    return SiblingRelationship.objects.filter(is_verified=True)


def get_unverified_sibling_relationships():
    """
    Get all unverified sibling relationships
    
    Returns:
        QuerySet: Unverified sibling relationships
    """
    from .models import SiblingRelationship
    return SiblingRelationship.objects.filter(is_verified=False)


def get_sibling_relationships_by_type(relationship_type):
    """
    Get count of sibling relationships by type
    
    Args:
        relationship_type (str): Relationship type code (e.g., 'FULL', 'HALF')
        
    Returns:
        int: Number of relationships of specified type
    """
    from .models import SiblingRelationship
    return SiblingRelationship.objects.filter(relationship_type=relationship_type).count()


def get_full_sibling_pairs():
    """
    Get all full sibling relationships
    
    Returns:
        QuerySet: Full sibling relationships
    """
    from .models import SiblingRelationship
    return SiblingRelationship.objects.filter(relationship_type='FULL')


def get_largest_sibling_groups():
    """
    Get students grouped by sibling connections, showing largest families
    
    Returns:
        list: List of tuples (student, sibling_count) ordered by count descending
    """
    from .models import Student
    
    students = Student.objects.annotate(
        sibling_count=Count('sibling_relationships') + Count('reverse_sibling_relationships')
    ).filter(sibling_count__gt=0).order_by('-sibling_count')[:10]
    
    return [(student, student.sibling_count) for student in students]


# =============================================================================
# COMBINED STATISTICS
# =============================================================================

def get_comprehensive_statistics():
    """
    Get all statistics in one call - students, guardians, and siblings
    
    Returns:
        dict: Dictionary with all statistics grouped by category
    """
    return {
        'students': get_student_statistics(),
        'guardians': get_guardian_statistics(),
        'siblings': get_sibling_statistics(),
    }


def get_family_statistics():
    """
    Get family-focused statistics combining students, guardians, and siblings
    
    Returns:
        dict: Dictionary with family-related statistics
    """
    from .models import Student, Guardian
    
    # Students with complete family info
    students_with_guardians = Student.objects.filter(
        guardian_relationships__isnull=False,
        guardian_relationships__is_active=True
    ).distinct().count()
    
    students_without_guardians = Student.objects.exclude(
        guardian_relationships__isnull=False
    ).count()
    
    # Students with both parents
    students_with_both_parents = Student.objects.filter(
        guardian_relationships__relationship__in=['FATHER', 'MOTHER'],
        guardian_relationships__is_active=True
    ).annotate(
        parent_count=Count('guardian_relationships', filter=Q(
            guardian_relationships__relationship__in=['FATHER', 'MOTHER'],
            guardian_relationships__is_active=True
        ))
    ).filter(parent_count__gte=2).count()
    
    # Single parent families
    students_with_single_parent = Student.objects.filter(
        guardian_relationships__relationship__in=['FATHER', 'MOTHER'],
        guardian_relationships__is_active=True
    ).annotate(
        parent_count=Count('guardian_relationships', filter=Q(
            guardian_relationships__relationship__in=['FATHER', 'MOTHER'],
            guardian_relationships__is_active=True
        ))
    ).filter(parent_count=1).count()
    
    return {
        'students_with_guardians': students_with_guardians,
        'students_without_guardians': students_without_guardians,
        'students_with_both_parents': students_with_both_parents,
        'students_with_single_parent': students_with_single_parent,
        'guardians_with_multiple_students': get_guardians_with_multiple_students().count(),
        'students_with_siblings': get_students_with_siblings().count(),
    }


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
    
    if student.enrollment_status in ['GRADUATED', 'WITHDRAWN', 'TRANSFERRED']:
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