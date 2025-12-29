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


    
