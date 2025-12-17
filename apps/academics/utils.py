# academics/utils.py

from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import AcademicSession, Holiday
from utils.models import SchoolConfiguration

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
# BREAK MANAGEMENT UTILITIES
# =============================================================================

def analyze_break_gaps(year_filter=None, include_statistics=True):
    """
    Comprehensive analysis of gaps between sessions
    
    Args:
        year_filter (str, optional): Filter by academic year
        include_statistics (bool): Include statistical analysis
        
    Returns:
        dict: Analysis results with gaps, statistics, and recommendations
    """
    analysis = {
        'gaps': [],
        'statistics': {} if include_statistics else None,
        'recommendations': [],
        'created_breaks': [],
        'missing_breaks': []
    }
    
    try:
        sessions = AcademicSession.objects.order_by('start_date', 'term_number')
        if year_filter:
            sessions = sessions.filter(year_name__icontains=year_filter)
        
        config = SchoolConfiguration.get_cached_instance()
        minimum_break_days = config.minimum_break_days if config else 1
        
        for session in sessions:
            next_sessions = sessions.filter(
                start_date__gt=session.end_date
            ).order_by('start_date')
            
            if next_sessions.exists():
                next_session = next_sessions.first()
                
                gap_start = session.end_date + timedelta(days=1)
                gap_end = next_session.start_date - timedelta(days=1)
                
                if gap_start <= gap_end:
                    gap_days = (gap_end - gap_start).days + 1
                    
                    # Check if break exists
                    existing_break = Holiday.objects.filter(
                        holiday_type='BREAK',
                        start_date=gap_start,
                        end_date=gap_end
                    ).first()
                    
                    # Determine break type
                    break_type = AcademicSession._determine_break_type_enhanced(session, next_session, config)
                    
                    gap_info = {
                        'start_date': gap_start,
                        'end_date': gap_end,
                        'duration_days': gap_days,
                        'previous_session': {
                            'id': session.id,
                            'name': str(session),
                            'year_name': session.year_name,
                            'term_number': session.term_number
                        },
                        'next_session': {
                            'id': next_session.id,
                            'name': str(next_session),
                            'year_name': next_session.year_name,
                            'term_number': next_session.term_number
                        },
                        'break_exists': existing_break is not None,
                        'existing_break': {
                            'id': existing_break.id,
                            'name': existing_break.name,
                            'break_type': existing_break.break_type
                        } if existing_break else None,
                        'meets_minimum': gap_days >= minimum_break_days,
                        'suggested_name': AcademicSession._generate_break_name_enhanced(
                            session, next_session, break_type
                        ),
                        'break_type': break_type
                    }
                    
                    analysis['gaps'].append(gap_info)
                    
                    if not existing_break and gap_days >= minimum_break_days:
                        analysis['missing_breaks'].append(gap_info)
                    elif existing_break:
                        analysis['created_breaks'].append(gap_info)
        
        # Generate recommendations
        if analysis['missing_breaks']:
            analysis['recommendations'].append({
                'type': 'create_missing_breaks',
                'priority': 'medium',
                'count': len(analysis['missing_breaks']),
                'description': f"Create {len(analysis['missing_breaks'])} missing break records",
                'action': 'sync_breaks'
            })
        
        # Check for very short gaps
        short_gaps = [g for g in analysis['gaps'] if g['duration_days'] < minimum_break_days]
        if short_gaps:
            analysis['recommendations'].append({
                'type': 'review_short_gaps',
                'priority': 'low',
                'count': len(short_gaps),
                'description': f"Review {len(short_gaps)} gaps shorter than minimum {minimum_break_days} days",
                'action': 'adjust_minimum_or_sessions'
            })
        
        # Check for very long gaps
        long_gaps = [g for g in analysis['gaps'] if g['duration_days'] > 90]
        if long_gaps:
            analysis['recommendations'].append({
                'type': 'review_long_gaps',
                'priority': 'medium',
                'count': len(long_gaps),
                'description': f"Review {len(long_gaps)} gaps longer than 3 months",
                'action': 'consider_splitting_breaks'
            })
        
        # Statistics
        if include_statistics and analysis['gaps']:
            gap_durations = [g['duration_days'] for g in analysis['gaps']]
            analysis['statistics'] = {
                'total_gaps': len(analysis['gaps']),
                'gaps_with_breaks': len(analysis['created_breaks']),
                'gaps_without_breaks': len(analysis['missing_breaks']),
                'average_gap_duration': sum(gap_durations) / len(gap_durations),
                'shortest_gap': min(gap_durations),
                'longest_gap': max(gap_durations),
                'total_break_days': sum(gap_durations),
                'break_coverage_percentage': (
                    len(analysis['created_breaks']) / len(analysis['gaps']) * 100
                ) if analysis['gaps'] else 0
            }
        
    except Exception as e:
        analysis['error'] = str(e)
    
    return analysis


def sync_breaks_with_preview(scope='all', year_filter=None, force_recreation=False, dry_run=True):
    """
    Synchronize breaks with preview capability
    
    Args:
        scope (str): 'all', 'year', or 'missing_only'
        year_filter (str, optional): Academic year filter
        force_recreation (bool): Force recreation of existing breaks
        dry_run (bool): Preview changes without applying them
        
    Returns:
        dict: Preview/results of sync operation
    """
    result = {
        'success': False,
        'dry_run': dry_run,
        'operations': [],
        'statistics': {},
        'errors': []
    }
    
    try:
        # Get current analysis
        analysis = analyze_break_gaps(year_filter)
        
        operations = []
        
        if scope in ['all', 'missing_only']:
            # Create missing breaks
            for gap in analysis['missing_breaks']:
                operation = {
                    'type': 'create_break',
                    'gap': gap,
                    'break_name': gap['suggested_name'],
                    'break_type': gap['break_type'],
                    'start_date': gap['start_date'],
                    'end_date': gap['end_date'],
                    'duration_days': gap['duration_days']
                }
                operations.append(operation)
        
        if scope == 'all' and force_recreation:
            # Recreate existing breaks
            for gap in analysis['created_breaks']:
                operations.append({
                    'type': 'delete_break',
                    'break_id': gap['existing_break']['id'],
                    'break_name': gap['existing_break']['name']
                })
                operations.append({
                    'type': 'create_break',
                    'gap': gap,
                    'break_name': gap['suggested_name'],
                    'break_type': gap['break_type'],
                    'start_date': gap['start_date'],
                    'end_date': gap['end_date'],
                    'duration_days': gap['duration_days']
                })
        
        result['operations'] = operations
        result['statistics'] = {
            'total_operations': len(operations),
            'creates': len([op for op in operations if op['type'] == 'create_break']),
            'deletes': len([op for op in operations if op['type'] == 'delete_break']),
            'total_break_days': sum(
                op.get('duration_days', 0) 
                for op in operations 
                if op['type'] == 'create_break'
            )
        }
        
        # Execute operations if not dry run
        if not dry_run:
            with transaction.atomic():
                created_breaks = []
                deleted_breaks = []
                
                for operation in operations:
                    try:
                        if operation['type'] == 'delete_break':
                            Holiday.objects.filter(id=operation['break_id']).delete()
                            deleted_breaks.append(operation['break_id'])
                        
                        elif operation['type'] == 'create_break':
                            gap = operation['gap']
                            break_holiday = Holiday.objects.create(
                                name=operation['break_name'],
                                holiday_type='BREAK',
                                break_type=operation['break_type'],
                                start_date=operation['start_date'],
                                end_date=operation['end_date'],
                                previous_session_id=gap['previous_session']['id'],
                                next_session_id=gap['next_session']['id'],
                                description=AcademicSession._generate_break_description(
                                    AcademicSession.objects.get(id=gap['previous_session']['id']),
                                    AcademicSession.objects.get(id=gap['next_session']['id']),
                                    operation['break_type']
                                )
                            )
                            created_breaks.append(break_holiday.id)
                            
                    except Exception as e:
                        result['errors'].append({
                            'operation': operation,
                            'error': str(e)
                        })
                
                result['statistics']['created_breaks'] = created_breaks
                result['statistics']['deleted_breaks'] = deleted_breaks
        
        result['success'] = len(result['errors']) == 0
        
    except Exception as e:
        result['errors'].append({'general_error': str(e)})
    
    return result


def get_break_recommendations(config=None):
    """
    Get intelligent recommendations for break management
    
    Args:
        config (SchoolConfiguration, optional): School configuration
        
    Returns:
        list: List of recommendation dictionaries
    """
    if config is None:
        config = SchoolConfiguration.get_cached_instance()
    
    recommendations = []
    
    try:
        # Check configuration status
        if not config:
            recommendations.append({
                'type': 'setup',
                'priority': 'critical',
                'title': 'School Configuration Missing',
                'description': 'Set up school configuration to enable intelligent break management',
                'action': 'configure_school',
                'estimated_time': '15 minutes'
            })
            return recommendations
        
        # Check break auto-creation setting
        if not config.auto_create_breaks:
            recommendations.append({
                'type': 'configuration',
                'priority': 'high',
                'title': 'Enable Auto-Break Creation',
                'description': 'Turn on automatic break detection to streamline session management',
                'action': 'enable_auto_breaks',
                'estimated_time': '2 minutes'
            })
        
        # Analyze current break coverage
        analysis = analyze_break_gaps(include_statistics=True)
        
        if analysis.get('missing_breaks'):
            count = len(analysis['missing_breaks'])
            recommendations.append({
                'type': 'action',
                'priority': 'medium',
                'title': f'Create {count} Missing Breaks',
                'description': f'Found {count} gaps between sessions without break records',
                'action': 'sync_missing_breaks',
                'estimated_time': f'{count * 2} minutes',
                'details': analysis['missing_breaks'][:3]  # Show first 3
            })
        
        # Check for system-specific recommendations
        period_count = config.get_period_count()
        
        if period_count == 1:  # Year-long programs
            recommendations.append({
                'type': 'suggestion',
                'priority': 'low',
                'title': 'Consider Adding Mid-Year Breaks',
                'description': 'Year-long programs benefit from mid-year reading weeks or intensive periods',
                'action': 'add_manual_breaks',
                'estimated_time': '10 minutes'
            })
        
        elif period_count > 8:  # Intensive systems
            recommendations.append({
                'type': 'review',
                'priority': 'medium',
                'title': 'Review Break Duration Settings',
                'description': f'With {period_count} periods per year, consider shorter minimum break periods',
                'action': 'adjust_break_settings',
                'estimated_time': '5 minutes'
            })
        
        # Check for quality issues
        if analysis.get('statistics'):
            stats = analysis['statistics']
            
            if stats.get('break_coverage_percentage', 0) < 50:
                recommendations.append({
                    'type': 'quality',
                    'priority': 'medium',
                    'title': 'Low Break Coverage',
                    'description': f"Only {stats['break_coverage_percentage']:.1f}% of gaps have break records",
                    'action': 'improve_break_coverage',
                    'estimated_time': '20 minutes'
                })
            
            if stats.get('longest_gap', 0) > 120:
                recommendations.append({
                    'type': 'review',
                    'priority': 'low',
                    'title': 'Review Extended Breaks',
                    'description': f"Longest break is {stats['longest_gap']} days - consider splitting",
                    'action': 'review_long_breaks',
                    'estimated_time': '15 minutes'
                })
        
        # Seasonal recommendations
        today = timezone.now().date()
        month = today.month
        
        if month in [6, 7, 8]:  # Summer months
            recommendations.append({
                'type': 'seasonal',
                'priority': 'low',
                'title': 'Plan Next Academic Year',
                'description': 'Summer is a good time to set up sessions and breaks for the next academic year',
                'action': 'plan_next_year',
                'estimated_time': '30 minutes'
            })
        
        elif month in [11, 12]:  # End of year
            recommendations.append({
                'type': 'seasonal',
                'priority': 'medium',
                'title': 'Prepare for Year-End',
                'description': 'Review current year completions and plan year-end breaks',
                'action': 'prepare_year_end',
                'estimated_time': '20 minutes'
            })
        
    except Exception as e:
        recommendations.append({
            'type': 'error',
            'priority': 'high',
            'title': 'Analysis Error',
            'description': f'Error analyzing breaks: {str(e)}',
            'action': 'check_system_health',
            'estimated_time': '10 minutes'
        })
    
    # Sort by priority
    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 4))
    
    return recommendations