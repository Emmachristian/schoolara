# In academics/urls.py

from django.urls import path, include
from . import views
from . import ajax_views

app_name = 'academics'

urlpatterns = [
    path('levels/', views.academic_level_list, name='academic_level_list'),
    path('levels/create/', views.academic_level_create, name='academic_level_create'),

     # Ajax End points
     path("ajax/students/search/", ajax_views.academic_level_search, name='academic_level_search'),
]
