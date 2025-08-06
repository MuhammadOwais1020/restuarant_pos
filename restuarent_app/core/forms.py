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


# core/forms.py
from django import forms
from .models import Expense, CashFlow

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date','category','amount','description']

class CashFlowForm(forms.ModelForm):
    class Meta:
        model = CashFlow
        fields = ['date','flow_type','amount','bank_account','description']
