# hr/utils.py

"""
HR Utility Functions

Pure utility functions for HR operations:
- Century-safe year handling
- Staff ID format generation (logic only, not creation)
- Salary calculations
- Date calculations
- Staff information queries

NO DATABASE WRITES - Only calculations, formatting, and simple queries.
For complex workflows with DB writes, see hr/services.py
"""

from django.utils import timezone
from django.db.models import F
from datetime import date, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CENTURY-SAFE YEAR UTILITIES
# =============================================================================

def get_century_safe_year_suffix(year):
    """
    Convert year to century-safe format.
    
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
    Parse the actual year from a century-safe staff ID.
    
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
            if 0 <= year_suffix <= 99:
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
# STAFF TYPE CODE UTILITIES
# =============================================================================

def get_staff_type_code(employment_status, is_teaching=False):
    """
    Get staff type code based on employment status and teaching status.
    Pure function - no DB access.
    
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


def build_staff_id_prefix(year, school_abbrev, dept_code=None, staff_type='ADM'):
    """
    Build staff ID prefix WITHOUT touching database.
    Pure function for prefix construction.
    
    Args:
        year (int): Joining year
        school_abbrev (str): School abbreviation
        dept_code (str, optional): Department code
        staff_type (str): Staff type code
        
    Returns:
        str: Prefix like "24/ATEPI/TCH-" or "A25/SCH/MATH/ADM-"
        
    Examples:
        build_staff_id_prefix(2024, 'SCH', None, 'TCH') → "24/SCH/TCH-"
        build_staff_id_prefix(2024, 'SCH', 'MATH', 'TCH') → "24/SCH/MATH/TCH-"
        build_staff_id_prefix(2125, 'SCH', None, 'ADM') → "A25/SCH/ADM-"
    """
    year_suffix = get_century_safe_year_suffix(year)
    
    if dept_code:
        return f"{year_suffix}/{school_abbrev}/{dept_code}/{staff_type}-"
    else:
        return f"{year_suffix}/{school_abbrev}/{staff_type}-"


def parse_staff_id_components(staff_id):
    """
    Parse staff ID into components.
    Pure function - no DB access.
    
    Args:
        staff_id (str): Staff ID (e.g., "24/SCH/MATH/TCH-001")
        
    Returns:
        dict: Components or None if invalid
        {
            'year': int,
            'school': str,
            'department': str or None,
            'type': str,
            'sequence': int
        }
        
    Examples:
        "24/SCH/TCH-001" → {year: 2024, school: 'SCH', type: 'TCH', seq: 1}
        "24/SCH/MATH/TCH-001" → {year: 2024, school: 'SCH', dept: 'MATH', type: 'TCH', seq: 1}
    """
    try:
        parts = staff_id.split('/')
        
        if len(parts) == 3:
            # Format: YY/SCHOOL/TYPE-NNN
            year_part, school, type_seq = parts
            type_code, sequence = type_seq.split('-')
            
            return {
                'year': parse_staff_year_from_id(staff_id),
                'school': school,
                'department': None,
                'type': type_code,
                'sequence': int(sequence)
            }
        elif len(parts) == 4:
            # Format: YY/SCHOOL/DEPT/TYPE-NNN
            year_part, school, dept, type_seq = parts
            type_code, sequence = type_seq.split('-')
            
            return {
                'year': parse_staff_year_from_id(staff_id),
                'school': school,
                'department': dept,
                'type': type_code,
                'sequence': int(sequence)
            }
    except (ValueError, IndexError):
        pass
    
    return None


# =============================================================================
# CONTRACT NUMBER UTILITIES
# =============================================================================

def build_contract_number_prefix(year, type_code='GEN'):
    """
    Build contract number prefix WITHOUT touching database.
    Pure function for prefix construction.
    
    Args:
        year (int): Contract year
        type_code (str): Contract type code
        
    Returns:
        str: Prefix like "CONT/2024/GEN/" or "CONT/A125/PERM/"
        
    Examples:
        build_contract_number_prefix(2024, 'PERM') → "CONT/2024/PERM/"
        build_contract_number_prefix(2125, 'TEMP') → "CONT/A125/TEMP/"
    """
    # Get century-safe year format
    if year < 2100:
        year_str = str(year)
    else:
        # For years beyond 2099, use letter prefix
        century = year // 100
        century_offset = century - 20  # 21st century = 0, 22nd = 1, etc.
        century_letter = chr(ord('A') + century_offset - 1)
        year_str = f"{century_letter}{year}"
    
    return f"CONT/{year_str}/{type_code}/"


def get_contract_type_code(contract_type_name):
    """
    Get contract type code from contract type name.
    Pure function - no DB access.
    
    Args:
        contract_type_name (str): Contract type name
        
    Returns:
        str: 4-letter type code
        
    Examples:
        "Permanent" → "PERM"
        "Fixed Term" → "FIXE"
        "Temporary Contract" → "TEMP"
    """
    # Get first 4 letters of contract type name
    return contract_type_name[:4].upper().replace(' ', '')


# =============================================================================
# SIMPLE QUERY HELPERS (Read-Only)
# =============================================================================

def get_expiring_contracts(days=30):
    """
    Get contracts expiring within specified days.
    Simple query helper - read-only.
    
    Args:
        days (int): Number of days to look ahead (default: 30)
        
    Returns:
        QuerySet: Contracts expiring within specified period
    """
    from hr.models import Contract
    
    today = date.today()
    end_date = today + timedelta(days=days)
    
    return Contract.objects.filter(
        status='ACTIVE',
        end_date__gte=today,
        end_date__lte=end_date
    ).select_related('staff')


def get_active_contracts():
    """
    Get all active contracts.
    Simple query helper - read-only.
    
    Returns:
        QuerySet: All active contracts
    """
    from hr.models import Contract
    return Contract.objects.filter(status='ACTIVE')


def get_probation_staff():
    """
    Get all staff currently on probation.
    Simple query helper - read-only.
    
    Returns:
        QuerySet: Staff members on probation
    """
    from hr.models import Staff
    return Staff.objects.filter(employment_status='PR', is_active=True)


def get_staff_on_probation_ending_soon(days=30):
    """
    Get staff whose probation period is ending soon.
    
    Args:
        days (int): Number of days to look ahead
        
    Returns:
        list: Staff instances with probation ending soon
    """
    from hr.models import Contract
    
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


def get_available_teachers():
    """
    Get teachers who have capacity for more classes.
    Simple query helper - read-only.
    
    Returns:
        QuerySet: Teachers with available capacity
    """
    from hr.models import Teacher
    
    return Teacher.objects.filter(
        staff__is_active=True
    ).exclude(
        current_teaching_load__gte=F('max_hours_per_week')
    )


def get_staff_current_contract(staff):
    """
    Get staff member's current active contract.
    Simple query helper - read-only.
    
    Args:
        staff: Staff instance
        
    Returns:
        Contract instance or None
    """
    from hr.models import Contract
    
    return Contract.objects.filter(
        staff=staff,
        status='ACTIVE'
    ).first()


# =============================================================================
# DATE & AGE CALCULATIONS
# =============================================================================

def get_days_until_birthday(staff):
    """
    Calculate days until staff member's next birthday.
    Pure calculation - no DB writes.
    
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
    Check if today is staff member's birthday.
    Pure check - no DB writes.
    
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
    Get how long staff member has been employed (in days).
    Pure calculation - no DB writes.
    
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
    Get how many years staff member has been employed.
    Pure calculation - no DB writes.
    
    Args:
        staff: Staff instance
        
    Returns:
        float: Number of years of service rounded to 1 decimal place
    """
    days = get_employment_duration(staff)
    if days:
        return round(days / 365.25, 1)
    return 0


def get_staff_age(staff):
    """
    Calculate staff member's current age.
    Pure calculation - no DB writes.
    
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
    Check if staff is approaching retirement age.
    Pure calculation - no DB writes.
    
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
# SALARY CALCULATIONS
# =============================================================================

def calculate_monthly_salary(contract):
    """
    Calculate monthly salary from contract based on salary frequency.
    Pure calculation - no DB writes.
    
    Args:
        contract: Contract instance
        
    Returns:
        Decimal: Monthly salary amount
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
    Calculate annual salary from contract.
    Pure calculation - no DB writes.
    
    Args:
        contract: Contract instance
        
    Returns:
        Decimal: Annual salary amount
    """
    monthly = calculate_monthly_salary(contract)
    return monthly * 12


def calculate_daily_rate(contract):
    """
    Calculate daily rate from contract.
    Pure calculation - no DB writes.
    
    Args:
        contract: Contract instance
        
    Returns:
        Decimal: Daily rate
    """
    monthly = calculate_monthly_salary(contract)
    return monthly / 22  # Assuming 22 working days per month


def calculate_hourly_rate(contract):
    """
    Calculate hourly rate from contract.
    Pure calculation - no DB writes.
    
    Args:
        contract: Contract instance
        
    Returns:
        Decimal: Hourly rate
    """
    monthly = calculate_monthly_salary(contract)
    hours_per_month = contract.working_hours_per_week * 52 / 12
    return monthly / Decimal(str(hours_per_month))


# =============================================================================
# TEACHER-SPECIFIC UTILITIES
# =============================================================================

def get_teacher_workload(teacher):
    """
    Calculate teacher's current workload percentage.
    Pure calculation - no DB writes.
    
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
    Check if teacher is overloaded (working more than max hours).
    Pure check - no DB writes.
    
    Args:
        teacher: Teacher instance
        
    Returns:
        bool: True if overloaded
    """
    return teacher.current_teaching_load > teacher.max_hours_per_week


def calculate_available_teaching_hours(teacher):
    """
    Calculate how many hours teacher has available.
    Pure calculation - no DB writes.
    
    Args:
        teacher: Teacher instance
        
    Returns:
        int: Available hours (can be negative if overloaded)
    """
    return teacher.max_hours_per_week - teacher.current_teaching_load


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_staff_data(staff_data):
    """
    Validate staff data before creation.
    Pure validation - no DB writes.
    
    Args:
        staff_data (dict): Staff data dictionary
        
    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str
        }
    """
    errors = []
    warnings = []
    
    # Required fields
    required = ['first_name', 'last_name', 'date_of_joining']
    for field in required:
        if field not in staff_data or not staff_data[field]:
            errors.append(f"{field.replace('_', ' ').title()} is required")
    
    # Date validations
    if 'date_of_birth' in staff_data and staff_data['date_of_birth']:
        if staff_data['date_of_birth'] > date.today():
            errors.append("Birth date cannot be in the future")
        
        # Check minimum age (18)
        age = (date.today() - staff_data['date_of_birth']).days / 365.25
        if age < 18:
            warnings.append("Staff member is under 18 years old")
    
    if 'date_of_joining' in staff_data and staff_data['date_of_joining']:
        if staff_data['date_of_joining'] > date.today():
            errors.append("Joining date cannot be in the future")
    
    # Email validation
    if 'personal_email' in staff_data and staff_data['personal_email']:
        if '@' not in staff_data['personal_email']:
            errors.append("Invalid email address")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }


def validate_contract_data(contract_data):
    """
    Validate contract data before creation.
    Pure validation - no DB writes.
    
    Args:
        contract_data (dict): Contract data dictionary
        
    Returns:
        dict: {
            'valid': bool,
            'errors': list of str,
            'warnings': list of str
        }
    """
    errors = []
    warnings = []
    
    # Required fields
    required = ['staff', 'contract_type', 'start_date', 'basic_salary']
    for field in required:
        if field not in contract_data or not contract_data[field]:
            errors.append(f"{field.replace('_', ' ').title()} is required")
    
    # Date validations
    if 'start_date' in contract_data and 'end_date' in contract_data:
        if contract_data['end_date'] and contract_data['end_date'] < contract_data['start_date']:
            errors.append("End date cannot be before start date")
    
    # Salary validation
    if 'basic_salary' in contract_data:
        if contract_data['basic_salary'] <= 0:
            errors.append("Basic salary must be positive")
    
    valid = len(errors) == 0
    
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings
    }