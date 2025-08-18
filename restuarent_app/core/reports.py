# core/reports.py
from __future__ import annotations
from decimal import Decimal
from datetime import datetime, timedelta, date
from typing import Literal

from django.db.models import (
    Sum, F, Case, When, Value, DecimalField, ExpressionWrapper, DateTimeField, Max
)
from django.db.models.functions import TruncMonth, TruncDate, Coalesce
from django.utils import timezone as tz
from django.views.generic import TemplateView
from django.http import JsonResponse

from .models import Order, OrderItem, Expense, PurchaseOrder, MenuItem, Deal, DealItem

Mode = Literal["recipe", "simple"]

# Typed zero for money expressions
DEC0 = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

# ---------- helpers ----------

def _parse_dt_local(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        naive = datetime.strptime(s, "%Y-%m-%dT%H:%M")
        return tz.make_aware(naive, tz.get_current_timezone())
    except ValueError:
        return None

def _month_start(d: date) -> date:
    return d.replace(day=1)

def _month_range(dt: datetime) -> tuple[datetime, datetime]:
    start = tz.make_aware(datetime.combine(_month_start(dt.date()), datetime.min.time()))
    return start, tz.localtime()

def _sum_revenue(orderitems):
    money = ExpressionWrapper(F("quantity") * F("unit_price"),
                              output_field=DecimalField(max_digits=14, decimal_places=2))
    return orderitems.aggregate(s=Coalesce(Sum(money), DEC0))["s"] or Decimal("0")

def _sum_cogs_recipe(orderitems):
    cost_price = Case(
        When(menu_item__isnull=False, then=F("menu_item__cost_price")),
        When(deal__isnull=False,      then=F("deal__cost_price")),
        default=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    cost = ExpressionWrapper(F("quantity") * cost_price,
                             output_field=DecimalField(max_digits=14, decimal_places=2))
    return orderitems.aggregate(s=Coalesce(Sum(cost), DEC0))["s"] or Decimal("0")

def _sum_purchases(po_qs):
    return po_qs.aggregate(s=Coalesce(Sum("net_total"), Sum("total_cost"), DEC0))["s"] or Decimal("0")

def _sum_other_expenses(exp_qs):
    exp_qs = exp_qs.exclude(category__iexact="purchase")
    return exp_qs.aggregate(s=Coalesce(Sum("amount"), DEC0))["s"] or Decimal("0")

def _aware_start_end(request) -> tuple[datetime, datetime]:
    now = tz.localtime()
    default_start, default_end = _month_range(now)
    start = _parse_dt_local(request.GET.get("from"))
    end   = _parse_dt_local(request.GET.get("to"))
    if not start and not end:
        return default_start, default_end
    if start and not end:
        return start, now
    if end and not start:
        return end - timedelta(days=30), end
    if start and end and start > end:
        start, end = end, start
    return start, end

def _business_mode(request) -> Mode:
    mode = (request.GET.get("mode") or "").lower()
    if mode in ("recipe", "simple"):
        return mode
    total = MenuItem.objects.count() + Deal.objects.count()
    with_cost = (MenuItem.objects.filter(cost_price__gt=0).count()
                 + Deal.objects.filter(cost_price__gt=0).count())
    return "recipe" if total and (with_cost / total) >= 0.5 else "simple"


# ---------- Main dashboard view ----------

class ReportsOverviewView(TemplateView):
    template_name = "reports/overview.html"

    def get_context_data(self, **kwargs):
        from collections import defaultdict

        ctx = super().get_context_data(**kwargs)
        start_dt, end_dt = _aware_start_end(self.request)
        mode: Mode = _business_mode(self.request)

        # --- base querysets in range ---
        paid_orders = Order.objects.filter(
            status="paid",
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        items = OrderItem.objects.filter(order__in=paid_orders)

        # expenses: prefer created_at; if null, treat as start_dt just for filtering
        expenses = (
            Expense.objects
            .annotate(ed=Coalesce(F("created_at"), Value(start_dt, output_field=DateTimeField())))
            .filter(ed__gte=start_dt, ed__lte=end_dt)
        )

        # purchases by created_at
        purchases = PurchaseOrder.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )

        # --- KPIs ---
        revenue = _sum_revenue(items)

        if mode == "recipe":
            cogs   = _sum_cogs_recipe(items)
            others = _sum_other_expenses(expenses)
            cost_label = "COGS (Recipe Cost)"
        else:
            cogs   = _sum_purchases(purchases)
            others = _sum_other_expenses(expenses)
            cost_label = "Purchases"

        net_profit = revenue - cogs - others

        # --- Daily series in the selected range ---
        money = ExpressionWrapper(F("quantity") * F("unit_price"),
                                  output_field=DecimalField(max_digits=14, decimal_places=2))
        rev_by_day = (
            items.annotate(d=TruncDate("order__created_at"))
                 .values("d")
                 .annotate(v=Sum(money))
                 .order_by("d")
        )

        if mode == "recipe":
            cp = Case(
                When(menu_item__isnull=False, then=F("menu_item__cost_price")),
                When(deal__isnull=False,      then=F("deal__cost_price")),
                default=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
            cost_expr = ExpressionWrapper(F("quantity") * cp,
                                          output_field=DecimalField(max_digits=14, decimal_places=2))
            cost_by_day = (
                items.annotate(d=TruncDate("order__created_at"))
                     .values("d")
                     .annotate(v=Sum(cost_expr))
                     .order_by("d")
            )
        else:
            cost_by_day = (
                purchases.annotate(d=TruncDate("created_at"))
                         .values("d")
                         .annotate(v=Sum(Coalesce("net_total", "total_cost")))
                         .order_by("d")
            )

        exp_by_day = (
            expenses.annotate(d=TruncDate("ed"))
                    .values("d")
                    .annotate(v=Sum("amount"))
                    .order_by("d")
        )

        # normalize series
        days = []
        rev_series, cost_series, exp_series, profit_series = [], [], [], []
        cur = start_dt.date()
        while cur <= end_dt.date():
            days.append(cur.isoformat())
            r = next((x["v"] for x in rev_by_day  if x["d"] == cur), Decimal("0")) or Decimal("0")
            c = next((x["v"] for x in cost_by_day if x["d"] == cur), Decimal("0")) or Decimal("0")
            e = next((x["v"] for x in exp_by_day  if x["d"] == cur), Decimal("0")) or Decimal("0")
            rev_series.append(float(r))
            cost_series.append(float(c))
            exp_series.append(float(e))
            profit_series.append(float(r - c - e))
            cur += timedelta(days=1)

        # --- 12-month trend ---
        year_ago = _month_start(tz.localdate()).replace(day=1)
        year_start = tz.make_aware(datetime.combine(year_ago, datetime.min.time())) - timedelta(days=330)
        paid_12m = OrderItem.objects.filter(order__status="paid", order__created_at__gte=year_start)
        rev_12m = (
            paid_12m.annotate(m=TruncMonth("order__created_at"))
                    .values("m").annotate(v=Sum(money)).order_by("m")
        )
        if mode == "recipe":
            cost_12m = (
                paid_12m.annotate(m=TruncMonth("order__created_at"))
                        .values("m")
                        .annotate(v=Sum(ExpressionWrapper(
                            F("quantity") * Case(
                                When(menu_item__isnull=False, then=F("menu_item__cost_price")),
                                When(deal__isnull=False,      then=F("deal__cost_price")),
                                default=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                                output_field=DecimalField(max_digits=12, decimal_places=2),
                            ),
                            output_field=DecimalField(max_digits=14, decimal_places=2)
                        ))).order_by("m")
            )
        else:
            po_12m = PurchaseOrder.objects.filter(created_at__gte=year_start)
            cost_12m = (
                po_12m.annotate(m=TruncMonth("created_at"))
                      .values("m")
                      .annotate(v=Sum(Coalesce("net_total", "total_cost")))
                      .order_by("m")
            )

        months, rev_month, profit_month = [], [], []
        m_cur = _month_start(tz.localdate()).replace(day=1)
        m_start = (m_cur.replace(day=1) - timedelta(days=330)).replace(day=1)
        m = m_start
        while m <= m_cur:
            months.append(m.strftime("%b %Y"))
            r = next((x["v"] for x in rev_12m  if x["m"].date() == m), Decimal("0")) or Decimal("0")
            c = next((x["v"] for x in cost_12m if x["m"].date() == m), Decimal("0")) or Decimal("0")

            ms = tz.make_aware(datetime.combine(m, datetime.min.time()))
            next_m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
            me = tz.make_aware(datetime.combine(next_m, datetime.min.time()))
            e = (
                Expense.objects
                .annotate(ed=Coalesce(F("created_at"), Value(ms, output_field=DateTimeField())))
                .filter(ed__gte=ms, ed__lt=me)
                .exclude(category__iexact="purchase")
                .aggregate(s=Coalesce(Sum("amount"), DEC0))["s"] or Decimal("0")
            )

            months_last = next_m  # advance below
            rev_month.append(float(r))
            profit_month.append(float(r - c - e))
            m = months_last

        # ---------- EXTRA SECTIONS (ADDED ONLY; NOTHING ABOVE REMOVED) ----------

        # A) Expenses by Category (mode-aware: include 'purchase' only in simple mode)
        exp_for_chart = expenses
        if mode != "simple":
            exp_for_chart = exp_for_chart.exclude(category__iexact="purchase")
        exp_cat_rows = (
            exp_for_chart.values("category")
                         .annotate(total=Coalesce(Sum("amount"), DEC0))
                         .order_by("-total")
        )
        exp_cat_labels = [(r["category"] or "Other").replace("_", " ").title() for r in exp_cat_rows]
        exp_cat_values = [float(r["total"] or 0) for r in exp_cat_rows]

        # B) Sales by Category (quantity), counting items inside deals
        item_qty = defaultdict(int)   # (menu_item_id, name) -> qty
        cat_qty  = defaultdict(int)   # category name -> qty

        # direct menu item rows
        direct = (
            OrderItem.objects
            .filter(order__in=paid_orders, menu_item__isnull=False)
            .values("menu_item_id", "menu_item__name", "menu_item__category__name")
            .annotate(q=Sum("quantity"))
        )
        for r in direct:
            q = int(r["q"] or 0)
            name = r["menu_item__name"]
            mid = r["menu_item_id"]
            cat = r["menu_item__category__name"] or "Uncategorized"
            item_qty[(mid, name)] += q
            cat_qty[cat] += q

        # expand deals into their component menu items
        deal_qs = (
            OrderItem.objects
            .filter(order__in=paid_orders, deal__isnull=False)
            .values("deal_id")
            .annotate(q=Sum("quantity"))
        )
        deal_qty = {row["deal_id"]: int(row["q"] or 0) for row in deal_qs}
        if deal_qty:
            for di in DealItem.objects.filter(deal_id__in=deal_qty.keys()).select_related("menu_item__category"):
                comp_total = deal_qty.get(di.deal_id, 0) * int(di.quantity or 0)
                mid = di.menu_item_id
                name = di.menu_item.name
                cat = di.menu_item.category.name if getattr(di.menu_item, "category_id", None) else "Uncategorized"
                item_qty[(mid, name)] += comp_total
                cat_qty[cat] += comp_total

        # sorted outputs
        items_sorted = sorted(item_qty.items(), key=lambda kv: (-kv[1], kv[0][1]))
        items_sold = [{"name": name, "qty": qty} for ((_, name), qty) in items_sorted]
        cats_sorted = sorted(cat_qty.items(), key=lambda kv: -kv[1])
        sales_cat_labels = [name for name, _ in cats_sorted]
        sales_cat_values = [qty for _, qty in cats_sorted]

        # ---------- existing context ----------
        ctx.update({
            "mode": mode,
            "cost_label": cost_label,
            "from": tz.localtime(start_dt).strftime("%Y-%m-%dT%H:%M"),
            "to":   tz.localtime(end_dt).strftime("%Y-%m-%dT%H:%M"),
            "kpi_revenue": revenue,
            "kpi_cost":    cogs,
            "kpi_other":   others,
            "kpi_profit":  net_profit,
            "days": days,
            "series_revenue": rev_series,
            "series_cost":    cost_series,
            "series_expense": exp_series,
            "series_profit":  profit_series,
            "months": months,
            "trend_revenue": rev_month,
            "trend_profit":  profit_month,
        })

        # ---------- extra context (ADDED below your existing cards/charts) ----------
        ctx.update({
            "exp_cat_labels": exp_cat_labels,
            "exp_cat_values": exp_cat_values,
            "sales_cat_labels": sales_cat_labels,
            "sales_cat_values": sales_cat_values,
            "sales_items_labels": [it["name"] for it in items_sold],
            "sales_items_values": [it["qty"] for it in items_sold],
            "items_sold": items_sold,  # for the table
        })

        return ctx


# ---------- JSON endpoint ----------
def api_sales_report(request):
    """
    Datetime-aware filtering.
    GET ?from=YYYY-MM-DDTHH:MM&to=YYYY-MM-DDTHH:MM
    """
    start_dt, end_dt = _aware_start_end(request)
    qs = (
        OrderItem.objects
        .filter(order__created_at__gte=start_dt, order__created_at__lte=end_dt)
        .values("menu_item__name")
        .annotate(total_qty=Sum("quantity"), last_sold=Max("order__created_at"))
        .order_by("menu_item__name")
    )
    data = []
    for r in qs:
        last = r["last_sold"]
        data.append({
            "name": r["menu_item__name"],
            "total_qty": int(r["total_qty"] or 0),
            "last_sold": tz.localtime(last).strftime("%Y-%m-%d %H:%M") if last else None,
        })
    return JsonResponse(data, safe=False)
