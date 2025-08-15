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


# core/forms.py

from django import forms
from .models import BankAccount, BankMovement

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['name','bank_name','account_number','branch','opening_balance','is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'bank_name': forms.TextInput(attrs={'class':'form-control'}),
            'account_number': forms.TextInput(attrs={'class':'form-control'}),
            'branch': forms.TextInput(attrs={'class':'form-control'}),
            'opening_balance': forms.NumberInput(attrs={'class':'form-control','step':'0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }

class BankMovementForm(forms.ModelForm):
    class Meta:
        model = BankMovement
        fields = [
            'date','movement_type','amount',
            'from_bank','to_bank','method','reference_no','notes'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type':'date','class':'form-control'}),
            'movement_type': forms.Select(attrs={'class':'form-select'}),
            'amount': forms.NumberInput(attrs={'class':'form-control','step':'0.01','min':'0'}),
            'from_bank': forms.Select(attrs={'class':'form-select'}),
            'to_bank': forms.Select(attrs={'class':'form-select'}),
            'method': forms.TextInput(attrs={'class':'form-control','placeholder':'Cash / Cheque / Online'}),
            'reference_no': forms.TextInput(attrs={'class':'form-control','placeholder':'Txn/cheque ref'}),
            'notes': forms.TextInput(attrs={'class':'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        # We rely on model.clean() for core validation
        return cleaned


# forms.py
from django import forms
from django.contrib.auth import get_user_model
from core.models import Staff

User = get_user_model()


class StaffForm(forms.ModelForm):
    has_software_access = forms.BooleanField(required=False)

    class Meta:
        model = Staff
        fields = [
            'full_name', 'role', 'phone', 'cnic', 'address',
            'has_software_access',
            'joined_on', 'salary_start', 'monthly_salary',
            'access_sales', 'access_inventory', 'access_accounts',
        ]
        widgets = {
            'joined_on': forms.DateInput(attrs={'type': 'date'}),
            'salary_start': forms.DateInput(attrs={'type': 'date'}),
            'monthly_salary': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'address': forms.Textarea(attrs={'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        has_access = cleaned_data.get('has_software_access')

        if has_access:
            # Username/password will be handled in the view when access is enabled.
            pass
        else:
            # Auto-create a user with default password "1122" if not exists.
            name = cleaned_data.get('full_name')
            if name:
                username = name.lower().replace(' ', '_')
                user, created = User.objects.get_or_create(username=username)
                if created:
                    user.set_password('1122')
                    user.save()
                # Stash it so we can apply it on save()
                cleaned_data['user'] = user
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        user_from_clean = self.cleaned_data.get('user')
        if user_from_clean and not getattr(instance, 'user', None):
            instance.user = user_from_clean
        if commit:
            instance.save()
        return instance



# core/forms/expense_forms.py
from django import forms
from django.contrib.auth import get_user_model
from core.models import Expense, Supplier, Staff, BankAccount

User = get_user_model()

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'date', 'category', 'amount', 'description', 'reference', 'attachment',
            'supplier', 'staff',
            'payment_source', 'bank_account',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Details (optional)'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bill/Invoice # (optional)'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'payment_source': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # Friendly empty label
        self.fields['supplier'].empty_label = "— Select supplier —"
        self.fields['staff'].empty_label = "— Select staff —"
        self.fields['bank_account'].empty_label = "— Select bank account —"

        # Optional by default; JS + model.clean enforce rules
        self.fields['supplier'].required = False
        self.fields['staff'].required = False
        self.fields['bank_account'].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.created_by_id and self.request and self.request.user.is_authenticated:
            obj.created_by = self.request.user
        if commit:
            obj.save()
        return obj


from django import forms
from django.forms import inlineformset_factory
from core.models import KitchenVoucher, KitchenVoucherItem

class KitchenVoucherForm(forms.ModelForm):
    class Meta:
        model = KitchenVoucher
        fields = ['date','vtype','handler','notes']
        widgets = {
            'date': forms.DateInput(attrs={'type':'date','class':'form-control'}),
            'vtype': forms.Select(attrs={'class':'form-select'}),
            'handler': forms.Select(attrs={'class':'form-select'}),
            'notes': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Optional notes'}),
        }

class KitchenVoucherItemForm(forms.ModelForm):
    class Meta:
        model = KitchenVoucherItem
        fields = ['raw_material','quantity']
        widgets = {
            'raw_material': forms.Select(attrs={'class':'form-select'}),
            'quantity': forms.NumberInput(attrs={'class':'form-control','step':'0.01','min':'0'}),
        }

VoucherItemFormSet = inlineformset_factory(
    KitchenVoucher, KitchenVoucherItem,
    form=KitchenVoucherItemForm, extra=1, can_delete=True, min_num=1, validate_min=True
)
