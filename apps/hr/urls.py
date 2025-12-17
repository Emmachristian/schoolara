# hr/urls.py
from django.urls import path
from . import views, ajax_views

app_name = 'hr'

urlpatterns = [
    # =============================================================================
    # DASHBOARD
    # =============================================================================
    path('dashboard/', views.hr_dashboard, name='hr_dashboard'),
    
    # =============================================================================
    # STAFF URLS
    # =============================================================================
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/create/', views.staff_create, name='staff_create'),
    path('staff/create-wizard/', views.staff_create_wizard, name='staff_create_wizard'),
    path('staff/<uuid:pk>/', views.staff_profile, name='staff_profile'),
    path('staff/<uuid:pk>/update/', views.staff_update, name='staff_update'),
    path('staff/<uuid:pk>/delete/', views.staff_delete, name='staff_delete'),
    
    # =============================================================================
    # DEPARTMENT URLS
    # =============================================================================
    path('departments/', views.department_list, name='department_list'),
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<uuid:pk>/', views.department_detail, name='department_detail'),
    path('departments/<uuid:pk>/update/', views.department_update, name='department_update'),
    path('departments/<uuid:pk>/delete/', views.department_delete, name='department_delete'),
    
    # =============================================================================
    # DESIGNATION URLS
    # =============================================================================
    path('designations/', views.designation_list, name='designation_list'),
    path('designations/create/', views.designation_create, name='designation_create'),
    path('designations/<uuid:pk>/', views.designation_detail, name='designation_detail'),
    path('designations/<uuid:pk>/update/', views.designation_update, name='designation_update'),
    path('designations/<uuid:pk>/delete/', views.designation_delete, name='designation_delete'),
    
    # =============================================================================
    # CONTRACT TYPE URLS
    # =============================================================================
    path('contract-types/', views.contract_type_list, name='contract_type_list'),
    path('contract-types/create/', views.contract_type_create, name='contract_type_create'),
    path('contract-types/<uuid:pk>/', views.contract_type_detail, name='contract_type_detail'),
    path('contract-types/<uuid:pk>/update/', views.contract_type_update, name='contract_type_update'),
    path('contract-types/<uuid:pk>/delete/', views.contract_type_delete, name='contract_type_delete'),
    
    # =============================================================================
    # CONTRACT URLS
    # =============================================================================
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/create/', views.contract_create, name='contract_create'),
    path('contracts/<uuid:pk>/', views.contract_detail, name='contract_detail'),
    path('contracts/<uuid:pk>/update/', views.contract_update, name='contract_update'),
    path('contracts/<uuid:pk>/delete/', views.contract_delete, name='contract_delete'),
    
    # =============================================================================
    # TEACHER URLS
    # =============================================================================
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/create/', views.teacher_create, name='teacher_create'),
    path('teachers/<uuid:pk>/update/', views.teacher_update, name='teacher_update'),
    path('teachers/<uuid:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    
    # =============================================================================
    # AJAX SEARCH ENDPOINTS
    # =============================================================================
    path('ajax/staff/search/', ajax_views.staff_search, name='staff_search'),
    path('ajax/staff/<uuid:staff_id>/quick-info/', ajax_views.get_staff_quick_info, name='get_staff_quick_info'),
    path('ajax/staff/update-profile-picture/', ajax_views.update_staff_profile_picture, name='update_staff_profile_picture'),
    
    path('ajax/teachers/search/', ajax_views.teacher_search, name='teacher_search'),
    path('ajax/contracts/search/', ajax_views.contract_search, name='contract_search'),
    path('ajax/contract-types/search/', ajax_views.contract_type_search, name='contract_type_search'),
    path('ajax/departments/search/', ajax_views.department_search, name='department_search'),
    path('ajax/designations/search/', ajax_views.designation_search, name='designation_search'),
    
    # =============================================================================
    # EXPORT ENDPOINTS
    # =============================================================================
    # Staff
    path('staff/export/excel/', views.export_staff_excel, name='export_staff_excel'),
    path('staff/export/pdf/', views.export_staff_pdf, name='export_staff_pdf'),
    
    # Additional export endpoints can be added as needed:
    # path('departments/export/excel/', views.export_departments_excel, name='export_departments_excel'),
    # path('contracts/export/excel/', views.export_contracts_excel, name='export_contracts_excel'),
    # path('teachers/export/excel/', views.export_teachers_excel, name='export_teachers_excel'),
]