# accounts/views.py
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
import json
from django.views.decorators.cache import never_cache
from .forms import LoginForm, UserProfileForm
from .models import UserProfile
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages

def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('accounts:login')

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
    """Save user theme preferences via AJAX"""
    try:
        data = json.loads(request.body)
        setting = data.get('setting')
        value = data.get('value')
        
        if not setting:
            return JsonResponse({'success': False, 'error': 'Setting required'})
        
        profile = request.user.userprofile
        
        # Boolean settings
        if setting in ['fixed_header', 'fixed_sidebar', 'fixed_footer']:
            bool_value = value.lower() == 'true' if isinstance(value, str) else bool(value)
            setattr(profile, setting, bool_value)
        
        # String settings
        elif setting in ['header_class', 'sidebar_class', 'page_tabs_style', 'theme_color']:
            setattr(profile, setting, value or '')
        
        else:
            return JsonResponse({'success': False, 'error': f'Unknown setting: {setting}'})
        
        profile.save()
        return JsonResponse({
            'success': True,
            'message': f'{setting} updated',
            'setting': setting,
            'value': value
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@login_required
def user_account_settings(request):
    """
    View for user to edit their account settings and profile
    """
    try:
        # Get the user's profile
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        messages.error(request, 'User profile not found.')
        return redirect('core:home')  # Change 'home' to your home page URL name
    
    if request.method == 'POST':
        form = UserProfileForm(
            request.POST, 
            request.FILES, 
            instance=user_profile,
            user=request.user
        )
        
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('accounts:user_account_settings')  # Redirect to same page to show updated data
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=user_profile, user=request.user)
    
    context = {
        'form': form,
        'user_profile': user_profile,
    }
    
    return render(request, 'user_account_settings.html', context)