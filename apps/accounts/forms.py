# accounts/forms.py
from django import forms
from .models import UserProfile
from django.contrib.auth.models import User

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
    # User fields - read-only
    username = forms.CharField(
        max_length=150,
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly'
        })
    )
    email = forms.EmailField(
        required=False,
        disabled=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly'
        })
    )
    
    # User fields - editable
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )
    
    # Password fields
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'New Password (leave blank to keep current)'
        }),
        help_text='Leave blank if you don\'t want to change the password.'
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
            'school',
            'role',
            'photo',
        ]
        widgets = {
            'school': forms.Select(attrs={
                'class': 'form-control',
                'disabled': 'disabled'
            }),
            'role': forms.Select(attrs={
                'class': 'form-control',
                'disabled': 'disabled'
            }),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'photo': 'Profile Photo',
        }

    def __init__(self, *args, **kwargs):
        # Extract the user instance if provided
        self.user_instance = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Make school field disabled (read-only but display value)
        self.fields['school'].disabled = True
        
        # Populate user fields if editing existing profile
        if self.instance and self.instance.pk and self.instance.user:
            self.fields['username'].initial = self.instance.user.username
            self.fields['email'].initial = self.instance.user.email
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        # If password is provided, validate it
        if password or confirm_password:
            if password != confirm_password:
                raise forms.ValidationError({
                    'confirm_password': 'Passwords do not match.'
                })
            
            # Optional: Add password strength validation
            if password and len(password) < 8:
                raise forms.ValidationError({
                    'password': 'Password must be at least 8 characters long.'
                })

        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        
        # Update the associated user
        if profile.user:
            # Only update editable fields
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