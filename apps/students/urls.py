# students/urls.py

from . import views, htmx_views
from django.urls import path

app_name = 'students'

urlpatterns = [
     path("list/", views.student_list, name="student_list"),
     path("create/", views.student_create, name="student_create"),
     path("<uuid:pk>/update/", views.student_edit, name="student_edit"),
     path("<uuid:pk>/delete/", views.student_delete, name="student_delete"),
     path("<uuid:pk>/profile/", views.student_profile, name="student_profile"),

     # Export URLs
     path('export/excel/', views.export_students_excel, name='export_excel'),
     path('export/pdf/', views.export_students_pdf, name='export_pdf'),

     # =============================================================================
     # HTMX SEARCH ENDPOINTS
     # =============================================================================

     # Students
     path('htmx/students/search/', htmx_views.student_search, name='student_search'),
     path('htmx/students/quick-stats/', htmx_views.student_quick_stats, name='student_quick_stats'),

     # Guardians
     path('htmx/guardians/search/', htmx_views.guardian_search, name='guardian_search'),
     path('htmx/guardians/quick-stats/', htmx_views.guardian_quick_stats, name='guardian_quick_stats'),

     # Student-Guardian Relationships
     path('htmx/relationships/search/', htmx_views.student_guardian_search, name='relationship_search'),

     # Sibling Relationships
     path('htmx/siblings/search/', htmx_views.sibling_search, name='sibling_search'),

     # Enrollment Status History
     path('htmx/enrollment-history/search/', htmx_views.enrollment_status_history_search, name='enrollment_history_search'),
     path('htmx/enrollment-history/quick-stats/', htmx_views.enrollment_status_quick_stats, name='enrollment_status_quick_stats'),

     # Medical Alerts
     path('htmx/medical-alerts/quick-stats/', htmx_views.medical_alerts_quick_stats, name='medical_alerts_quick_stats'),

]
