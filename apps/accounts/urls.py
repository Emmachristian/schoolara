# In accounts/urls.py

from django.urls import path
from . import views, ajax_views

app_name = 'accounts'

urlpatterns = [

    path('', views.login_view, name='login'),  # root URL points to login_view
    path('logout/', views.logout_view, name='logout'),
    
    # FIXED: Correct URL pattern for theme settings
    path('account/settings/', views.user_account_settings, name='user_account_settings'),
    path('save-theme-preference/', views.save_theme_preference, name='save_theme_preference'),

    path('ajax/update-profile-picture/', ajax_views.update_profile_picture, name='update_profile_picture'),
]