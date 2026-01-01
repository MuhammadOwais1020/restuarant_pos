from django import forms
from core.models import PaymentReceived

class PaymentReceivedForm(forms.ModelForm):
    class Meta:
        model = PaymentReceived
        fields = [
            'date', 'party_type', 'customer', 'supplier', 
            'amount', 'payment_method', 'bank_account', 'description'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'party_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_party_type'}),
            'customer': forms.Select(attrs={'class': 'form-select search-select'}), 
            'supplier': forms.Select(attrs={'class': 'form-select search-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'payment_method': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].required = False
        self.fields['customer'].required = False
        self.fields['supplier'].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.request:
            obj.created_by = self.request.user
        if commit:
            obj.save()
        return obj