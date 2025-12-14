# academics/views.py

from django.shortcuts import render, redirect
from .models import AcademicLevel
from .forms import AcademicLevelForm

# Create your views here.
def academic_level_list(request):
    """List all academic levels with comprehensive statistics"""

    levels = AcademicLevel.objects.all().order_by('order')
    
    # Prepare context with all required data
    context = {
        'levels': levels,
    }
    
    return render(request, 'levels/list.html', context)

def academic_level_create(request):
    """Create a new academic level"""
    if request.method == 'POST':
        form = AcademicLevelForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('academics:academic_level_list')  
    else:
        form = AcademicLevelForm()
    
    context = {'form': form}
    return render(request, 'levels/form.html', context)
