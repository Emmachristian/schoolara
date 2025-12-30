# students/urls.py

"""
URL Configuration for Students Module
Organized into three main sections:
1. Regular Views (views.py) - Full page loads and redirects
2. Modal Views (modal_views.py) - HTMX modal actions without page refresh
3. HTMX Views (htmx_views.py) - Dynamic search and filtering

All URLs use UUID primary keys for security
"""

from django.urls import path
from . import views, htmx_views, modal_views

app_name = 'students'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('', views.students_dashboard, name='dashboard'),
    
    # =============================================================================
    # STUDENTS
    # =============================================================================
    # Regular Views
    path('students/', views.student_list, name='student_list'),
    path('students/create/', views.student_create, name='student_create'),  # Wizard view
    path('students/<uuid:pk>/', views.student_profile, name='student_profile'),
    path('students/<uuid:pk>/edit/', views.student_edit, name='student_edit'),
    path('students/<uuid:pk>/activate/', views.student_activate, name='student_activate'),
    path('students/<uuid:pk>/suspend/', views.student_suspend, name='student_suspend'),
    path('students/print/', views.student_print_view, name='student_print_view'),
    
    # Modal Views
    path('students/<uuid:pk>/modal/delete/', modal_views.student_delete_modal, name='student_delete_modal'),
    path('students/<uuid:pk>/modal/delete/submit/', modal_views.student_delete, name='student_delete'),
    path('students/<uuid:pk>/modal/status-change/', modal_views.student_status_change_modal, name='student_status_change_modal'),
    path('students/<uuid:pk>/modal/status-change/submit/', modal_views.student_status_change, name='student_status_change'),
    path('students/<uuid:pk>/modal/add-guardian/', modal_views.add_guardian_modal, name='add_guardian_modal'),
    path('students/<uuid:pk>/modal/add-guardian/submit/', modal_views.add_guardian, name='add_guardian'),
    path('students/<uuid:pk>/modal/add-sibling/', modal_views.add_sibling_modal, name='add_sibling_modal'),
    path('students/<uuid:pk>/modal/add-sibling/submit/', modal_views.add_sibling, name='add_sibling'),
    path('students/modal/bulk-status-change/', modal_views.bulk_status_change_modal, name='bulk_status_change_modal'),
    path('students/modal/bulk-status-change/submit/', modal_views.bulk_status_change, name='bulk_status_change'),
    
    # HTMX Views
    path('students/htmx/search/', htmx_views.student_search, name='student_search'),
    path('students/htmx/quick-stats/', htmx_views.student_quick_stats, name='student_quick_stats'),
    path('students/htmx/medical-alerts/', htmx_views.medical_alerts_quick_stats, name='medical_alerts_quick_stats'),
    
    # =============================================================================
    # GUARDIANS
    # =============================================================================
    # Regular Views
    path('guardians/', views.guardian_list, name='guardian_list'),
    path('guardians/create/', views.guardian_create, name='guardian_create'),
    path('guardians/<uuid:pk>/', views.guardian_profile, name='guardian_profile'),
    path('guardians/<uuid:pk>/edit/', views.guardian_edit, name='guardian_edit'),
    path('guardians/print/', views.guardian_print_view, name='guardian_print_view'),
    
    # Modal Views
    path('guardians/<uuid:pk>/modal/delete/', modal_views.guardian_delete_modal, name='guardian_delete_modal'),
    path('guardians/<uuid:pk>/modal/delete/submit/', modal_views.guardian_delete, name='guardian_delete'),
    
    # HTMX Views
    path('guardians/htmx/search/', htmx_views.guardian_search, name='guardian_search'),
    path('guardians/htmx/quick-stats/', htmx_views.guardian_quick_stats, name='guardian_quick_stats'),
    
    # =============================================================================
    # STUDENT-GUARDIAN RELATIONSHIPS
    # =============================================================================
    # Regular Views
    path('relationships/', views.student_guardian_list, name='relationship_list'),
    path('relationships/create/', views.student_guardian_create, name='relationship_create'),
    path('relationships/<uuid:pk>/', views.student_guardian_detail, name='relationship_detail'),
    path('relationships/<uuid:pk>/edit/', views.student_guardian_edit, name='relationship_edit'),
    
    # Modal Views
    path('relationships/<uuid:pk>/modal/delete/', modal_views.guardian_relationship_delete_modal, name='guardian_relationship_delete_modal'),
    path('relationships/<uuid:pk>/modal/delete/submit/', modal_views.guardian_relationship_delete, name='guardian_relationship_delete'),
    
    # HTMX Views
    path('relationships/htmx/search/', htmx_views.student_guardian_search, name='student_guardian_search'),
    
    # =============================================================================
    # SIBLING RELATIONSHIPS
    # =============================================================================
    # Regular Views
    path('siblings/', views.sibling_list, name='sibling_list'),
    path('siblings/create/', views.sibling_create, name='sibling_create'),
    path('siblings/<uuid:pk>/', views.sibling_detail, name='sibling_detail'),
    path('siblings/<uuid:pk>/edit/', views.sibling_edit, name='sibling_edit'),
    
    # Modal Views
    path('siblings/<uuid:pk>/modal/delete/', modal_views.sibling_relationship_delete_modal, name='sibling_relationship_delete_modal'),
    path('siblings/<uuid:pk>/modal/delete/submit/', modal_views.sibling_relationship_delete, name='sibling_relationship_delete'),
    
    # HTMX Views
    path('siblings/htmx/search/', htmx_views.sibling_search, name='sibling_search'),
    
    # =============================================================================
    # ENROLLMENT STATUS HISTORY
    # =============================================================================
    # Regular Views
    path('enrollment-history/', views.enrollment_history_list, name='enrollment_history_list'),
    path('enrollment-history/<uuid:pk>/', views.enrollment_history_detail, name='enrollment_history_detail'),
    
    # HTMX Views
    path('enrollment-history/htmx/search/', htmx_views.enrollment_status_history_search, name='enrollment_history_search'),
    path('enrollment-history/htmx/quick-stats/', htmx_views.enrollment_status_quick_stats, name='enrollment_status_quick_stats'),
    
    # =============================================================================
    # REPORTS & ANALYTICS
    # =============================================================================
    path('reports/', views.student_reports_dashboard, name='reports_dashboard'),
    path('reports/demographics/', views.demographics_report, name='demographics_report'),
    path('reports/health/', views.health_report, name='health_report'),
    path('reports/guardians/', views.guardian_report, name='guardian_report'),
    path('reports/siblings/', views.sibling_report, name='sibling_report'),
    path('reports/birthdays/', views.birthday_report, name='birthday_report'),
    
    # Export endpoints
    path('export/students/excel/', views.export_students_excel, name='export_students_excel'),
    path('export/students/pdf/', views.export_students_pdf, name='export_students_pdf'),
    path('export/guardians/excel/', views.export_guardians_excel, name='export_guardians_excel'),
    path('export/guardians/pdf/', views.export_guardians_pdf, name='export_guardians_pdf'),
]