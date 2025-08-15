# core/kitchen.py

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.shortcuts import redirect, render
from django.db.models import Sum, Q
# from django.utils import timezone  # not used here

from core.models import (
    KitchenVoucher, KitchenVoucherItem, RawMaterial, PurchaseOrderItem
)
from .forms import KitchenVoucherForm, VoucherItemFormSet  # <-- correct import path


# ------------------- VOUCHERS -------------------

class KitchenVoucherListView(LoginRequiredMixin, ListView):
    model = KitchenVoucher
    template_name = 'kitchen/voucher_list.html'
    context_object_name = 'vouchers'
    paginate_by = 25
    ordering = ['-date', '-id']

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related('handler', 'created_by')
        )
        t = self.request.GET.get('type')
        q = self.request.GET.get('q')
        if t in ('issue', 'return'):
            qs = qs.filter(vtype=t)
        if q:
            qs = qs.filter(Q(notes__icontains=q) | Q(handler__full_name__icontains=q))
        return qs


class KitchenVoucherCreateView(LoginRequiredMixin, CreateView):
    model = KitchenVoucher
    form_class = KitchenVoucherForm
    template_name = 'kitchen/voucher_form.html'
    success_url = reverse_lazy('kitchen_voucher_list')

    def get_initial(self):
        initial = super().get_initial()
        t = (self.request.GET.get('type') or '').lower()
        if t in ('issue', 'return'):
            initial['vtype'] = t
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # On GET self.object is None — fine; formset will render blank row(s)
        ctx['formset'] = kwargs.get('formset') or VoucherItemFormSet(self.request.POST or None, instance=self.object)
        ctx['rm_units'] = dict(RawMaterial.objects.values_list('id', 'unit'))  # <— add this
        ctx['is_create'] = True
        return ctx

    def form_valid(self, form):
        # Save parent first (without using super()) so we can control formset behavior
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()

        formset = VoucherItemFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            self.object.sync_transactions()
            return redirect(self.get_success_url())
        # If formset has errors, re-render with errors visible
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def form_invalid(self, form):
        # Ensure formset is present on invalid render
        formset = VoucherItemFormSet(self.request.POST or None, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class KitchenVoucherUpdateView(LoginRequiredMixin, UpdateView):
    model = KitchenVoucher
    form_class = KitchenVoucherForm
    template_name = 'kitchen/voucher_form.html'
    success_url = reverse_lazy('kitchen_voucher_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formset'] = kwargs.get('formset') or VoucherItemFormSet(self.request.POST or None, instance=self.object)
        ctx['rm_units'] = dict(RawMaterial.objects.values_list('id', 'unit'))  # <— add this
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        formset = VoucherItemFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            self.object.sync_transactions()
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def form_invalid(self, form):
        formset = VoucherItemFormSet(self.request.POST or None, instance=self.object)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class KitchenVoucherDeleteView(LoginRequiredMixin, DeleteView):
    model = KitchenVoucher
    template_name = 'kitchen/voucher_confirm_delete.html'
    success_url = reverse_lazy('kitchen_voucher_list')


# ------------------- STOCK SUMMARY -------------------

class KitchenStockSummaryView(LoginRequiredMixin, TemplateView):
    """
    Purchased (PO items) minus Issued to Kitchen plus Returned from Kitchen.
    Ignores recipe consumption by design; that remains covered by your existing flow.
    """
    template_name = 'kitchen/stock_summary.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Purchased (sum of PO item quantities)
        purchased = (
            PurchaseOrderItem.objects
            .values('raw_material_id', 'raw_material__name', 'raw_material__unit')
            .annotate(q=Sum('quantity'))
        )

        # Issued & Returned via vouchers
        issued = (
            KitchenVoucherItem.objects
            .filter(voucher__vtype='issue')
            .values('raw_material_id')
            .annotate(q=Sum('quantity'))
        )
        returned = (
            KitchenVoucherItem.objects
            .filter(voucher__vtype='return')
            .values('raw_material_id')
            .annotate(q=Sum('quantity'))
        )

        i_map = {r['raw_material_id']: r['q'] or 0 for r in issued}
        r_map = {r['raw_material_id']: r['q'] or 0 for r in returned}

        rows = []
        seen_ids = set()

        for p in purchased:
            rid = p['raw_material_id']
            seen_ids.add(rid)
            name = p['raw_material__name']
            unit = p['raw_material__unit']
            p_qty = p['q'] or 0
            i_qty = i_map.get(rid, 0)
            r_qty = r_map.get(rid, 0)
            remaining = p_qty - i_qty + r_qty
            rows.append({
                'id': rid,
                'name': name,
                'unit': unit,
                'purchased': p_qty,
                'issued': i_qty,
                'returned': r_qty,
                'remaining': remaining,
            })

        # include materials never purchased (edge case)
        for rm in RawMaterial.objects.exclude(id__in=seen_ids).values('id', 'name', 'unit'):
            rows.append({
                'id': rm['id'],
                'name': rm['name'],
                'unit': rm['unit'],
                'purchased': 0,
                'issued': 0,
                'returned': 0,
                'remaining': 0,
            })

        # current_stock (your live figure including recipe usage) for comparison
        cs_map = {rm.id: rm.current_stock for rm in RawMaterial.objects.all()}
        for r in rows:
            r['current_stock'] = cs_map.get(r['id'], 0)

        ctx['rows'] = rows
        return ctx
