# academics/forms.py

from django import forms
from .models import AcademicLevel

class AcademicLevelForm(forms.ModelForm):
    """Form for creating and updating academic levels"""
    
    class Meta:
        model = AcademicLevel
        fields = [
            'name', 'code', 'description', 'order', 'next_level',
            'has_sections', 'is_active','is_graduation_level', 
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'next_level': forms.Select(attrs={'class': 'form-select'}),
            'has_sections': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_graduation_level': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        

