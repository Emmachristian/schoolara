# hr/utils.py

from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q, F
from datetime import date, timedelta
from decimal import Decimal
import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

logger = logging.getLogger(__name__)

# =============================================================================
# CORE UTILITY HELPER FUNCTIONS
# =============================================================================

def paginate_queryset(request, queryset, per_page=20):
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj, paginator

def parse_filters(request, filter_keys):
    """
    Extract filter values from request.GET.
    filter_keys: list of filter names to extract
    Returns dict: {key: value or None}
    """
    filters = {}
    for key in filter_keys:
        value = request.GET.get(key, '').strip()
        filters[key] = value if value else None
    return filters

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


def parse_staff_year_from_id(staff_id):
    """
    Parse the actual year from a century-safe staff ID
    
    Args:
        staff_id (str): Staff ID (e.g., "24/SCH/TCH-001", "B25/SCH/ADM-001")
        
    Returns:
        int: The actual year (e.g., 2024, 2225) or None if parsing fails
        
    Examples:
        "24/SCH/TCH-001" → 2024
        "A25/SCH/TCH-001" → 2125
        "B00/SCH/ADM-001" → 2200
    """
    try:
        year_part = staff_id.split('/')[0]
        
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
# STAFF ID GENERATION (CENTURY-SAFE)
# =============================================================================

def get_staff_type_code(employment_status, is_teaching=False):
    """
    Get staff type code based on employment status and teaching status
    
    Args:
        employment_status (str): Employment status code
        is_teaching (bool): Whether staff is a teacher
        
    Returns:
        str: Staff type code
        
    Examples:
        ('FT', True) → 'TCH'  # Full-time Teacher
        ('FT', False) → 'ADM'  # Full-time Admin
        ('PT', True) → 'PTT'   # Part-time Teacher
        ('CT', False) → 'CNT'  # Contract Staff
    """
    if is_teaching:
        if employment_status == 'PT':
            return 'PTT'  # Part-time Teacher
        return 'TCH'  # Teacher
    else:
        status_codes = {
            'FT': 'ADM',  # Full-time Admin
            'PT': 'PTA',  # Part-time Admin
            'CT': 'CNT',  # Contract
            'PR': 'PRB',  # Probation
            'IN': 'INT',  # Intern
            'VO': 'VOL',  # Volunteer
        }
        return status_codes.get(employment_status, 'STF')  # Default: Staff


def generate_staff_id(
    *,
    school=None,
    user=None,
    joining_year=None,
    department=None,
    employment_status='FT',
    is_teaching=False
):
    """
    Generate a unique century-safe staff ID.

    Format:
        YY/SCHOOL/TYPE-NNN
        YY/SCHOOL/DEPT/TYPE-NNN (if department provided)
        AYY/SCHOOL/TYPE-NNN (for years beyond 2099)
    
    Args:
        school: School instance
        user: User instance (alternative to school)
        joining_year: Year of joining (defaults to current year)
        department: Department instance (optional)
        employment_status: Employment status code
        is_teaching: Whether this is a teaching staff
        
    Returns:
        str: Unique staff ID
        
    Examples:
        generate_staff_id(school=sch, is_teaching=True) → "24/ATEPI/TCH-001"
        generate_staff_id(school=sch, department=math) → "24/ATEPI/MATH/TCH-001"
        generate_staff_id(school=sch, employment_status='CT') → "24/ATEPI/CNT-001"
    """
    from .models import Staff
    from accounts.models import UserProfile

    current_year = joining_year or timezone.now().year
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

    # -----------------------------
    # Build prefix
    # -----------------------------
    staff_type = get_staff_type_code(employment_status, is_teaching)
    
    if department and department.code:
        prefix = f"{year_suffix}/{school_abbrev}/{department.code}/{staff_type}-"
    else:
        prefix = f"{year_suffix}/{school_abbrev}/{staff_type}-"

    # -----------------------------
    # Generate sequential number
    # -----------------------------
    while True:
        with transaction.atomic():
            last_staff = (
                Staff.objects
                .select_for_update()
                .filter(staff_id__startswith=prefix)
                .order_by("-staff_id")
                .first()
            )

            if last_staff:
                try:
                    last_seq = int(last_staff.staff_id.split("-")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = (
                        Staff.objects
                        .filter(staff_id__startswith=prefix)
                        .count() + 1
                    )
            else:
                next_seq = 1

            staff_id = f"{prefix}{next_seq:03d}"

            if not Staff.objects.filter(staff_id=staff_id).exists():
                return staff_id
            
# =============================================================================
# CONTRACT NUMBER GENERATION (CENTURY-SAFE)
# =============================================================================

def generate_contract_number(contract_type=None, year=None):
    """
    Generate a unique century-safe contract number.
    Format: CONT/YYYY/TYPE/NNNN or CONT/AYYYY/TYPE/NNNN (for years beyond 2099)
    
    Args:
        contract_type: ContractType instance (optional)
        year: Contract year (defaults to current year)
        
    Returns:
        str: Unique contract number
        
    Examples:
        generate_contract_number() → "CONT/2024/GEN/0001"
        generate_contract_number(permanent_type) → "CONT/2024/PERM/0001"
        generate_contract_number(temp_type, 2125) → "CONT/A125/TEMP/0001"
    """
    from .models import Contract
    
    current_year = year or timezone.now().year
    
    # Get century-safe year format
    if current_year < 2100:
        year_str = str(current_year)
    else:
        # For years beyond 2099, use letter prefix
        century = current_year // 100
        century_offset = century - 20  # 21st century = 0, 22nd = 1, etc.
        century_letter = chr(ord('A') + century_offset - 1)
        year_suffix = current_year % 100
        year_str = f"{century_letter}{current_year}"
    
    # Get type code
    type_code = "GEN"
    if contract_type:
        # Get first 4 letters of contract type name
        type_code = contract_type.name[:4].upper().replace(' ', '')
    
    # Generate sequential number
    prefix = f"CONT/{year_str}/{type_code}/"
    
    while True:
        with transaction.atomic():
            last_contract = (
                Contract.objects
                .select_for_update()
                .filter(contract_number__startswith=prefix)
                .order_by("-contract_number")
                .first()
            )
            
            if last_contract:
                try:
                    last_seq = int(last_contract.contract_number.split("/")[-1])
                    next_seq = last_seq + 1
                except (ValueError, IndexError):
                    next_seq = (
                        Contract.objects
                        .filter(contract_number__startswith=prefix)
                        .count() + 1
                    )
            else:
                next_seq = 1
            
            contract_number = f"{prefix}{next_seq:04d}"
            
            if not Contract.objects.filter(contract_number=contract_number).exists():
                return contract_number

# =============================================================================
# CONTRACT UTILITIES
# =============================================================================

def get_expiring_contracts(days=30):
    """
    Get contracts expiring within specified days
    
    Args:
        days (int): Number of days to look ahead (default: 30)
        
    Returns:
        QuerySet: Contracts expiring within specified period
    """
    from .models import Contract
    
    today = date.today()
    end_date = today + timedelta(days=days)
    
    return Contract.objects.filter(
        status='ACTIVE',
        end_date__gte=today,
        end_date__lte=end_date
    ).select_related('staff', 'contract_type')


def get_active_contracts():
    """
    Get all active contracts
    
    Returns:
        QuerySet: All active contracts
    """
    from .models import Contract
    return Contract.objects.filter(status='ACTIVE')


def get_probation_staff():
    """
    Get all staff currently on probation
    
    Returns:
        QuerySet: Staff members on probation
    """
    from .models import Staff
    return Staff.objects.filter(employment_status='PR', is_active=True)


def get_staff_on_probation_ending_soon(days=30):
    """
    Get staff whose probation period is ending soon
    
    Args:
        days (int): Number of days to look ahead
        
    Returns:
        QuerySet: Staff with probation ending soon
    """
    from .models import Contract
    
    today = date.today()
    end_date = today + timedelta(days=days)
    
    # Get contracts with probation period ending soon
    contracts = Contract.objects.filter(
        status='ACTIVE',
        probation_period_months__gt=0
    ).select_related('staff')
    
    probation_ending = []
    for contract in contracts:
        probation_end = contract.start_date + timedelta(days=contract.probation_period_months * 30)
        if today <= probation_end <= end_date:
            probation_ending.append(contract.staff)
    
    return probation_ending


# =============================================================================
# STAFF INSTANCE UTILITIES
# =============================================================================

def get_days_until_birthday(staff):
    """
    Calculate days until staff member's next birthday
    
    Args:
        staff: Staff instance
        
    Returns:
        int: Number of days until next birthday, or None if no birth date
    """
    if not staff.date_of_birth:
        return None
    
    today = date.today()
    next_birthday = date(today.year, staff.date_of_birth.month, staff.date_of_birth.day)
    
    if next_birthday < today:
        next_birthday = date(today.year + 1, staff.date_of_birth.month, staff.date_of_birth.day)
    
    return (next_birthday - today).days


def is_birthday_today(staff):
    """
    Check if today is staff member's birthday
    
    Args:
        staff: Staff instance
        
    Returns:
        bool: True if today is staff's birthday, False otherwise
    """
    if not staff.date_of_birth:
        return False
    
    today = date.today()
    return (staff.date_of_birth.month == today.month and 
            staff.date_of_birth.day == today.day)


def get_employment_duration(staff):
    """
    Get how long staff member has been employed (in days)
    
    Args:
        staff: Staff instance
        
    Returns:
        int: Number of days employed, or None if no joining date
    """
    if not staff.date_of_joining:
        return None
    
    if staff.date_of_leaving:
        end_date = staff.date_of_leaving
    else:
        end_date = date.today()
    
    return (end_date - staff.date_of_joining).days


def get_years_of_service(staff):
    """
    Get how many years staff member has been employed
    
    Args:
        staff: Staff instance
        
    Returns:
        float: Number of years of service rounded to 1 decimal place
    """
    days = get_employment_duration(staff)
    if days:
        return round(days / 365.25, 1)
    return 0


def get_staff_current_contract(staff):
    """
    Get staff member's current active contract
    
    Args:
        staff: Staff instance
        
    Returns:
        Contract instance or None
    """
    from .models import Contract
    
    return Contract.objects.filter(
        staff=staff,
        status='ACTIVE'
    ).first()


def get_staff_age(staff):
    """
    Calculate staff member's current age
    
    Args:
        staff: Staff instance
        
    Returns:
        int: Age in years, or None if no birth date
    """
    if not staff.date_of_birth:
        return None
    
    today = date.today()
    age = today.year - staff.date_of_birth.year - (
        (today.month, today.day) < (staff.date_of_birth.month, staff.date_of_birth.day)
    )
    return age


def is_staff_due_for_retirement(staff, retirement_age=60):
    """
    Check if staff is approaching retirement age
    
    Args:
        staff: Staff instance
        retirement_age (int): Retirement age (default: 60)
        
    Returns:
        dict: Dictionary with retirement information
    """
    age = get_staff_age(staff)
    if not age:
        return {
            'is_due': False,
            'years_remaining': None,
            'retirement_date': None
        }
    
    years_remaining = retirement_age - age
    is_due = years_remaining <= 5  # Within 5 years of retirement
    
    retirement_date = None
    if staff.date_of_birth:
        retirement_date = date(
            staff.date_of_birth.year + retirement_age,
            staff.date_of_birth.month,
            staff.date_of_birth.day
        )
    
    return {
        'is_due': is_due,
        'years_remaining': years_remaining,
        'retirement_date': retirement_date,
        'current_age': age
    }


# =============================================================================
# SALARY CALCULATION UTILITIES
# =============================================================================

def calculate_monthly_salary(contract):
    """
    Calculate monthly salary from contract based on salary frequency
    
    Args:
        contract: Contract instance
        
    Returns:
        Money: Monthly salary amount
    """
    basic_salary = contract.basic_salary
    frequency = contract.salary_frequency
    
    conversions = {
        'MONTHLY': 1,
        'ANNUAL': 1/12,
        'WEEKLY': 52/12,
        'DAILY': 22,  # Assuming 22 working days per month
        'HOURLY': contract.working_hours_per_week * 52 / 12
    }
    
    multiplier = conversions.get(frequency, 1)
    return basic_salary * Decimal(str(multiplier))


def calculate_annual_salary(contract):
    """
    Calculate annual salary from contract
    
    Args:
        contract: Contract instance
        
    Returns:
        Money: Annual salary amount
    """
    monthly = calculate_monthly_salary(contract)
    return monthly * 12


# =============================================================================
# TEACHER-SPECIFIC UTILITIES
# =============================================================================

def get_teacher_workload(teacher):
    """
    Calculate teacher's current workload percentage
    
    Args:
        teacher: Teacher instance
        
    Returns:
        float: Workload percentage (0-100+)
    """
    if teacher.max_hours_per_week == 0:
        return 0
    
    return round((teacher.current_teaching_load / teacher.max_hours_per_week) * 100, 1)


def is_teacher_overloaded(teacher):
    """
    Check if teacher is overloaded (working more than max hours)
    
    Args:
        teacher: Teacher instance
        
    Returns:
        bool: True if overloaded
    """
    return teacher.current_teaching_load > teacher.max_hours_per_week


def get_available_teachers():
    """
    Get teachers who have capacity for more classes
    
    Returns:
        QuerySet: Teachers with available capacity
    """
    from .models import Teacher
    
    return Teacher.objects.filter(
        staff__is_active=True
    ).exclude(
        current_teaching_load__gte=F('max_hours_per_week')
    )