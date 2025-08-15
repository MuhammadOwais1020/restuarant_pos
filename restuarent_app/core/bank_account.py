# core/views/bank_account.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Sum, F, Case, When, DecimalField
from django.contrib import messages

from core.models import BankAccount, BankMovement, CashFlow
from core.forms import BankAccountForm, BankMovementForm

# --------- Bank Accounts ---------

class BankAccountListView(LoginRequiredMixin, ListView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_list.html'
    context_object_name = 'accounts'

    def get_queryset(self):
        qs = super().get_queryset().order_by('-is_active','bank_name','name')
        return qs

class BankAccountCreateView(LoginRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bankaccount_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank account created.")
        return super().form_valid(form)

class BankAccountUpdateView(LoginRequiredMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'bank_accounts/bankaccount_form.html'
    success_url = reverse_lazy('bankaccount_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank account updated.")
        return super().form_valid(form)

class BankAccountDeleteView(LoginRequiredMixin, DeleteView):
    model = BankAccount
    template_name = 'bank_accounts/bankaccount_confirm_delete.html'
    success_url = reverse_lazy('bankaccount_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Bank account deleted.")
        return super().delete(request, *args, **kwargs)

# --------- Movements (Deposit / Withdraw / Transfer / Fee / Interest) ---------

class BankMovementListView(LoginRequiredMixin, ListView):
    model = BankMovement
    template_name = 'bank_movements/bankmovement_list.html'
    context_object_name = 'movements'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        acc = self.request.GET.get('account')
        mtype = self.request.GET.get('type')
        if acc:
            qs = qs.filter(
                # any side matches
                (F('from_bank_id') == acc) | (F('to_bank_id') == acc)
            )
        if mtype:
            qs = qs.filter(movement_type=mtype)
        return qs.select_related('from_bank','to_bank','created_by')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['accounts'] = BankAccount.objects.filter(is_active=True).order_by('bank_name','name')
        ctx['types'] = BankMovement.TYPES
        return ctx


class BankMovementCreateView(LoginRequiredMixin, CreateView):
    model = BankMovement
    form_class = BankMovementForm
    template_name = 'bank_movements/bankmovement_form.html'
    success_url = reverse_lazy('bankmovement_list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.save()
        messages.success(self.request, "Movement recorded.")
        return super().form_valid(form)


class BankMovementUpdateView(LoginRequiredMixin, UpdateView):
    model = BankMovement
    form_class = BankMovementForm
    template_name = 'bank_movements/bankmovement_form.html'
    success_url = reverse_lazy('bankmovement_list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user  # keep the creator
        # force linked cashflows to update amounts/refs
        obj.save()
        messages.success(self.request, "Movement updated.")
        return super().form_valid(form)


class BankMovementDeleteView(LoginRequiredMixin, DeleteView):
    model = BankMovement
    template_name = 'bank_movements/bankmovement_confirm_delete.html'
    success_url = reverse_lazy('bankmovement_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Movement deleted.")
        return super().delete(request, *args, **kwargs)
