# academics/views.py
from django.http import JsonResponse
from django.db.models import Q
from .models import AcademicLevel

def academic_level_search(request):
    """
    AJAX view to return filtered academic levels as JSON.
    """
    query = request.GET.get('q', '').strip()
    is_active = request.GET.get('is_active', '')
    is_graduation_level = request.GET.get('is_graduation_level', '')

    levels = AcademicLevel.objects.all()

    if query:
        # Split query into terms and search in name or code
        terms = query.split()
        q_objects = Q()
        for term in terms:
            q_objects &= Q(name__icontains=term) | Q(code__icontains=term)
        levels = levels.filter(q_objects)

    if is_active != '':
        levels = levels.filter(is_active=(is_active.lower() == 'true'))

    if is_graduation_level != '':
        levels = levels.filter(is_graduation_level=(is_graduation_level.lower() == 'true'))

    level_list = []
    for l in levels:
        level_list.append({
            'id': l.id,
            'name': l.name,
            'code': l.code,
            'order': l.order,
            'next_level': l.next_level.name if l.next_level else '',
            'has_sections': l.has_sections,
            'is_active': l.is_active,
            'is_graduation_level': l.is_graduation_level,
        })

    return JsonResponse({'levels': level_list})
