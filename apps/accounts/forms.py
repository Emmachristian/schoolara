# accounts/forms.py
from django import forms
from .models import UserProfile
from django.contrib.auth.models import User
from django_countries.fields import CountryField
from zoneinfo import available_timezones

class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'id': 'userEmail',
            'placeholder': 'Enter your email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'id': 'userPassword',
            'placeholder': 'Enter your password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'exampleCheck'
        })
    )


class UserProfileForm(forms.ModelForm):
    """
    Form for users to edit their own profile information.
    Includes both User model fields (first_name, last_name) and UserProfile fields.
    """
    
    # =========================================================================
    # USER MODEL FIELDS (from django.contrib.auth.models.User)
    # =========================================================================
    
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        }),
        label='First Name'
    )
    
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        }),
        label='Last Name'
    )
    
    # =========================================================================
    # PASSWORD CHANGE FIELDS (Optional)
    # =========================================================================
    
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New Password (leave blank to keep current)'
        }),
        help_text='Leave blank if you don\'t want to change the password.',
        label='New Password'
    )
    
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm New Password'
        }),
        label='Confirm Password'
    )

    class Meta:
        model = UserProfile
        fields = [
            # Personal Information
            'photo',
            'mobile',
            'date_of_birth',
            'gender',
            'national_id',
            
            # Contact Information
            'address',
            'city',
            'state_province',
            'country',
            
            # Emergency Contact
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relationship',
            
            # Preferences
            'language',
            'timezone',
        ]
        
        widgets = {
            # Personal Information
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256123456789'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'gender': forms.Select(attrs={
                'class': 'form-select'
            }),
            'national_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'National ID or Passport Number'
            }),
            
            # Contact Information
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Street address, P.O. Box, etc.'
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'City or Town'
            }),
            'state_province': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'State, Province, or Region'
            }),
            'country': forms.Select(attrs={
                'class': 'form-select'
            }),
            
            # Emergency Contact
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+256123456789'
            }),
            'emergency_contact_relationship': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Spouse, Parent, Sibling'
            }),
            
            # Preferences
            'language': forms.Select(attrs={
                'class': 'form-select'
            }),
            'timezone': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        
        labels = {
            'photo': 'Profile Photo',
            'mobile': 'Mobile Phone',
            'date_of_birth': 'Date of Birth',
            'gender': 'Gender',
            'national_id': 'National ID / Passport',
            'address': 'Home Address',
            'city': 'City/Town',
            'state_province': 'State/Province/Region',
            'country': 'Country',
            'emergency_contact_name': 'Emergency Contact Name',
            'emergency_contact_phone': 'Emergency Contact Phone',
            'emergency_contact_relationship': 'Relationship',
            'language': 'Preferred Language',
            'timezone': 'Timezone',
        }

    def __init__(self, *args, **kwargs):
        # Extract the user instance if provided
        self.user_instance = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Populate User model fields if editing existing profile
        if self.instance and self.instance.pk and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name

    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        # Validate password if provided
        if password or confirm_password:
            if password != confirm_password:
                raise forms.ValidationError({
                    'confirm_password': 'Passwords do not match.'
                })
            
            # Password strength validation
            if password and len(password) < 8:
                raise forms.ValidationError({
                    'password': 'Password must be at least 8 characters long.'
                })

        # Validate mobile phone format (basic check)
        mobile = cleaned_data.get('mobile')
        if mobile and not mobile.replace('+', '').replace(' ', '').replace('-', '').isdigit():
            raise forms.ValidationError({
                'mobile': 'Please enter a valid phone number (digits only, may start with +).'
            })

        # Validate emergency contact phone if provided
        emergency_phone = cleaned_data.get('emergency_contact_phone')
        if emergency_phone and not emergency_phone.replace('+', '').replace(' ', '').replace('-', '').isdigit():
            raise forms.ValidationError({
                'emergency_contact_phone': 'Please enter a valid phone number (digits only, may start with +).'
            })

        return cleaned_data

    def save(self, commit=True):
        """Save both User and UserProfile data"""
        profile = super().save(commit=False)
        
        # Update the associated User model fields
        if profile.user:
            # Update editable User fields
            profile.user.first_name = self.cleaned_data['first_name']
            profile.user.last_name = self.cleaned_data['last_name']
            
            # Update password if provided
            password = self.cleaned_data.get('password')
            if password:
                profile.user.set_password(password)
            
            if commit:
                profile.user.save()
        
        if commit:
            profile.save()
        
        return profile