# utils/utils.py

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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