# hr/stats.py
"""
Comprehensive statistics utility functions for HR models
Similar to academics and students statistics pattern
"""

from django.utils import timezone
from django.db.models import Count, Q, Avg, Sum, Max, Min, F, Case, When, IntegerField, FloatField, DecimalField
from django.db.models.functions import TruncMonth, TruncYear, TruncWeek, TruncDate
from datetime import timedelta, date
from collections import defaultdict
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# STAFF STATISTICS
# =============================================================================

def get_staff_statistics(filters=None):
    """
    Get comprehensive statistics for staff
    
    Args:
        filters (dict): Optional filters to apply
            - employment_status: Filter by employment status
            - gender: Filter by gender
            - department: Filter by department
            - is_active: Filter by active status
            - date_range: Tuple of (start_date, end_date) for joining dates
            - min_age: Minimum age filter
            - max_age: Maximum age filter
    
    Returns:
        dict: Staff statistics including counts, demographics, distributions
    """
    from .models import Staff, Teacher
    from datetime import date, timedelta
    from django.db.models import Count
    from django.db.models.functions import TruncYear
    
    # Define today at the top of the function
    today = date.today()
    
    staff = Staff.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('employment_status'):
            staff = staff.filter(employment_status=filters['employment_status'])
        if filters.get('gender'):
            staff = staff.filter(gender=filters['gender'])
        if filters.get('department'):
            staff = staff.filter(primary_department_id=filters['department'])
        if filters.get('is_active') is not None:
            staff = staff.filter(is_active=filters['is_active'])
        if filters.get('date_range'):
            start_date, end_date = filters['date_range']
            staff = staff.filter(date_of_joining__gte=start_date, date_of_joining__lte=end_date)
    
    total_staff = staff.count()
    
    # Basic counts
    stats = {
        'total_staff': total_staff,
        'active_staff': staff.filter(is_active=True).count(),
        'inactive_staff': staff.filter(is_active=False).count(),
        
        # Gender distribution
        'gender_distribution': {
            'male': staff.filter(gender='M').count(),
            'female': staff.filter(gender='F').count(),
            'other': staff.filter(gender='O').count(),
            'male_percentage': round((staff.filter(gender='M').count() / total_staff * 100), 1) if total_staff > 0 else 0,
            'female_percentage': round((staff.filter(gender='F').count() / total_staff * 100), 1) if total_staff > 0 else 0,
        },
        
        # Employment status distribution
        'by_employment_status': dict(
            staff.values('employment_status')
            .annotate(count=Count('id'))
            .values_list('employment_status', 'count')
        ),
        
        # Department distribution
        'by_department': dict(
            staff.exclude(primary_department__isnull=True)
            .values('primary_department__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('primary_department__name', 'count')
        ),
        
        # Marital status distribution
        'by_marital_status': dict(
            staff.exclude(marital_status='')
            .values('marital_status')
            .annotate(count=Count('id'))
            .values_list('marital_status', 'count')
        ),
        
        # Religious affiliation
        'by_religion': dict(
            staff.exclude(religious_affiliation='')
            .values('religious_affiliation')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('religious_affiliation', 'count')
        ),
        
        # Nationality distribution
        'by_nationality': dict(
            staff.values('nationality')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('nationality', 'count')[:10]
        ),
    }
    
    # Age analysis
    if total_staff > 0:
        ages = []
        for staff_member in staff:
            if staff_member.date_of_birth:
                age = today.year - staff_member.date_of_birth.year - (
                    (today.month, today.day) < (staff_member.date_of_birth.month, staff_member.date_of_birth.day)
                )
                ages.append(age)
        
        if ages:
            stats['age_analysis'] = {
                'average_age': round(sum(ages) / len(ages), 1),
                'youngest_age': min(ages),
                'oldest_age': max(ages),
                'median_age': sorted(ages)[len(ages) // 2],
                'age_groups': {
                    '18-25': len([a for a in ages if 18 <= a <= 25]),
                    '26-35': len([a for a in ages if 26 <= a <= 35]),
                    '36-45': len([a for a in ages if 36 <= a <= 45]),
                    '46-55': len([a for a in ages if 46 <= a <= 55]),
                    '56-65': len([a for a in ages if 56 <= a <= 65]),
                    '65+': len([a for a in ages if a > 65]),
                }
            }
    
    # Service duration analysis
    if total_staff > 0:
        service_durations = []
        for staff_member in staff:
            if staff_member.date_of_joining:
                if staff_member.date_of_leaving:
                    duration = (staff_member.date_of_leaving - staff_member.date_of_joining).days
                else:
                    duration = (today - staff_member.date_of_joining).days
                service_durations.append(duration)
        
        if service_durations:
            avg_service_days = sum(service_durations) / len(service_durations)
            stats['service_analysis'] = {
                'average_service_days': round(avg_service_days, 1),
                'average_service_years': round(avg_service_days / 365.25, 1),
                'shortest_service_days': min(service_durations),
                'longest_service_days': max(service_durations),
                'service_groups': {
                    '0-1 years': len([d for d in service_durations if d <= 365]),
                    '1-3 years': len([d for d in service_durations if 365 < d <= 1095]),
                    '3-5 years': len([d for d in service_durations if 1095 < d <= 1825]),
                    '5-10 years': len([d for d in service_durations if 1825 < d <= 3650]),
                    '10+ years': len([d for d in service_durations if d > 3650]),
                }
            }
    
    # Teaching vs non-teaching
    teaching_staff_ids = Teacher.objects.values_list('staff_id', flat=True)
    stats['staff_categories'] = {
        'teaching_staff': staff.filter(id__in=teaching_staff_ids).count(),
        'non_teaching_staff': staff.exclude(id__in=teaching_staff_ids).count(),
        'management_positions': staff.filter(
            designations__is_management=True,
            staffdesignation__is_active=True
        ).distinct().count(),
    }
    
    # Recent activity
    stats['recent_activity'] = {
        'joined_last_30_days': staff.filter(
            date_of_joining__gte=today - timedelta(days=30)
        ).count(),
        'joined_last_90_days': staff.filter(
            date_of_joining__gte=today - timedelta(days=90)
        ).count(),
        'left_last_30_days': staff.filter(
            date_of_leaving__gte=today - timedelta(days=30)
        ).count(),
        'birthdays_this_month': staff.filter(
            date_of_birth__month=today.month,
            is_active=True
        ).count(),
    }
    
    # Joining trends by year - Convert dates to strings for JSON serialization
    joining_trends_raw = (
        staff.annotate(year=TruncYear('date_of_joining'))
        .values('year')
        .annotate(count=Count('id'))
        .order_by('-year')
        .values_list('year', 'count')[:10]
    )
    
    # Convert date keys to ISO format strings (YYYY-MM-DD) or year strings
    stats['joining_trends'] = {}
    for year_date, count in joining_trends_raw:
        if year_date:
            # Extract just the year for cleaner display
            year_str = str(year_date.year)
            stats['joining_trends'][year_str] = count
        else:
            stats['joining_trends']['Unknown'] = count
    
    # Retirement analysis (assuming retirement age is 60)
    approaching_retirement = []
    for staff_member in staff.filter(is_active=True):
        if staff_member.date_of_birth:
            age = today.year - staff_member.date_of_birth.year - (
                (today.month, today.day) < (staff_member.date_of_birth.month, staff_member.date_of_birth.day)
            )
            if 55 <= age < 60:
                approaching_retirement.append(staff_member)
    
    # Calculate retirement date safely
    retirement_cutoff_date = date(today.year - 60, today.month, today.day)
    
    stats['retirement_analysis'] = {
        'approaching_retirement_5_years': len(approaching_retirement),
        'eligible_for_retirement': staff.filter(
            is_active=True,
            date_of_birth__lte=retirement_cutoff_date
        ).count(),
    }
    
    # Add total departments for consistency with template
    from .models import Department
    stats['total_departments'] = Department.objects.filter(is_active=True).count()
    
    return stats

# =============================================================================
# DEPARTMENT STATISTICS
# =============================================================================

def get_department_statistics(filters=None):
    """
    Get comprehensive statistics for departments
    
    Args:
        filters (dict): Optional filters
            - department_type: Filter by type
            - is_active: Filter by active status
            - is_academic: Filter by academic status
    
    Returns:
        dict: Department statistics and analysis
    """
    from .models import Department, Staff
    
    departments = Department.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('department_type'):
            departments = departments.filter(department_type=filters['department_type'])
        if filters.get('is_active') is not None:
            departments = departments.filter(is_active=filters['is_active'])
        if filters.get('is_academic') is not None:
            departments = departments.filter(is_academic=filters['is_academic'])
    
    # Annotate with staff counts
    departments = departments.annotate(
        staff_count=Count('primary_staff', filter=Q(primary_staff__is_active=True), distinct=True),
        total_staff_count=Count('primary_staff', distinct=True)
    )
    
    total_departments = departments.count()
    
    stats = {
        'total_departments': total_departments,
        'active_departments': departments.filter(is_active=True).count(),
        'inactive_departments': departments.filter(is_active=False).count(),
        'academic_departments': departments.filter(is_academic=True).count(),
        'non_academic_departments': departments.filter(is_academic=False).count(),
        
        # Type distribution
        'by_type': dict(
            departments.values('department_type')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('department_type', 'count')
        ),
        
        # Academic subtype distribution
        'by_academic_subtype': dict(
            departments.exclude(academic_subtype__isnull=True)
            .exclude(academic_subtype='')
            .values('academic_subtype')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('academic_subtype', 'count')
        ),
        
        # Staff distribution
        'staff_distribution': {
            'departments_with_staff': departments.filter(staff_count__gt=0).count(),
            'departments_without_staff': departments.filter(staff_count=0).count(),
            'total_staff_across_departments': Staff.objects.filter(is_active=True).count(),
            'average_staff_per_department': departments.aggregate(
                avg=Avg('staff_count')
            )['avg'] or 0,
        },
        
        # Departments with heads
        'leadership': {
            'departments_with_head': departments.exclude(head__isnull=True).count(),
            'departments_without_head': departments.filter(head__isnull=True).count(),
        },
    }
    
    # Capacity analysis
    departments_with_capacity = departments.exclude(capacity__isnull=True)
    if departments_with_capacity.exists():
        capacity_data = departments_with_capacity.aggregate(
            total_capacity=Sum('capacity'),
            avg_capacity=Avg('capacity'),
            total_staff=Sum('staff_count')
        )
        
        stats['capacity_analysis'] = {
            'total_capacity': capacity_data['total_capacity'] or 0,
            'average_capacity': float(capacity_data['avg_capacity'] or 0),
            'total_staff': capacity_data['total_staff'] or 0,
            'overall_utilization': (
                (capacity_data['total_staff'] / capacity_data['total_capacity'] * 100)
                if capacity_data['total_capacity'] and capacity_data['total_capacity'] > 0
                else 0
            ),
            'departments_at_capacity': departments_with_capacity.filter(
                staff_count__gte=F('capacity')
            ).count(),
            'departments_under_capacity': departments_with_capacity.filter(
                staff_count__lt=F('capacity')
            ).count(),
        }
    
    # Budget analysis
    departments_with_budget = departments.exclude(annual_budget__isnull=True)
    if departments_with_budget.exists():
        budget_data = departments_with_budget.aggregate(
            total_budget=Sum('annual_budget'),
            avg_budget=Avg('annual_budget'),
            min_budget=Min('annual_budget'),
            max_budget=Max('annual_budget')
        )
        
        stats['budget_analysis'] = {
            'departments_with_budget': departments_with_budget.count(),
            'total_budget': float(budget_data['total_budget'].amount) if budget_data['total_budget'] else 0,
            'average_budget': float(budget_data['avg_budget'].amount) if budget_data['avg_budget'] else 0,
            'smallest_budget': float(budget_data['min_budget'].amount) if budget_data['min_budget'] else 0,
            'largest_budget': float(budget_data['max_budget'].amount) if budget_data['max_budget'] else 0,
        }
    
    # Largest departments
    largest = departments.order_by('-staff_count')[:10]
    stats['largest_departments'] = [
        {
            'id': d.id,
            'name': d.name,
            'department_type': d.get_department_type_display(),
            'staff_count': d.staff_count,
            'capacity': d.capacity,
            'utilization': (d.staff_count / d.capacity * 100) if d.capacity else 0,
        }
        for d in largest
    ]
    
    # Departments needing attention
    stats['departments_needing_attention'] = {
        'no_head': departments.filter(is_active=True, head__isnull=True).count(),
        'no_staff': departments.filter(is_active=True, staff_count=0).count(),
        'over_capacity': departments.filter(
            is_active=True,
            staff_count__gt=F('capacity')
        ).count() if departments_with_capacity.exists() else 0,
    }
    
    return stats


# =============================================================================
# DESIGNATION STATISTICS
# =============================================================================

def get_designation_statistics(filters=None):
    """
    Get comprehensive statistics for designations
    
    Args:
        filters (dict): Optional filters
            - department: Filter by department
            - is_teaching: Filter by teaching status
            - is_management: Filter by management status
            - is_active: Filter by active status
    
    Returns:
        dict: Designation statistics and analysis
    """
    from .models import Designation, StaffDesignation
    from django.db.models import Count, Avg, Min, Max, Q
    
    designations = Designation.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('department'):
            designations = designations.filter(department_id=filters['department'])
        if filters.get('is_teaching') is not None:
            designations = designations.filter(is_teaching=filters['is_teaching'])
        if filters.get('is_management') is not None:
            designations = designations.filter(is_management=filters['is_management'])
        if filters.get('is_active') is not None:
            designations = designations.filter(is_active=filters['is_active'])
    
    # Annotate with staff counts
    designations = designations.annotate(
        staff_count=Count(
            'staff_members',
            filter=Q(staffdesignation__is_active=True),
            distinct=True
        )
    )
    
    total_designations = designations.count()
    
    stats = {
        'total_designations': total_designations,
        'active_designations': designations.filter(is_active=True).count(),
        'inactive_designations': designations.filter(is_active=False).count(),
        'teaching_designations': designations.filter(is_teaching=True).count(),
        'non_teaching_designations': designations.filter(is_teaching=False).count(),
        'management_designations': designations.filter(is_management=True).count(),
        
        # Department distribution
        'by_department': dict(
            designations.values('department__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('department__name', 'count')
        ),
        
        # Usage statistics
        'usage_stats': {
            'designations_in_use': designations.filter(staff_count__gt=0).count(),
            'unused_designations': designations.filter(staff_count=0).count(),
            'total_staff_assignments': StaffDesignation.objects.filter(is_active=True).count(),
            'average_staff_per_designation': designations.aggregate(
                avg=Avg('staff_count')
            )['avg'] or 0,
        },
    }
    
    # Salary range analysis
    designations_with_salary = designations.exclude(
        Q(min_salary__isnull=True) | Q(max_salary__isnull=True)
    )
    
    if designations_with_salary.exists():
        salary_data = designations_with_salary.aggregate(
            avg_min=Avg('min_salary'),
            avg_max=Avg('max_salary'),
            lowest_min=Min('min_salary'),
            highest_max=Max('max_salary')
        )
        
        stats['salary_range_analysis'] = {
            'designations_with_range': designations_with_salary.count(),
            'average_min_salary': float(salary_data['avg_min']) if salary_data['avg_min'] else 0,
            'average_max_salary': float(salary_data['avg_max']) if salary_data['avg_max'] else 0,
            'lowest_min_salary': float(salary_data['lowest_min']) if salary_data['lowest_min'] else 0,
            'highest_max_salary': float(salary_data['highest_max']) if salary_data['highest_max'] else 0,
        }
    
    # Most popular designations
    most_popular = designations.order_by('-staff_count')[:10]
    stats['most_popular_designations'] = [
        {
            'id': d.id,
            'name': d.name,
            'department': d.department.name,
            'staff_count': d.staff_count,
            'is_teaching': d.is_teaching,
            'is_management': d.is_management,
        }
        for d in most_popular
    ]
    
    # Rank distribution
    if total_designations > 0:
        rank_data = designations.aggregate(
            avg_rank=Avg('rank_order'),
            min_rank=Min('rank_order'),
            max_rank=Max('rank_order')
        )
        
        stats['rank_analysis'] = {
            'average_rank': float(rank_data['avg_rank'] or 0),
            'highest_rank': rank_data['min_rank'],  # Lower number = higher rank
            'lowest_rank': rank_data['max_rank'],
            'rank_levels': rank_data['max_rank'] - rank_data['min_rank'] + 1 if rank_data['max_rank'] and rank_data['min_rank'] else 0,
        }
    
    return stats

# =============================================================================
# CONTRACT TYPE STATISTICS
# =============================================================================

def get_contract_type_statistics():
    """
    Get comprehensive statistics for contract types
    
    Returns:
        dict: Statistics including counts, usage, and contract data
    """
    from .models import ContractType, Contract
    
    # Basic counts
    total_types = ContractType.objects.count()
    active_types = ContractType.objects.filter(is_active=True).count()
    inactive_types = ContractType.objects.filter(is_active=False).count()
    renewable_types = ContractType.objects.filter(requires_renewal=True).count()
    with_auto_probation = ContractType.objects.filter(auto_create_probation=True).count()
    
    # Contract counts
    total_contracts = Contract.objects.count()
    active_contracts = Contract.objects.filter(status='ACTIVE').count()
    
    # Contract types by usage
    most_used_type = (
        ContractType.objects
        .annotate(contract_count=Count('contracts'))
        .order_by('-contract_count')
        .first()
    )
    
    # Average durations
    avg_duration = (
        ContractType.objects
        .filter(default_duration_months__isnull=False)
        .aggregate(Avg('default_duration_months'))
    )['default_duration_months__avg'] or 0
    
    avg_probation = (
        ContractType.objects
        .filter(default_probation_months__isnull=False, auto_create_probation=True)
        .aggregate(Avg('default_probation_months'))
    )['default_probation_months__avg'] or 0
    
    # Types with no contracts
    unused_types = ContractType.objects.annotate(
        contract_count=Count('contracts')
    ).filter(contract_count=0).count()
    
    # Active types with active contracts
    active_types_in_use = ContractType.objects.filter(
        is_active=True,
        contracts__status='ACTIVE'
    ).distinct().count()
    
    # Get distribution of contract types
    contract_type_distribution = list(
        ContractType.objects
        .annotate(contract_count=Count('contracts'))
        .values('name', 'contract_count', 'is_active', 'requires_renewal')
        .order_by('-contract_count')
    )
    
    return {
        # Basic counts
        'total_types': total_types,
        'active_types': active_types,
        'inactive_types': inactive_types,
        'renewable_types': renewable_types,
        'non_renewable_types': total_types - renewable_types,
        'with_auto_probation': with_auto_probation,
        
        # Contract counts
        'total_contracts': total_contracts,
        'active_contracts': active_contracts,
        'expired_contracts': Contract.objects.filter(status='EXPIRED').count() if hasattr(Contract, 'status') else 0,
        'terminated_contracts': Contract.objects.filter(status='TERMINATED').count() if hasattr(Contract, 'status') else 0,
        
        # Usage statistics
        'unused_types': unused_types,
        'used_types': total_types - unused_types,
        'active_types_in_use': active_types_in_use,
        'most_used_type': most_used_type.name if most_used_type else None,
        'most_used_type_count': most_used_type.contract_count if most_used_type else 0,
        
        # Averages
        'avg_duration_months': round(avg_duration, 1),
        'avg_probation_months': round(avg_probation, 1),
        
        # Percentages
        'active_percentage': round((active_types / total_types * 100), 1) if total_types > 0 else 0,
        'renewable_percentage': round((renewable_types / total_types * 100), 1) if total_types > 0 else 0,
        'usage_percentage': round(((total_types - unused_types) / total_types * 100), 1) if total_types > 0 else 0,
        'auto_probation_percentage': round((with_auto_probation / total_types * 100), 1) if total_types > 0 else 0,
        
        # Distribution
        'contract_type_distribution': contract_type_distribution,
    }

# =============================================================================
# CONTRACT STATISTICS
# =============================================================================

def get_contract_statistics(filters=None):
    """
    Get comprehensive statistics for contracts
    
    Args:
        filters (dict): Optional filters
            - status: Filter by contract status
            - contract_type: Filter by contract type
            - staff: Filter by staff member
            - expiring_within_days: Filter contracts expiring within X days
            - salary_frequency: Filter by salary frequency
    
    Returns:
        dict: Contract statistics and analysis
    """
    from .models import Contract
    
    contracts = Contract.objects.all()
    
    # Apply filters
    if filters:
        if filters.get('status'):
            contracts = contracts.filter(status=filters['status'])
        if filters.get('contract_type'):
            contracts = contracts.filter(contract_type_id=filters['contract_type'])
        if filters.get('staff'):
            contracts = contracts.filter(staff_id=filters['staff'])
        if filters.get('salary_frequency'):
            contracts = contracts.filter(salary_frequency=filters['salary_frequency'])
        if filters.get('expiring_within_days'):
            days = filters['expiring_within_days']
            cutoff_date = date.today() + timedelta(days=days)
            contracts = contracts.filter(
                status='ACTIVE',
                end_date__lte=cutoff_date,
                end_date__gte=date.today()
            )
    
    total_contracts = contracts.count()
    current_date = date.today()
    
    stats = {
        'total_contracts': total_contracts,
        
        # Status distribution
        'by_status': dict(
            contracts.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        ),
        
        # Contract type distribution
        'by_type': dict(
            contracts.values('contract_type__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('contract_type__name', 'count')
        ),
        
        # Salary frequency distribution
        'by_salary_frequency': dict(
            contracts.values('salary_frequency')
            .annotate(count=Count('id'))
            .values_list('salary_frequency', 'count')
        ),
        
        # Active contracts
        'active_contracts': {
            'total': contracts.filter(status='ACTIVE').count(),
            'expiring_30_days': contracts.filter(
                status='ACTIVE',
                end_date__gte=current_date,
                end_date__lte=current_date + timedelta(days=30)
            ).count(),
            'expiring_60_days': contracts.filter(
                status='ACTIVE',
                end_date__gte=current_date,
                end_date__lte=current_date + timedelta(days=60)
            ).count(),
            'expiring_90_days': contracts.filter(
                status='ACTIVE',
                end_date__gte=current_date,
                end_date__lte=current_date + timedelta(days=90)
            ).count(),
            'expired_not_closed': contracts.filter(
                status='ACTIVE',
                end_date__lt=current_date
            ).count(),
        },
        
        # Probation analysis
        'probation_analysis': {
            'contracts_with_probation': contracts.filter(probation_period_months__gt=0).count(),
            'average_probation_months': contracts.filter(
                probation_period_months__gt=0
            ).aggregate(avg=Avg('probation_period_months'))['avg'] or 0,
        },
        
        # Auto-renewal
        'renewal_stats': {
            'auto_renewal_enabled': contracts.filter(auto_renew=True).count(),
            'manual_renewal': contracts.filter(auto_renew=False).count(),
        },
    }
    
    # Duration analysis
    if total_contracts > 0:
        contracts_with_dates = contracts.exclude(
            Q(start_date__isnull=True) | Q(end_date__isnull=True)
        )
        
        if contracts_with_dates.exists():
            durations = [
                (c.end_date - c.start_date).days
                for c in contracts_with_dates
            ]
            
            stats['duration_analysis'] = {
                'average_duration_days': sum(durations) / len(durations),
                'average_duration_months': (sum(durations) / len(durations)) / 30.44,
                'shortest_duration_days': min(durations),
                'longest_duration_days': max(durations),
                'duration_distribution': {
                    'under_6_months': len([d for d in durations if d < 180]),
                    '6_12_months': len([d for d in durations if 180 <= d < 365]),
                    '1_2_years': len([d for d in durations if 365 <= d < 730]),
                    '2_5_years': len([d for d in durations if 730 <= d < 1825]),
                    '5plus_years': len([d for d in durations if d >= 1825]),
                }
            }
    
    # Salary analysis
    if total_contracts > 0:
        from .utils import calculate_monthly_salary
        
        # Get monthly salaries for all contracts
        monthly_salaries = []
        for contract in contracts:
            try:
                monthly = calculate_monthly_salary(contract)
                monthly_salaries.append(float(monthly.amount))
            except:
                pass
        
        if monthly_salaries:
            stats['salary_analysis'] = {
                'total_monthly_payroll': sum(monthly_salaries),
                'average_monthly_salary': sum(monthly_salaries) / len(monthly_salaries),
                'lowest_monthly_salary': min(monthly_salaries),
                'highest_monthly_salary': max(monthly_salaries),
                'total_annual_payroll': sum(monthly_salaries) * 12,
            }
    
    # Working hours analysis
    if total_contracts > 0:
        hours_data = contracts.aggregate(
            avg_hours=Avg('working_hours_per_week'),
            min_hours=Min('working_hours_per_week'),
            max_hours=Max('working_hours_per_week')
        )
        
        stats['working_hours_analysis'] = {
            'average_hours_per_week': float(hours_data['avg_hours'] or 0),
            'minimum_hours_per_week': hours_data['min_hours'] or 0,
            'maximum_hours_per_week': hours_data['max_hours'] or 0,
        }
    
    # Leave analysis
    if total_contracts > 0:
        leave_data = contracts.aggregate(
            avg_leave=Avg('annual_leave_days'),
            min_leave=Min('annual_leave_days'),
            max_leave=Max('annual_leave_days')
        )
        
        stats['leave_analysis'] = {
            'average_annual_leave': float(leave_data['avg_leave'] or 0),
            'minimum_annual_leave': leave_data['min_leave'] or 0,
            'maximum_annual_leave': leave_data['max_leave'] or 0,
        }
    
    # Recent activity
    stats['recent_activity'] = {
        'created_last_30_days': contracts.filter(
            created_at__gte=current_date - timedelta(days=30)
        ).count(),
        'started_last_30_days': contracts.filter(
            start_date__gte=current_date - timedelta(days=30)
        ).count(),
        'ended_last_30_days': contracts.filter(
            end_date__gte=current_date - timedelta(days=30),
            end_date__lt=current_date
        ).count(),
    }
    
    return stats


# =============================================================================
# TEACHER STATISTICS
# =============================================================================

def get_teacher_statistics(filters=None):
    """
    Get comprehensive statistics for teachers
    
    Args:
        filters (dict): Optional filters
            - is_class_teacher: Filter by class teacher status
            - can_teach_online: Filter by online teaching capability
            - digital_literacy_level: Filter by digital literacy
            - department: Filter by department
    
    Returns:
        dict: Teacher statistics and analysis
    """
    from .models import Teacher
    
    teachers = Teacher.objects.select_related('staff', 'staff__primary_department').all()
    
    # Apply filters
    if filters:
        if filters.get('is_class_teacher') is not None:
            teachers = teachers.filter(is_class_teacher=filters['is_class_teacher'])
        if filters.get('can_teach_online') is not None:
            teachers = teachers.filter(can_teach_online=filters['can_teach_online'])
        if filters.get('digital_literacy_level'):
            teachers = teachers.filter(digital_literacy_level=filters['digital_literacy_level'])
        if filters.get('department'):
            teachers = teachers.filter(staff__primary_department_id=filters['department'])
    
    total_teachers = teachers.count()
    
    stats = {
        'total_teachers': total_teachers,
        'active_teachers': teachers.filter(staff__is_active=True).count(),
        'class_teachers': teachers.filter(is_class_teacher=True).count(),
        'non_class_teachers': teachers.filter(is_class_teacher=False).count(),
        
        # Digital capabilities
        'digital_capabilities': {
            'can_teach_online': teachers.filter(can_teach_online=True).count(),
            'cannot_teach_online': teachers.filter(can_teach_online=False).count(),
            'by_literacy_level': dict(
                teachers.values('digital_literacy_level')
                .annotate(count=Count('id'))
                .values_list('digital_literacy_level', 'count')
            ),
        },
        
        # Department distribution
        'by_department': dict(
            teachers.exclude(staff__primary_department__isnull=True)
            .values('staff__primary_department__name')
            .annotate(count=Count('id'))
            .order_by('-count')
            .values_list('staff__primary_department__name', 'count')
        ),
    }
    
    # Workload analysis
    if total_teachers > 0:
        workload_data = teachers.aggregate(
            avg_max_hours=Avg('max_hours_per_week'),
            avg_current_hours=Avg('current_teaching_load'),
            total_capacity=Sum('max_hours_per_week'),
            total_utilized=Sum('current_teaching_load')
        )
        
        stats['workload_analysis'] = {
            'average_max_hours_per_week': float(workload_data['avg_max_hours'] or 0),
            'average_current_hours_per_week': float(workload_data['avg_current_hours'] or 0),
            'total_teaching_capacity_hours': workload_data['total_capacity'] or 0,
            'total_hours_utilized': workload_data['total_utilized'] or 0,
            'overall_utilization_percentage': (
                (workload_data['total_utilized'] / workload_data['total_capacity'] * 100)
                if workload_data['total_capacity'] and workload_data['total_capacity'] > 0
                else 0
            ),
            'teachers_at_capacity': teachers.filter(
                current_teaching_load__gte=F('max_hours_per_week')
            ).count(),
            'teachers_overloaded': teachers.filter(
                current_teaching_load__gt=F('max_hours_per_week')
            ).count(),
            'teachers_underutilized': teachers.filter(
                current_teaching_load__lt=F('max_hours_per_week') * 0.5
            ).count(),
        }
    
    # Subject qualifications
    stats['subject_qualifications'] = {
        'teachers_with_qualified_subjects': teachers.filter(
            qualified_subjects__isnull=False
        ).distinct().count(),
        'teachers_without_qualified_subjects': teachers.filter(
            qualified_subjects__isnull=True
        ).count(),
    }
    
    # Class assignments
    stats['class_assignments'] = {
        'teachers_with_assigned_classes': teachers.filter(
            assigned_classes__isnull=False
        ).distinct().count(),
        'teachers_without_assigned_classes': teachers.exclude(
            assigned_classes__isnull=False
        ).count(),
    }
    
    # Most loaded teachers
    most_loaded = teachers.order_by('-current_teaching_load')[:10]
    stats['most_loaded_teachers'] = [
        {
            'id': t.id,
            'name': t.staff.full_name(),
            'current_load': t.current_teaching_load,
            'max_hours': t.max_hours_per_week,
            'utilization_percentage': (
                (t.current_teaching_load / t.max_hours_per_week * 100)
                if t.max_hours_per_week > 0
                else 0
            ),
            'department': t.staff.primary_department.name if t.staff.primary_department else 'N/A',
        }
        for t in most_loaded
    ]
    
    # Available capacity
    available_teachers = teachers.filter(
        staff__is_active=True,
        current_teaching_load__lt=F('max_hours_per_week')
    )
    
    stats['available_capacity'] = {
        'teachers_with_capacity': available_teachers.count(),
        'total_available_hours': sum([
            t.max_hours_per_week - t.current_teaching_load
            for t in available_teachers
        ]),
    }
    
    return stats


# =============================================================================
# COMPREHENSIVE HR DASHBOARD STATISTICS
# =============================================================================

def get_hr_dashboard_statistics(filters=None):
    """
    Get comprehensive dashboard statistics across all HR models
    
    Args:
        filters (dict): Optional filters to apply across models
    
    Returns:
        dict: Comprehensive HR dashboard statistics
    """
    dashboard = {
        'generated_at': timezone.now(),
        'staff': get_staff_statistics(filters),
        'departments': get_department_statistics(filters),
        'designations': get_designation_statistics(filters),
        'contracts': get_contract_statistics(filters),
        'teachers': get_teacher_statistics(filters),
    }
    
    # Overall summary
    dashboard['summary'] = {
        'total_staff': dashboard['staff']['total_staff'],
        'active_staff': dashboard['staff']['active_staff'],
        'total_departments': dashboard['departments']['total_departments'],
        'total_designations': dashboard['designations']['total_designations'],
        'active_contracts': dashboard['contracts']['by_status'].get('ACTIVE', 0),
        'total_teachers': dashboard['teachers']['total_teachers'],
        'contracts_expiring_soon': dashboard['contracts']['active_contracts']['expiring_30_days'],
    }
    
    # Key metrics
    dashboard['key_metrics'] = {
        'employee_to_department_ratio': (
            dashboard['staff']['active_staff'] / dashboard['departments']['active_departments']
            if dashboard['departments']['active_departments'] > 0
            else 0
        ),
        'teaching_staff_percentage': (
            dashboard['staff']['staff_categories']['teaching_staff'] / dashboard['staff']['total_staff'] * 100
            if dashboard['staff']['total_staff'] > 0
            else 0
        ),
        'average_years_of_service': (
            dashboard['staff']['service_analysis']['average_service_years']
            if 'service_analysis' in dashboard['staff']
            else 0
        ),
    }
    
    # Alerts and attention items
    dashboard['alerts'] = {
        'contracts_expiring_30_days': dashboard['contracts']['active_contracts']['expiring_30_days'],
        'overloaded_teachers': dashboard['teachers']['workload_analysis']['teachers_overloaded'] if 'workload_analysis' in dashboard['teachers'] else 0,
        'departments_without_head': dashboard['departments']['departments_needing_attention']['no_head'],
        'approaching_retirement': dashboard['staff']['retirement_analysis']['approaching_retirement_5_years'],
    }
    
    return dashboard


# =============================================================================
# EXPORT HELPER FUNCTIONS
# =============================================================================

def format_hr_statistics_for_export(stats, format_type='dict'):
    """
    Format HR statistics for export (Excel, PDF, JSON)
    
    Args:
        stats (dict): Statistics dictionary
        format_type (str): Output format ('dict', 'flat', 'hierarchical')
    
    Returns:
        dict or list: Formatted statistics
    """
    if format_type == 'flat':
        # Flatten nested dictionaries
        flat_stats = {}
        
        def flatten(d, parent_key=''):
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    flatten(v, new_key)
                else:
                    flat_stats[new_key] = v
        
        flatten(stats)
        return flat_stats
    
    elif format_type == 'hierarchical':
        # Keep hierarchical structure but ensure all values are serializable
        def clean_values(d):
            cleaned = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    cleaned[k] = clean_values(v)
                elif isinstance(v, (list, tuple)):
                    cleaned[k] = [clean_values(item) if isinstance(item, dict) else item for item in v]
                else:
                    # Convert to JSON-serializable types
                    if hasattr(v, 'isoformat'):
                        cleaned[k] = v.isoformat()
                    elif isinstance(v, Decimal):
                        cleaned[k] = float(v)
                    else:
                        cleaned[k] = v
            return cleaned
        
        return clean_values(stats)
    
    return stats