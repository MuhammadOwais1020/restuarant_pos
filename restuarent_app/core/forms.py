# core/forms.py
from django import forms
from .models import Table

class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ['number', 'seats', 'is_occupied']
        widgets = {
            'number': forms.NumberInput(attrs={'class': 'form-control'}),
            'seats':  forms.NumberInput(attrs={'class': 'form-control'}),
            'is_occupied': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
