# uniforms/urls.py
from django.urls import path
from . import views, htmx_views

app_name = 'boarding'

urlpatterns = [

    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Dormitories
    path('htmx/dormitories/search/', htmx_views.dormitory_search, name='dormitory_search'),
    path('htmx/dormitories/quick-stats/', htmx_views.dormitory_quick_stats, name='dormitory_quick_stats'),

    # Boarding Enrollments
    path('htmx/enrollments/search/', htmx_views.boarding_enrollment_search, name='enrollment_search'),
    path('htmx/enrollments/quick-stats/', htmx_views.boarding_enrollment_quick_stats, name='enrollment_quick_stats'),


]
