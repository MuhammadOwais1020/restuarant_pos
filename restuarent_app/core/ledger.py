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


# core/ledger.py
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal

from django.db.models import Sum, Q, F, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import (
    Supplier,
    Staff,
    Expense,
    PurchaseOrder,
    BankAccount,
    Customer,        # NEW
    Order,           # NEW
    PaymentReceived  # NEW
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
    val = getattr(po, "net_total", None)
    if val is not None:
        return Decimal(val)
    # fallback re-calculation
    tax = Decimal(getattr(po, "tax_percent", 0) or 0)
    disc = Decimal(getattr(po, "discount_percent", 0) or 0)
    subtotal = Decimal(po.total_cost or 0)
    return (subtotal + (subtotal * tax / Decimal("100")) - (subtotal * disc / Decimal("100"))).quantize(Decimal("0.01"))

def calculate_order_total(order) -> Decimal:
    """Helper to calculate Grand Total of a customer order."""
    # 1. Sum items
    subtotal = sum(item.quantity * item.unit_price for item in order.items.all())
    # 2. Apply Discount
    discount = order.discount or Decimal(0)
    after_disc = subtotal - discount
    if after_disc < 0: after_disc = Decimal(0)
    # 3. Apply Tax
    tax_p = order.tax_percentage or Decimal(0)
    tax_amt = (after_disc * tax_p) / Decimal(100)
    # 4. Apply Service
    svc = order.service_charge or Decimal(0)
    
    return (after_disc + tax_amt + svc).quantize(Decimal("0.01"))


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
        if not q_to:
            q_to = timezone.localdate()
        return q_from, q_to, from_start

# ---------- Home (lists suppliers & staff with quick balances) ----------

class LedgerHomeView(LoginRequiredMixin, TemplateView):
    template_name = "ledger/ledger_home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["suppliers"] = Supplier.objects.order_by("name")
        ctx["staff"] = Staff.objects.order_by("full_name")
        ctx["customers"] = Customer.objects.order_by("name") # Added Customers
        return ctx


# ---------- Supplier Ledger ----------

class SupplierLedgerView(LoginRequiredMixin, LedgerBaseView):
    template_name = "ledger/supplier_ledger.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        supplier = get_object_or_404(Supplier, pk=kwargs["pk"])
        dfrom, dto, from_start = self.parse_filters(self.request)

        entries = []

        # 1. Purchases (PO) -> CREDIT (We owe them)
        # Prefetch items and raw_material to build detailed description strings
        po_qs = (
            PurchaseOrder.objects
            .filter(supplier=supplier)
            .select_related("supplier")
            .prefetch_related("items__raw_material")
            .order_by("created_at")
        )
        if dfrom: po_qs = po_qs.filter(created_at__date__gte=dfrom)
        if dto:   po_qs = po_qs.filter(created_at__date__lte=dto)

        for po in po_qs:
            nt = safe_net_total(po)
            # Build detailed description
            item_details = ", ".join([
                f"{i.quantity}{i.raw_material.unit} {i.raw_material.name} @{i.unit_price}" 
                for i in po.items.all()
            ])
            desc_str = f"PO #{po.id}: {item_details}" if item_details else f"PO #{po.id}"

            entries.append({
                "dt": po.created_at,
                "desc": desc_str,
                "ref": po.id,
                "dr": Decimal("0.00"),
                "cr": nt,
            })

        # 2. Expenses (Payments TO Supplier) -> DEBIT (We paid them)
        pay_qs = Expense.objects.filter(
            Q(supplier=supplier) | Q(purchase_order__supplier=supplier)
        ).order_by("created_at")
        if dfrom: pay_qs = pay_qs.filter(created_at__date__gte=dfrom)
        if dto:   pay_qs = pay_qs.filter(created_at__date__lte=dto)

        for e in pay_qs:
            label = f"Payment ({e.get_category_display()})"
            if e.description: label += f" - {e.description}"
            if e.purchase_order_id: label += f" [Ref PO #{e.purchase_order_id}]"
            
            entries.append({
                "dt": getattr(e, "created_at", None) or datetime.combine(e.date, datetime.min.time()),
                "desc": label,
                "ref": e.id,
                "dr": Decimal(e.amount or 0),
                "cr": Decimal("0.00"),
            })

        # 3. Payment Received (Refund FROM Supplier) -> CREDIT 
        # (Treating refund as 'Reverse Payment' or 'Income' which reduces the debit side, 
        # effectively increasing the balance we owe/offsetting the payment).
        # Alternatively: It's Money In. Accounting: Supplier Account (Dr), Cash (Cr). 
        # Wait, if Supplier gives money back, our liability to them DECREASES? No.
        # Simple Logic: 
        #   We Buy 1000 (Cr). Bal: 1000 (Owe).
        #   We Pay 1000 (Dr). Bal: 0.
        #   We Return Item. They give 200 Cash. 
        #   This acts like a negative payment. So it should appear on the CREDIT side 
        #   to balance out the cash we received.
        recv_qs = PaymentReceived.objects.filter(supplier=supplier, party_type='supplier').order_by('created_at')
        if dfrom: recv_qs = recv_qs.filter(date__gte=dfrom)
        if dto:   recv_qs = recv_qs.filter(date__lte=dto)
        
        for r in recv_qs:
            entries.append({
                "dt": getattr(r, "created_at", None) or datetime.combine(r.date, datetime.min.time()),
                "desc": f"Refund Received: {r.description}",
                "ref": r.id,
                "dr": Decimal("0.00"), 
                "cr": Decimal(r.amount), # Increases 'payable' balance or offsets previous debit
            })


        # 4. Opening Balance Logic
        opening = Decimal("0.00")
        if not from_start and dfrom:
            # Purchases before
            cr_before = sum(safe_net_total(po) for po in PurchaseOrder.objects.filter(supplier=supplier, created_at__date__lt=dfrom))
            
            # Refunds before
            ref_before = PaymentReceived.objects.filter(supplier=supplier, date__lt=dfrom).aggregate(s=Coalesce(Sum('amount'), Decimal('0')))['s']
            cr_total_before = cr_before + ref_before

            # Payments before
            dr_before = Decimal(Expense.objects.filter(
                Q(supplier=supplier) | Q(purchase_order__supplier=supplier),
                created_at__date__lt=dfrom
            ).aggregate(s=Coalesce(Sum("amount"), Decimal("0")))["s"])
            
            opening = (cr_total_before - dr_before)

        # Sort & Running Balance
        entries.sort(key=lambda x: x["dt"] or timezone.now())
        running = opening
        for it in entries:
            running = running + it["cr"] - it["dr"]
            it["bal"] = running

        # Color: Positive = We owe them (Red), Negative = Advance (Green)
        color = "red" if running > 0 else "green"

        ctx.update({
            "supplier": supplier,
            "entries": entries,
            "opening": opening,
            "closing": running,
            "closing_color": color,
            "from": dfrom,
            "to": dto,
            "from_start": from_start,
        })
        return ctx
    


# ---------- Customer Ledger (NEW) ----------

class CustomerLedgerView(LoginRequiredMixin, LedgerBaseView):
    template_name = "ledger/customer_ledger.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = get_object_or_404(Customer, pk=kwargs["pk"])
        dfrom, dto, from_start = self.parse_filters(self.request)

        entries = []

        # 1. Orders (Sales) -> DEBIT (They owe us)
        # Filter: Orders linked to this customer
        # Note: We need to calculate grand total dynamically as it's not stored as a single db field usually
        order_qs = (
            Order.objects
            .filter(customer=customer)
            .exclude(status='cancelled') # Safety check
            .prefetch_related('items')
            .order_by("created_at")
        )
        
        if dfrom: order_qs = order_qs.filter(created_at__date__gte=dfrom)
        if dto:   order_qs = order_qs.filter(created_at__date__lte=dto)

        for o in order_qs:
            g_total = calculate_order_total(o)
            
            # Detail string: "Chicken Biryani x2, Coke x1"
            items_desc = ", ".join([f"{i.menu_item.name if i.menu_item else i.deal.name} x{i.quantity}" for i in o.items.all()])
            desc = f"Order #{o.number}: {items_desc}"

            entries.append({
                "dt": o.created_at,
                "desc": desc,
                "ref": o.id,
                "dr": g_total,         # Debit = Receivable
                "cr": Decimal("0.00"),
            })

        # 2. Payments Received (From Customer) -> CREDIT (Reduces balance)
        pay_qs = PaymentReceived.objects.filter(customer=customer).order_by("created_at")
        if dfrom: pay_qs = pay_qs.filter(date__gte=dfrom)
        if dto:   pay_qs = pay_qs.filter(date__lte=dto)

        for p in pay_qs:
            entries.append({
                "dt": getattr(p, "created_at", None) or datetime.combine(p.date, datetime.min.time()),
                "desc": f"Payment Received ({p.get_payment_method_display()}) {p.description}",
                "ref": p.id,
                "dr": Decimal("0.00"),
                "cr": Decimal(p.amount), # Credit = Reduces Receivable
            })

        # 3. Opening Balance Logic
        opening = Decimal("0.00")
        if not from_start and dfrom:
            # Sales before
            orders_before = Order.objects.filter(customer=customer, created_at__date__lt=dfrom).exclude(status='cancelled')
            dr_before = sum(calculate_order_total(o) for o in orders_before)

            # Payments before
            cr_before = PaymentReceived.objects.filter(customer=customer, date__lt=dfrom).aggregate(s=Coalesce(Sum('amount'), Decimal('0')))['s']
            
            opening = dr_before - cr_before

        # Sort & Running Balance
        entries.sort(key=lambda x: x["dt"] or timezone.now())
        running = opening
        for it in entries:
            # For Customer: Balance = Debit (Sale) - Credit (Payment)
            running = running + it["dr"] - it["cr"]
            it["bal"] = running

        # Color: Positive = They owe us (Red/Warning), Negative = Advance (Green)
        # (Though usually Receivable is considered Asset, highlighted Red often means "Outstanding Debt" in UI context)
        color = "red" if running > 0 else "green"

        ctx.update({
            "customer": customer,
            "entries": entries,
            "opening": opening,
            "closing": running,
            "closing_color": color,
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
