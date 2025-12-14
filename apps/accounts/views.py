# accounts/views.py
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
import json
from django.views.decorators.cache import never_cache
from .forms import LoginForm
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages

def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('users:login')

@never_cache
def login_view(request):
    """Handle user login - function-based alternative"""
    
    # Redirect if already authenticated
    if request.user.is_authenticated:
        return redirect('core:home')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data.get('remember_me', False)
            
            # Authenticate user
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Handle remember me
                    if not remember_me:
                        request.session.set_expiry(0)
                    else:
                        request.session.set_expiry(1209600)
                    
                    # Handle next parameter
                    next_url = request.GET.get('next') or request.POST.get('next')
                    if next_url:
                        return redirect(next_url)
                    
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                    return redirect('core:home')
                else:
                    messages.error(request, "Your account has been disabled. Please contact support.")
            else:
                messages.error(request, "Invalid email or password. Please try again.")
                form.add_error(None, "Invalid email or password.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form})

@login_required
@require_POST
def save_theme_preference(request):
    try:
        data = json.loads(request.body)
        setting = data.get('setting')
        value = data.get('value')
        
        profile = request.user.userprofile
        
        if setting == 'fixed_header':
            profile.fixed_header = value == 'true'
        elif setting == 'fixed_sidebar':
            profile.fixed_sidebar = value == 'true'
        elif setting == 'fixed_footer':
            profile.fixed_footer = value == 'true'
        elif setting == 'header_class':
            profile.header_class = value
        elif setting == 'sidebar_class':
            profile.sidebar_class = value
        elif setting == 'page_tabs_style':
            profile.page_tabs_style = value
        elif setting == 'theme_color':
            profile.theme_color = value
        
        profile.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})