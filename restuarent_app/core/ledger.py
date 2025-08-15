# core/ledger.py
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal

from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from django.utils import timezone

from .models import (
    Supplier,
    Staff,
    Expense,          # uses your extended Expense model (already working)
    PurchaseOrder,
    BankAccount,
)

# ---------- Helpers ----------

def dt_from_str(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def month_ends(start_date: date, end_date: date):
    """Yield month-end dates from start_date..end_date."""
    if not start_date or not end_date or start_date > end_date:
        return
    y, m = start_date.year, start_date.month
    while True:
        last_day = monthrange(y, m)[1]
        d = date(y, m, last_day)
        if d >= start_date and d <= end_date:
            yield d
        # advance
        if y > end_date.year or (y == end_date.year and m >= end_date.month):
            break
        m += 1
        if m == 13:
            m = 1
            y += 1

def safe_net_total(po: PurchaseOrder) -> Decimal:
    # If your model has net_total, use it; else derive from total_cost and stored percents (if any)
    val = getattr(po, "net_total", None)
    if val is not None:
        return Decimal(val)
    # graceful fallback
    tax = Decimal(getattr(po, "tax_percent", 0) or 0)
    disc = Decimal(getattr(po, "discount_percent", 0) or 0)
    subtotal = Decimal(po.total_cost or 0)
    return (subtotal + (subtotal * tax / Decimal("100")) - (subtotal * disc / Decimal("100"))).quantize(Decimal("0.01"))

def colored_direction(amount: Decimal):
    """
    Return ('green'|'red', label) where:
      - Positive balance means 'we owe them' → RED
      - Negative balance means 'they owe us' → GREEN
    """
    if amount is None:
        amount = Decimal("0")
    return ("red" if amount > 0 else "green", "Other side" if amount > 0 else "Our side")


# ---------- Base view for filter parsing ----------

class LedgerBaseView(TemplateView):
    def parse_filters(self, request):
        q_from = dt_from_str(request.GET.get("from", "") or "")
        q_to = dt_from_str(request.GET.get("to", "") or "")
        from_start = request.GET.get("from_start") in ["1", "true", "True", "on"]

        # defaults: from = None (start), to = today
        if not q_to:
            q_to = timezone.localdate()
        return q_from, q_to, from_start


# ---------- Home (lists suppliers & staff with quick balances) ----------

class LedgerHomeView(TemplateView):
    template_name = "ledger/ledger_home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["suppliers"] = Supplier.objects.order_by("name")
        ctx["staff"] = Staff.objects.order_by("full_name")
        return ctx


# ---------- Supplier Ledger ----------

class SupplierLedgerView(LedgerBaseView):
    template_name = "ledger/supplier_ledger.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Value as V, DecimalField

        ctx = super().get_context_data(**kwargs)
        supplier = get_object_or_404(Supplier, pk=kwargs["pk"])
        dfrom, dto, from_start = self.parse_filters(self.request)

        # Build entries
        entries = []

        # Purchases (CR)
        po_qs = PurchaseOrder.objects.filter(supplier=supplier).order_by("created_at")
        if dfrom:
            po_qs = po_qs.filter(created_at__date__gte=dfrom)
        if dto:
            po_qs = po_qs.filter(created_at__date__lte=dto)
        for po in po_qs.select_related("supplier"):
            nt = safe_net_total(po)
            entries.append({
                "dt": po.created_at,
                "desc": f"PO #{po.id}",
                "ref": po.id,
                "dr": Decimal("0.00"),
                "cr": nt,
            })

        # Payments to supplier (DR)  — include those tied to PO or directly to supplier
        pay_qs = Expense.objects.filter(
            Q(supplier=supplier) | Q(purchase_order__supplier=supplier)
        ).order_by("created_at")
        if dfrom:
            pay_qs = pay_qs.filter(created_at__date__gte=dfrom)
        if dto:
            pay_qs = pay_qs.filter(created_at__date__lte=dto)

        for e in pay_qs.select_related("purchase_order", "bank_account"):
            label = "Payment"
            if e.purchase_order_id:
                label += f" for PO #{e.purchase_order_id}"
            entries.append({
                "dt": getattr(e, "created_at", None) or datetime.combine(e.date, datetime.min.time()),
                "desc": label,
                "ref": e.id,
                "dr": Decimal(e.amount or 0),
                "cr": Decimal("0.00"),
            })

        # Opening balance (if not from_start)
        opening = Decimal("0.00")
        if not from_start and dfrom:
            # CR before start = purchases before dfrom
            cr_before = sum(
                safe_net_total(po) for po in
                PurchaseOrder.objects.filter(supplier=supplier, created_at__date__lt=dfrom)
            ) or Decimal("0")
            # DR before start = payments before dfrom
            dr_before = Decimal(Expense.objects.filter(
                Q(supplier=supplier) | Q(purchase_order__supplier=supplier),
                created_at__date__lt=dfrom
            ).aggregate(s=Coalesce(Sum("amount"), Decimal("0")))["s"])
            opening = (cr_before - dr_before)

        # Sort & running balance
        entries.sort(key=lambda x: x["dt"] or timezone.now())
        running = opening
        for it in entries:
            running = running + it["cr"] - it["dr"]
            it["bal"] = running

        color, side_label = colored_direction(running)

        ctx.update({
            "supplier": supplier,
            "entries": entries,
            "opening": opening,
            "closing": running,
            "closing_color": color,   # 'red' or 'green'
            "from": dfrom,
            "to": dto,
            "from_start": from_start,
        })
        return ctx


# ---------- Staff Ledger ----------
# core/ledger.py  — replace StaffLedgerView with this version
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Min
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone as tz
from django.views.generic import DetailView

from .models import Staff, Expense


# core/ledger.py  — FIX StaffLedgerView context keys

class StaffLedgerView(LoginRequiredMixin, DetailView):
    model = Staff
    template_name = "ledger/staff_ledger.html"
    context_object_name = "staff"

    @staticmethod
    def _parse_dmy(s: str | None) -> date | None:
        if not s:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _month_start(d: date) -> date:
        return date(d.year, d.month, 1)

    @staticmethod
    def _add_month(d: date) -> date:
        return date(d.year + (1 if d.month == 12 else 0),
                    1 if d.month == 12 else d.month + 1, 1)

    def get_context_data(self, **kwargs):
        from django.db.models import Sum, Min
        from django.db.models.functions import TruncDate, Coalesce
        from decimal import Decimal
        import django.utils.timezone as tz

        ctx = super().get_context_data(**kwargs)
        staff: Staff = self.object

        today = tz.localdate()
        monthly = Decimal(staff.monthly_salary or 0)

        pay_base = (
            Expense.objects
            .filter(staff=staff, category__iexact="salary")
            .annotate(edate=Coalesce("date", TruncDate("created_at")))
        )

        earliest_payment = pay_base.aggregate(m=Min("edate"))["m"]
        base_start = staff.salary_start or staff.joined_on or earliest_payment or today

        q_from = self._parse_dmy(self.request.GET.get("from"))
        q_to   = self._parse_dmy(self.request.GET.get("to"))
        from_start = str(self.request.GET.get("from_start", "")).lower() in ("1", "true", "on", "yes")

        start = q_from or base_start
        end   = q_to or today
        if start > end:
            start, end = end, start

        # Opening
        opening = Decimal("0")
        if not from_start:
            accr_before = Decimal("0")
            cur = self._month_start(base_start)
            first_of_period = self._month_start(start)
            while cur < first_of_period:
                accr_before += monthly
                cur = self._add_month(cur)

            paid_before = pay_base.filter(edate__lt=start).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            opening = accr_before - paid_before

        # Rows in period
        rows = []
        cur = self._month_start(max(base_start, start))
        last = self._month_start(end)
        while cur <= last:
            rows.append({"date": cur, "desc": f"Salary accrued for {cur.strftime('%b %Y')}",
                         "dr": Decimal("0"), "cr": monthly})
            cur = self._add_month(cur)

        pays = pay_base.filter(edate__gte=start, edate__lte=end).order_by("edate", "id")
        for p in pays:
            src_txt = f" via {p.get_payment_source_display()}" if hasattr(p, "get_payment_source_display") else ""
            bank_txt = f" — {p.bank_account}" if getattr(p, "bank_account", None) else ""
            rows.append({"date": p.edate,
                         "desc": p.description or f"Salary paid{src_txt}{bank_txt}",
                         "dr": Decimal(p.amount or 0), "cr": Decimal("0")})

        rows.sort(key=lambda r: (r["date"], 0 if r["cr"] > 0 else 1))

        running = opening
        for r in rows:
            running += (r["cr"] - r["dr"])
            r["run"] = running

        closing = running
        paid_sum = sum((r["dr"] for r in rows), Decimal("0"))
        accrued_sum = sum((r["cr"] for r in rows), Decimal("0"))

        # Map to template-friendly names (and keep old ones)
        accrual_start = staff.salary_start or staff.joined_on or earliest_payment
        entries = [{"dt": r["date"], "desc": r["desc"], "dr": r["dr"], "cr": r["cr"], "bal": r["run"]} for r in rows]

        ctx.update({
            # what the template expects
            "from": start,
            "to": end,
            "from_start": from_start,
            "opening": opening,
            "closing": closing,
            "entries": entries,
            "accrual_start": accrual_start,
            "monthly_salary": monthly,

            # keep these too (harmless) in case other code uses them
            "from_date": start,
            "to_date": end,
            "opening_balance": opening,
            "closing_balance": closing,
            "rows": rows,
            "salary_start": accrual_start,
            "paid_sum": paid_sum,
            "accrued_sum": accrued_sum,
        })
        return ctx


# --- Raw Material kitchen ledger (purchases / issues / returns only) -------
from django.views.generic import TemplateView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import RawMaterial, PurchaseOrderItem, KitchenVoucherItem

class RawMaterialLedgerView(TemplateView):
    template_name = 'ledger/raw_material_ledger.html'

    def parse_filters(self, request):
        from datetime import datetime
        def d(s):
            try: return datetime.strptime(s, "%Y-%m-%d").date()
            except: return None
        f = d(request.GET.get('from','') or '')
        t = d(request.GET.get('to','') or '')
        if not t: t = timezone.localdate()
        from_start = str(request.GET.get('from_start','')).lower() in ('1','true','on','yes')
        return f, t, from_start

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rm = get_object_or_404(RawMaterial, pk=kwargs['pk'])
        f, t, from_start = self.parse_filters(self.request)

        rows = []

        # Purchases (IN)
        pos = PurchaseOrderItem.objects.filter(raw_material=rm).select_related('purchase_order').order_by('purchase_order__created_at')
        if f: pos = pos.filter(purchase_order__created_at__date__gte=f)
        if t: pos = pos.filter(purchase_order__created_at__date__lte=t)
        for it in pos:
            rows.append({'dt': it.purchase_order.created_at, 'desc': f"PO #{it.purchase_order_id}",
                         'in': it.quantity, 'out': 0})

        # Issues to kitchen (OUT)
        issues = KitchenVoucherItem.objects.filter(raw_material=rm, voucher__vtype='issue').select_related('voucher').order_by('voucher__date','id')
        if f: issues = issues.filter(voucher__date__gte=f)
        if t: issues = issues.filter(voucher__date__lte=t)
        for it in issues:
            rows.append({'dt': it.voucher.date, 'desc': f"Issue to Kitchen KV#{it.voucher_id}",
                         'in': 0, 'out': it.quantity})

        # Returns from kitchen (IN)
        returns = KitchenVoucherItem.objects.filter(raw_material=rm, voucher__vtype='return').select_related('voucher').order_by('voucher__date','id')
        if f: returns = returns.filter(voucher__date__gte=f)
        if t: returns = returns.filter(voucher__date__lte=t)
        for it in returns:
            rows.append({'dt': it.voucher.date, 'desc': f"Return from Kitchen KV#{it.voucher_id}",
                         'in': it.quantity, 'out': 0})

        # Opening (prior to range)
        opening = 0
        if not from_start and f:
            p_before = PurchaseOrderItem.objects.filter(raw_material=rm, purchase_order__created_at__date__lt=f).aggregate(s=Sum('quantity'))['s'] or 0
            i_before = KitchenVoucherItem.objects.filter(raw_material=rm, voucher__vtype='issue', voucher__date__lt=f).aggregate(s=Sum('quantity'))['s'] or 0
            r_before = KitchenVoucherItem.objects.filter(raw_material=rm, voucher__vtype='return', voucher__date__lt=f).aggregate(s=Sum('quantity'))['s'] or 0
            opening = p_before - i_before + r_before

        rows.sort(key=lambda x: x['dt'])
        run = opening
        for r in rows:
            run += (r['in'] - r['out'])
            r['bal'] = run

        ctx.update({
            'rm': rm,
            'entries': rows,
            'opening': opening,
            'closing': run,
            'from': f, 'to': t, 'from_start': from_start,
        })
        return ctx
