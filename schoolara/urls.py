"""
URL configuration for schoolara project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # Core app - homepage / landing dashboard
    path('core/', include(('core.urls', 'core'), namespace='core')),

    # Accounts app - login, register, profiles
    path('', include(('accounts.urls', 'accounts'), namespace='accounts')),

    # Students app
    path('students/', include(('students.urls', 'students'), namespace='students')),

    # Boarding app 
    path('boarding/', include(('boarding.urls', 'boarding'), namespace='boarding')),

    # Student Discipline app
    path('discipline/', include(('discipline.urls', 'discipline'), namespace='discipline')),

    # Documents app
    path('documents/', include(('documents.urls', 'documents'), namespace='documents')),

    # Academics app - sessions, classes, subjects
    path('academics/', include(('academics.urls', 'academics'), namespace='academics')),

    # Exams app
    path('exams/', include(('exams.urls', 'exams'), namespace='exams')),

    # HR / Staff app
    path('hr/', include(('hr.urls', 'hr'), namespace='hr')),

    # Fees app - student invoices/payments
    path('fees/', include(('fees.urls', 'fees'), namespace='fees')),

    # Finance app - expenses, budgets
    path('finance/', include(('finance.urls', 'finance'), namespace='finance')),

    # Inventory app
    path('inventory/', include(('inventory.urls', 'inventory'), namespace='inventory')),

    # Uniforms app
    path('uniforms/', include(('uniforms.urls', 'uniforms'), namespace='uniforms')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
