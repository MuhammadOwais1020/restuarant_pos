from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .license_check import enforce_authorization
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import PrintStatus
from django.views.decorators.http import require_POST

from .printing import send_to_printer

class LoginView(View):
    def get(self, request):
        return render(request, 'login.html')

    def post(self, request):
        try:
            enforce_authorization(request)
        except RuntimeError as e: 
            print(f"message: {str(e)}")
            return render(request, "error_not_authorized.html", {"message": str(e)})
        
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        return render(request, 'login.html', {'error': 'Invalid credentials'})

class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('login')

class DashboardView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            enforce_authorization(request)
        except RuntimeError as e:
            return render(request, "error_not_authorized.html", {"message": str(e)})

        return render(request, 'dashboard.html')
    

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.http import JsonResponse
from .models import Category, MenuItem

# Mixin to return JSON for AJAX forms
class AjaxableResponseMixin:
    def is_ajax(self):
        return self.request.headers.get('x-requested-with') == 'XMLHttpRequest'

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.is_ajax():
            return JsonResponse({'message': 'OK'})
        return response

    def form_invalid(self, form):
        if self.is_ajax():
            return JsonResponse(form.errors, status=400)
        return super().form_invalid(form)

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if self.is_ajax():
            return JsonResponse({'message': 'Deleted'})
        return super().delete(request, *args, **kwargs)

# --- Categories ---
class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'categories/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        qs = super().get_queryset().order_by('-updated_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs

class CategoryCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = Category
    fields = ['name', 'description']
    template_name = 'categories/category_form.html'
    success_url = reverse_lazy('category_list')

class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'categories/category_detail.html'
    context_object_name = 'category'

class CategoryUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = Category
    fields = ['name', 'description']
    template_name = 'categories/category_form.html'
    success_url = reverse_lazy('category_list')

class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    success_url = reverse_lazy('category_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message': 'Deleted'})
        return super().delete(request, *args, **kwargs)

# --- Menu Items ---
class MenuItemListView(LoginRequiredMixin, ListView):
    model = MenuItem
    template_name = 'menu_items/menuitem_list.html'
    context_object_name = 'items'

    def get_queryset(self):
        qs = super().get_queryset().select_related('category').order_by('-updated_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs

class MenuItemCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = MenuItem
    fields = ['category', 'name', 'description', 'price', 'is_available', 'image']
    template_name = 'menu_items/menuitem_form.html'
    success_url = reverse_lazy('menuitem_list')

class MenuItemDetailView(LoginRequiredMixin, DetailView):
    model = MenuItem
    template_name = 'menu_items/menuitem_detail.html'
    context_object_name = 'item'

class MenuItemUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = MenuItem
    fields = ['category', 'name', 'description', 'price', 'is_available', 'image']
    template_name = 'menu_items/menuitem_form.html'
    success_url = reverse_lazy('menuitem_list')

class MenuItemDeleteView(LoginRequiredMixin, DeleteView):
    model = MenuItem
    success_url = reverse_lazy('menuitem_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message': 'Deleted'})
        return super().delete(request, *args, **kwargs)
    

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, HttpResponse
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, View
)
from .models import (
    Category, MenuItem, Deal, DealItem,
    Table, Order, OrderItem, Payment
)
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# ---------- DEALS CRUD ----------

class DealListView(LoginRequiredMixin, ListView):
    model = Deal
    template_name = 'deals/deal_list.html'
    context_object_name = 'deals'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('-updated_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs

class DealCreateView(LoginRequiredMixin, CreateView):
    model = Deal
    fields = ['name', 'description', 'price', 'is_available', 'image']
    template_name = 'deals/deal_form.html'
    success_url = reverse_lazy('deal_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Serialize all available MenuItems to JSON
        menu_items_qs = MenuItem.objects.filter(is_available=True).order_by('name')
        menu_items_data = [
            {'pk': mi.pk, 'name': mi.name, 'price': float(mi.price)}
            for mi in menu_items_qs
        ]
        context['menu_items_json'] = json.dumps(menu_items_data, cls=DjangoJSONEncoder)
        # For create view, no initial items
        context['initial_deal_items'] = []
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        data = json.loads(self.request.POST.get('deal_items_json', '[]'))
        for item in data:
            mi = MenuItem.objects.get(pk=item['menu_item_id'])
            DealItem.objects.create(deal=self.object, menu_item=mi, quantity=item['quantity'])
        return response


class DealUpdateView(LoginRequiredMixin, UpdateView):
    model = Deal
    fields = ['name', 'description', 'price', 'is_available', 'image']
    template_name = 'deals/deal_form.html'
    success_url = reverse_lazy('deal_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Serialize all available MenuItems to JSON
        menu_items_qs = MenuItem.objects.filter(is_available=True).order_by('name')
        menu_items_data = [
            {'pk': mi.pk, 'name': mi.name, 'price': float(mi.price)}
            for mi in menu_items_qs
        ]
        context['menu_items_json'] = json.dumps(menu_items_data, cls=DjangoJSONEncoder)
        # Pass existing DealItem rows as JSON
        context['initial_deal_items'] = [
            {'menu_item_id': di.menu_item.id, 'quantity': di.quantity}
            for di in self.object.deal_items.all()
        ]
        return context

    def form_valid(self, form):
        # Delete all existing items, then recreate from JSON
        DealItem.objects.filter(deal=self.object).delete()
        response = super().form_valid(form)
        data = json.loads(self.request.POST.get('deal_items_json', '[]'))
        for item in data:
            mi = MenuItem.objects.get(pk=item['menu_item_id'])
            DealItem.objects.create(deal=self.object, menu_item=mi, quantity=item['quantity'])
        return response

class DealDetailView(LoginRequiredMixin, DetailView):
    model = Deal
    template_name = 'deals/deal_detail.html'
    context_object_name = 'deal'


class DealDeleteView(LoginRequiredMixin, AjaxableResponseMixin, DeleteView):
    model = Deal
    success_url = reverse_lazy('deal_list')


# ---------- ORDER CRUD ----------

# core/views.py

import json
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from .models import Order

class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 15

    def get_queryset(self):
        """
        1) Start with the base queryset, prefetching related 'table' and 'created_by'.
        2) Apply your existing filters (q, status, date_from, date_to).
        3) Annotate each Order with:
           - 'subtotal': sum of (quantity * unit_price) over all OrderItems
           - 'total_amount': (subtotal - discount) + (subtotal * tax_percentage/100) + service_charge
        """
        # Step 1: Base queryset with select_related
        qs = super().get_queryset().select_related('table', 'created_by').order_by('-created_at')

        # Step 2: Apply filters from GET params
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if q:
            qs = qs.filter(number__icontains=q)
        if status:
            qs = qs.filter(status=status)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # Step 3a: Define an expression for line_total = quantity * unit_price
        #        We'll sum this expression across all related OrderItem rows.
        line_total_expr = ExpressionWrapper(
            F('items__quantity') * F('items__unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )

        # Annotate each Order with 'subtotal' = SUM(line_total_expr)
        qs = qs.annotate(subtotal=Sum(line_total_expr))

        # Step 3b: Now annotate 'total_amount'
        # total_amount = (subtotal - discount) + (subtotal * tax_percentage/100) + service_charge
        qs = qs.annotate(
            total_amount=ExpressionWrapper(
                (
                    F('subtotal')
                    - F('discount')
                    + (F('subtotal') * F('tax_percentage') / 100)
                    + F('service_charge')
                ),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )

        return qs
# core/views.py

import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseServerError
from django.views import View
from django.utils.timezone import now
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from .models import (
    Category, MenuItem, Deal, Table,
    Order, OrderItem
)
from .escpos_printers import print_token, print_bill  # our new printing helpers


import json
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import Category, MenuItem, Deal, Table, Order, OrderItem, PrintStatus
from .printing import send_to_printer

class OrderCreateView(LoginRequiredMixin, View):
    """
    GET:  Render a blank “New Order” form with table-selector annotated.
    POST: Accept JSON, create Order + OrderItems. If action=="paid", print and free table.
    """

    def get(self, request):
        categories = Category.objects.prefetch_related('items').order_by('name')

        # Serialize menu items
        all_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')
        menu_items_list = [
            {
                "id": mi.id,
                "name": mi.name,
                "price": float(mi.price),
                "category_id": mi.category.id,
                "image_url": mi.image.url if mi.image else ""
            }
            for mi in all_menu_items
        ]
        all_menu_items_json = json.dumps(menu_items_list)

        # Serialize deals
        all_deals = Deal.objects.filter(is_available=True).prefetch_related('deal_items__menu_item')
        deals_list = []
        for dl in all_deals:
            items = [
                {"menu_item_id": di.menu_item.id, "quantity": di.quantity}
                for di in dl.deal_items.all()
            ]
            deals_list.append({
                "id": dl.id,
                "name": dl.name,
                "price": float(dl.price),
                "image_url": dl.image.url if dl.image else "",
                "items": items,
            })
        all_deals_json = json.dumps(deals_list)

        existing_items_json = json.dumps([])

        # Annotate tables with pending totals and has_items flag
        tables = list(Table.objects.all().order_by("number"))
        for t in tables:
            pending = Order.objects.filter(table=t, status="pending").first()
            total = sum(oi.quantity * oi.unit_price for oi in (pending.items.all() if pending else []))
            t.current_order_total = f"{total:.2f}"
            t.has_items = (total > 0)

        return render(request, "orders/order_form.html", {
            "categories": categories,
            "all_menu_items_json": all_menu_items_json,
            "all_deals_json": all_deals_json,
            "existing_items_json": existing_items_json,
            "order": None,
            "tables": tables,
        })

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        user = request.user
        discount       = data.get("discount", 0) or 0
        tax_percentage = data.get("tax_percentage", 0) or 0
        service_charge = data.get("service_charge", 0) or 0
        items          = data.get("items", [])
        action         = data.get("action", "create")
        table_id       = data.get("table_id")

        status_value = "paid" if action == "paid" else "pending"

        order = Order.objects.create(
            created_by=user,
            table_id=table_id,
            discount=discount,
            tax_percentage=tax_percentage,
            service_charge=service_charge,
            status=status_value
        )

        if table_id and status_value != "paid":
            tbl = Table.objects.get(pk=table_id)
            tbl.is_occupied = True
            tbl.save()

        for it in items:
            if it.get("type") == "menu":
                OrderItem.objects.create(
                    order=order,
                    menu_item_id=it["menu_item_id"],
                    quantity=it["quantity"],
                    unit_price=it["unit_price"]
                )
            elif it.get("type") == "deal":
                OrderItem.objects.create(
                    order=order,
                    deal_id=it["deal_id"],
                    quantity=it["quantity"],
                    unit_price=it["unit_price"]
                )

        if status_value == "paid":
            try:
                # Kitchen Token
                token_data = build_token_bytes(order)
                send_to_printer(token_data)
                # Bill/Invoice
                bill_data = build_bill_bytes(order)
                send_to_printer(bill_data)
                # Free table
                if table_id:
                    tbl = Table.objects.get(pk=table_id)
                    tbl.is_occupied = False
                    tbl.save()
            except Exception as e:
                return JsonResponse({"error": f"Print failed: {e}"}, status=500)

        return JsonResponse({"message": "Order Created", "order_id": order.id})


class OrderUpdateView(LoginRequiredMixin, View):
    """
    GET:  Render “Edit Order” form pre-populated + table-selector annotated.
    POST: Accept JSON (with table_id), update Order + OrderItems, print if paid.
    """

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        categories = Category.objects.prefetch_related('items').order_by('name')

        # Serialize menu items
        all_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')
        menu_items_list = [
            {
                "id": mi.id,
                "name": mi.name,
                "price": float(mi.price),
                "category_id": mi.category.id,
                "image_url": mi.image.url if mi.image else ""
            }
            for mi in all_menu_items
        ]
        all_menu_items_json = json.dumps(menu_items_list)

        # Serialize deals
        all_deals = Deal.objects.filter(is_available=True).prefetch_related('deal_items__menu_item')
        deals_list = []
        for dl in all_deals:
            items = [
                {"menu_item_id": di.menu_item.id, "quantity": di.quantity}
                for di in dl.deal_items.all()
            ]
            deals_list.append({
                "id": dl.id,
                "name": dl.name,
                "price": float(dl.price),
                "image_url": dl.image.url if dl.image else "",
                "items": items,
            })
        all_deals_json = json.dumps(deals_list)

        existing_items = []
        for oi in order.items.all():
            if oi.menu_item_id:
                existing_items.append({
                    "type": "menu",
                    "menu_item_id": oi.menu_item_id,
                    "name": oi.menu_item.name,
                    "quantity": oi.quantity,
                    "unit_price": float(oi.unit_price)
                })
            else:
                existing_items.append({
                    "type": "deal",
                    "deal_id": oi.deal_id,
                    "name": oi.deal.name,
                    "quantity": oi.quantity,
                    "unit_price": float(oi.unit_price)
                })
        existing_items_json = json.dumps(existing_items)

        # Annotate tables
        tables = list(Table.objects.all().order_by("number"))
        for t in tables:
            pending = Order.objects.filter(table=t, status="pending").first()
            total = sum(oi.quantity * oi.unit_price for oi in (pending.items.all() if pending else []))
            t.current_order_total = f"{total:.2f}"
            t.has_items = (total > 0)

        return render(request, "orders/order_form.html", {
            "categories": categories,
            "all_menu_items_json": all_menu_items_json,
            "all_deals_json": all_deals_json,
            "existing_items_json": existing_items_json,
            "order": order,
            "tables": tables,
        })

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        discount       = data.get("discount", 0) or 0
        tax_percentage = data.get("tax_percentage", 0) or 0
        service_charge = data.get("service_charge", 0) or 0
        items          = data.get("items", [])
        action         = data.get("action", "update")
        table_id       = data.get("table_id")

        order.discount       = discount
        order.tax_percentage = tax_percentage
        order.service_charge = service_charge
        order.table_id       = table_id
        order.status         = "paid" if action == "paid" else "pending"
        order.save()

        if table_id is not None:
            tbl = Table.objects.get(pk=table_id)
            tbl.is_occupied = (order.status != "paid")
            tbl.save()

        order.items.all().delete()
        for it in items:
            if it.get("type") == "menu":
                OrderItem.objects.create(
                    order=order,
                    menu_item_id=it["menu_item_id"],
                    quantity=it["quantity"],
                    unit_price=it["unit_price"]
                )
            elif it.get("type") == "deal":
                OrderItem.objects.create(
                    order=order,
                    deal_id=it["deal_id"],
                    quantity=it["quantity"],
                    unit_price=it["unit_price"]
                )

        if order.status == "paid":
            try:
                ps = PrintStatus.objects.first()
                bill_enabled  = ps.bill  if ps else False
                token_enabled = ps.token if ps else False

                if token_enabled:
                    token_data = build_token_bytes(order)
                    send_to_printer(token_data)
                if bill_enabled:
                    bill_data = build_bill_bytes(order)
                    send_to_printer(bill_data)

                if table_id is not None:
                    tbl = Table.objects.get(pk=table_id)
                    tbl.is_occupied = False
                    tbl.save()
            except Exception as e:
                return JsonResponse({"error": f"Print failed: {e}"}, status=500)

        return JsonResponse({"message": "Order Updated", "order_id": order.id})


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'



class OrderDeleteView(LoginRequiredMixin, AjaxableResponseMixin, DeleteView):
    model = Order
    success_url = reverse_lazy('order_list')


# core/views.py  (continued)

# core/views.py  (or wherever you put your ESC/POS‐builders)

# core/views.py (or wherever your ESC/POS builders live)

from decimal import Decimal

# core/your_print_module.py

import os
from django.conf import settings
from .escpos_logo import logo_to_escpos_bytes

def build_token_bytes(order):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Insert the logo at the very top ───────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "static/img/logo.png")
    try:
        logo_bytes = logo_to_escpos_bytes(logo_path)
        lines.append(logo_bytes)
        # Add a blank line after logo so text doesn't overlap
        lines.append(b"\n")
    except Exception as e:
        # If logo read fails, skip gracefully
        lines.append(b"")  

    # ─── Restaurant name, larger/bold ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center alignment
    lines.append(esc + b"\x21" + b"\x30")   # double height & width
    lines.append(b"MR FOOD\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal
    lines.append(b"\n")

    # ─── Header “KITCHEN TOKEN” ───────────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center
    lines.append(b"KITCHEN TOKEN\n\n")

    # ─── Token number, bold, slightly bigger ─────────────────────────────
    token_str = str(order.token_number).encode("ascii")
    lines.append(esc + b"\x61" + b"\x01")   # center
    lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x10 → double width, normal height
    lines.append(b"TOKEN #: " + token_str + b"\n\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal

    # ─── Date / Time ──────────────────────────────────────────────────────
    now_str = order.created_at.strftime("%Y-%m-%d %H:%M").encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"Date: " + now_str + b"\n")
    lines.append(b"-" * 32 + b"\n")         # 32-char full width separator

    # ─── Order Items List (left name, right qty) ─────────────────────────
    for oi in order.items.all():
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        qty_bytes = str(oi.quantity).rjust(3).encode("ascii")
        lines.append(name_field + b"  x" + qty_bytes + b"\n")

    lines.append(b"\n\n\n\n\n\n\n\n")
    # ─── Feed + Cut ────────────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")    # full cut

    return b"".join(lines)


# def build_token_bytes(order):
#     esc = b"\x1B"
#     gs  = b"\x1D"

#     lines = []

#     # ----------------------------------------------------------------
#     # 1) Double‐sized Restaurant Name, centered
#     # ----------------------------------------------------------------
#     lines.append(esc + b"\x61" + b"\x01")   # ESC a 1  → center
#     lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x30 → double height & width
#     lines.append(b"MR FOOD\n")
#     lines.append(esc + b"\x21" + b"\x00")   # ESC ! 0x00 → back to normal
#     lines.append(b"\n")

#     # ----------------------------------------------------------------
#     # 2) “KITCHEN TOKEN” header, centered (normal size)
#     # ----------------------------------------------------------------
#     lines.append(esc + b"\x61" + b"\x01")   # center
#     lines.append(b"KITCHEN TOKEN\n")
#     lines.append(b"\n")

#     # ----------------------------------------------------------------
#     # 3) “TOKEN #” line in double‐height × double‐width
#     # ----------------------------------------------------------------
#     token_str = str(order.token_number)
#     lines.append(esc + b"\x61" + b"\x01")   # center
#     lines.append(esc + b"\x21" + b"\x30")   # double h×w
#     lines.append(b"TOKEN # " + token_str.encode("ascii") + b"\n")
#     lines.append(esc + b"\x21" + b"\x00")   # back to normal
#     lines.append(b"\n")

#     # ----------------------------------------------------------------
#     # 4) Date/time, left‐aligned
#     # ----------------------------------------------------------------
#     lines.append(esc + b"\x61" + b"\x01")   # center
#     now_str = order.created_at.strftime("%Y-%m-%d %H:%M")
#     lines.append(b"Date: " + now_str.encode("ascii") + b"\n")

#     # ----------------------------------------------------------------
#     # 5) Full‐width dashed separator
#     #    – Adjust the count of “-” to match your printer's character width.
#     #    – Here we use 32 hyphens for a typical 32‐column thermal printer.
#     # ----------------------------------------------------------------
#     lines.append(b"\n")

#     # ----------------------------------------------------------------
#     # 6) “Item                 Qty” header (32 characters total)
#     #      (ITEM_COL_WIDTH + QTY_COL_WIDTH = 32)
#     # ----------------------------------------------------------------
#     ITEM_COL_WIDTH = 24
#     QTY_COL_WIDTH = 8

#     header_item = b"Item".ljust(ITEM_COL_WIDTH)
#     header_qty  = b"Qty".rjust(QTY_COL_WIDTH)
#     lines.append(header_item + header_qty + b"\n")

#     # Another dashed line below the header
#     lines.append(b"----------------------------------------\n")

#     # ----------------------------------------------------------------
#     # 7) List each OrderItem:
#     #      Name left‐justified (up to 24 chars), quantity right‐justified (8 chars)
#     # ----------------------------------------------------------------
#     for oi in order.items.all():
#         # Determine the name (menu_item.name or deal.name)
#         name = (oi.menu_item.name if oi.menu_item else oi.deal.name)
#         # Truncate to ITEM_COL_WIDTH if needed, then left‐justify
#         name_trunc = name[:ITEM_COL_WIDTH]
#         name_field = name_trunc.ljust(ITEM_COL_WIDTH).encode("ascii", "ignore")

#         # Quantity as string, right‐justify into QTY_COL_WIDTH
#         qty_field = str(oi.quantity).rjust(QTY_COL_WIDTH).encode("ascii")

#         lines.append(name_field + qty_field + b"\n")

#     lines.append(b"\n")

#     # ----------------------------------------------------------------
#     # 8) Final dashed line at the bottom
#     # ----------------------------------------------------------------
#     lines.append(b"----------------------------------------\n")
#     lines.append(b"\n\n\n\n\n\n\n\n")

#     # ----------------------------------------------------------------
#     # 9) Cut paper (full cut)
#     # ----------------------------------------------------------------
#     lines.append(gs + b"\x56" + b"\x00")    # GS V 0

#     return b"".join(lines)


def build_bill_bytes(order):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Logo at top ──────────────────────────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "static/img/logo.png")
    try:
        lines.append(logo_to_escpos_bytes(logo_path))
        lines.append(b"\n")
    except:
        lines.append(b"")

    # ─── Restaurant name, double size ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")
    lines.append(esc + b"\x21" + b"\x30")
    lines.append(b"MR FOOD\n")
    lines.append(esc + b"\x21" + b"\x00")
    lines.append(b"\n")

    # ─── Order metadata (left) ────────────────────────────────────────────
    order_number_str = str(order.number).encode("ascii")
    token_str = str(order.token_number).encode("ascii")
    dt = order.created_at.strftime("%Y-%m-%d %H:%M").encode("ascii")

    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"Order #: " + order_number_str + b"\n")
    lines.append(b"Date    : " + dt + b"\n")
    lines.append(b"Token # : " + token_str + b"\n")
    lines.append(b"-" * 40 + b"\n")         # 40-char separator

    # ─── Column headers (Item │ Qty │ Price │ Total) ──────────────────────
    lines.append(esc + b"\x45" + b"\x01")   # bold on
    # 16 chars for name, 4 chars for qty, 7 for price, 8 for total = 35 + spacing
    lines.append(b"Item             Qty  Price   Total\n")
    lines.append(esc + b"\x45" + b"\x00")   # bold off
    lines.append(b"-" * 40 + b"\n")

    # ─── Each OrderItem row ───────────────────────────────────────────────
    subtotal = 0.0
    for oi in order.items.all():
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:16]
        name_field = name.ljust(16).encode("ascii", "ignore")

        qty = oi.quantity
        qty_field = str(qty).rjust(3).encode("ascii")

        unit_price_f = float(oi.unit_price)
        price_field = f"{unit_price_f:.2f}".rjust(7).encode("ascii")

        line_total_f = float(oi.quantity * oi.unit_price)
        total_field = f"{line_total_f:.2f}".rjust(7).encode("ascii")

        subtotal += line_total_f

        # e.g. b"Fish & Chips   2   150.00 300.00\n"
        lines.append(name_field + b" " + qty_field + b" " + price_field + b" " + total_field + b"\n")

    lines.append(b"-" * 40 + b"\n\n")

    # ─── Totals section ───────────────────────────────────────────────────
    discount_f = float(order.discount)
    tax_perc_f = float(order.tax_percentage)
    service_f = float(order.service_charge)
    after_disc = subtotal - discount_f
    tax_amt_f = after_disc * (tax_perc_f / 100.0)
    grand_f = after_disc + tax_amt_f + service_f

    lines.append(b"Subtotal : " + f"{subtotal:.2f}".encode("ascii") + b"\n")
    lines.append(b"Discount : " + f"{discount_f:.2f}".encode("ascii") + b"\n")
    lines.append(b"Tax (" + f"{tax_perc_f:.0f}".encode("ascii") + b"%) : " + f"{tax_amt_f:.2f}".encode("ascii") + b"\n")
    lines.append(b"Service : " + f"{service_f:.2f}".encode("ascii") + b"\n")
    lines.append(esc + b"\x45" + b"\x01")   # bold on for grand total
    lines.append(b"Grand Total: " + f"{grand_f:.2f}".encode("ascii") + b"\n\n")
    lines.append(esc + b"\x45" + b"\x00")   # bold off

    # ─── Footer / Branding (professional signature) ───────────────────────
    lines.append(b"-" * 40 + b"\n")
    lines.append(esc + b"\x61" + b"\x01")   # center
    # Company name
    lines.append(esc + b"\x21" + b"\x20")   # ESC ! 0x20 → double‐width
    lines.append(b"Barkat Smart POS\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal

    # Developer / tagline / contact
    lines.append(b"Developed by Qonkar Technologies\n\n")
    lines.append(b"Comprehensive Business Software Solutions\n\n")
    lines.append(b"Contact: +92 305 8214945\n")
    lines.append(b"www.qonkar.com\n\n")
    lines.append(b"Thank you for your support!\n\n\n\n\n\n\n")
    lines.append(b"\n" * 4)

    # ─── Cut paper (full) ─────────────────────────────────────────────────
    lines.append(gs + b"\x56" + b"\x00")

    return b"".join(lines)


# def build_bill_bytes(order):
#     """
#     Build a customer‐facing bill (ESC/POS) payload with perfectly
#     aligned columns under "Item", "Qty", "Price", "Total".
#     Assumes a 40-character-wide printer (dashed lines of length 40).
#     """
#     esc = b"\x1B"
#     gs  = b"\x1D"
#     lines = []

#     # 1) Restaurant name in double size, centered
#     lines.append(esc + b"\x61" + b"\x01")   # ESC a 1 → Center
#     lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x30 → double height & width
#     lines.append(b"MR. FOOD\n")
#     lines.append(esc + b"\x21" + b"\x00")   # ESC ! 0x00 → back to normal size
#     lines.append(b"\n")

#     # 2) Order metadata, left-aligned
#     order_number_str = str(order.number)
#     token_str = str(order.token_number)
#     dt = order.created_at.strftime("%Y-%m-%d %H:%M")

#     lines.append(esc + b"\x61" + b"\x00")   # ESC a 0 → Align left
#     lines.append(b"Order #: " + order_number_str.encode("ascii") + b"\n")
#     lines.append(b"Date:    " + dt.encode("ascii") + b"\n")
#     lines.append(b"Token #: " + token_str.encode("ascii") + b"\n")
#     lines.append(b"-" * 48 + b"\n")         # 40 dashes as separator

#     # 3) Column headers (bold)
#     lines.append(esc + b"\x45" + b"\x01")   # ESC E 1 → bold ON
#     # f"{'Item':<16}{'Qty':>4}{'Price':>8}{'Total':>8}\n"
#     header = f"{'Item':<22}{'Qty':>4}{'Price':>9}{'Total':>9}\n"
#     lines.append(header.encode("ascii"))
#     lines.append(esc + b"\x45" + b"\x00")   # ESC E 0 → bold OFF
#     lines.append(b"-" * 48 + b"\n")         # another 40-dash separator

#     # 4) Each OrderItem – same widths as header
#     subtotal = 0.0
#     for oi in order.items.all():
#         # Take first 16 chars of item name (or deal name)
#         raw_name = oi.menu_item.name if oi.menu_item else oi.deal.name
#         name = raw_name[:22].ljust(22)      # left-pad/truncate to 16 chars
#         qty = oi.quantity
#         # unit_price might be Decimal, so force float
#         unit_price_f = int(oi.unit_price)
#         line_total_f = int(oi.quantity * oi.unit_price)
#         subtotal += line_total_f

#         # Build one line in exactly 16 + 4 + 8 + 8 = 36 chars; remainder is just spaces.
#         # Format: |<16 chars item>|<4-char qty>|<8-char price>|<8-char total>|
#         line = f"{name}{qty:>4}{unit_price_f:>9}{line_total_f:>9}\n"
#         lines.append(line.encode("ascii"))

#     # 5) Footer-style separator
#     lines.append(b"-" * 48 + b"\n\n")

#     # 6) Totals
#     discount_f = float(order.discount)
#     tax_perc_f = float(order.tax_percentage)
#     service_f = float(order.service_charge)
#     tax_amt_f = (subtotal - discount_f) * (tax_perc_f / 100.0)
#     grand_f = (subtotal - discount_f) + tax_amt_f + service_f

#     lines.append(b"Subtotal:    " + f"{subtotal:>8.2f}".encode("ascii") + b"\n")
#     lines.append(b"Discount:    " + f"{discount_f:>8.2f}".encode("ascii") + b"\n")
#     lines.append(
#         b"Tax (" + f"{tax_perc_f:.0f}".encode("ascii") + b"%)   " +
#         f"{tax_amt_f:>8.2f}".encode("ascii") + b"\n"
#     )
#     lines.append(b"Service:     " + f"{service_f:>8.2f}".encode("ascii") + b"\n")
#     lines.append(esc + b"\x45" + b"\x01")   # bold ON for grand total
#     lines.append(b"Grand Total: " + f"{grand_f:>8.2f}".encode("ascii") + b"\n")
#     lines.append(esc + b"\x45" + b"\x00")   # bold OFF
#     lines.append(b"\n")

#     # 7) Footer / Branding
#     lines.append(b"-" * 48 + b"\n")
#     lines.append(esc + b"\x61" + b"\x01")   # center
#     lines.append(b"Barkat Smart POS Systems\n")
#     lines.append(b"Powered by Qonkar Technologies\n\n")
#     lines.append(b"Har Business ky liye Software Available Hain\n\n")
#     lines.append(b"Contact: (+92) 305 8214945\n")
#     lines.append(b"www.qonkar.com\n")
#     lines.append(b"Thank you!\n\n\n\n\n\n")
#     lines.append(b"\n" * 4)

#     # 8) CUT PAPER (full cut)
#     lines.append(gs + b"\x56" + b"\x00")    # GS V 0

#     return b"".join(lines)
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET", "POST"])
def update_print_status(request):
    if request.method == "GET":
        # Return existing status or defaults if none yet
        ps = PrintStatus.objects.first()
        if ps is None:
            return JsonResponse({"token": False, "bill": False})
        return JsonResponse({"token": ps.token, "bill": ps.bill})

    # POST path: toggle one field
    field = request.POST.get("field")
    value = request.POST.get("value")
    if field not in ("token", "bill") or value not in ("true", "false"):
        return JsonResponse(
            {"status": "error", "message": "Invalid field or value."},
            status=400
        )

    ps, created = PrintStatus.objects.get_or_create(defaults={"token": False, "bill": False})
    setattr(ps, field, (value == "true"))
    ps.save()

    return JsonResponse({
        "status": "success",
        "token": ps.token,
        "bill": ps.bill
    })

# core/views.py
from django.shortcuts import render
from django.db.models import Sum, F
from django.utils import timezone
from datetime import date, timedelta
import json

from .models import Order, OrderItem, MenuItem

def reports_view(request):
    """
    Render a page showing:
      - Today's sales
      - This month's sales
      - Total revenue + total orders in a custom date range
      - A 7-day daily-sales line chart (with floats, not Decimals)
      - A top-10 best-selling items horizontal bar chart
    """

    # 1) Parse start_date / end_date from GET or default to today
    if request.GET.get('start_date'):
        try:
            start_date = date.fromisoformat(request.GET['start_date'])
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    if request.GET.get('end_date'):
        try:
            end_date = date.fromisoformat(request.GET['end_date'])
        except ValueError:
            end_date = date.today()
    else:
        end_date = date.today()

    if end_date < start_date:
        end_date = start_date

    # 2) Paid orders in the custom range
    paid_orders_in_range = Order.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        status='paid'
    )

    # 3) Total orders in that range
    total_orders = paid_orders_in_range.count()

    # 4) Total revenue in that range (sum of quantity * unit_price)
    revenue_agg = OrderItem.objects.filter(
        order__in=paid_orders_in_range
    ).aggregate(
        total_revenue=Sum(F('quantity') * F('unit_price'))
    )
    total_revenue = revenue_agg['total_revenue'] or 0  # This is a Decimal or 0

    # 5) Top 10 best-selling items (sum of quantity). Cast to int.
    top_items_qs = (
        OrderItem.objects
        .filter(order__in=paid_orders_in_range, menu_item__isnull=False)
        .values('menu_item__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:10]
    )
    top_labels = []
    top_data = []
    for row in top_items_qs:
        top_labels.append(row['menu_item__name'])
        # row['total_qty'] might be a Decimal or int. Cast to int() if safe.
        top_data.append(int(row['total_qty']))

    # 6) Compute last 7 calendar days' revenue (float)
    today = date.today()
    daily_labels = []
    daily_data = []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_labels.append(d.strftime("%Y-%m-%d"))

        day_sum_agg = (
            OrderItem.objects
            .filter(
                order__created_at__date=d,
                order__status='paid'
            )
            .aggregate(day_sum=Sum(F('quantity') * F('unit_price')))
        )['day_sum'] or 0

        # day_sum_agg is a Decimal or 0; cast to float
        daily_data.append(float(day_sum_agg))

    # 7) Today's total revenue (cast to float)
    today_revenue_agg = (
        OrderItem.objects
        .filter(
            order__created_at__date=today,
            order__status='paid'
        )
        .aggregate(sum=Sum(F('quantity') * F('unit_price')))
    )['sum'] or 0
    today_revenue = float(today_revenue_agg)

    # 8) This month's total revenue (cast to float)
    first_of_month = today.replace(day=1)
    month_revenue_agg = (
        OrderItem.objects
        .filter(
            order__created_at__date__gte=first_of_month,
            order__created_at__date__lte=today,
            order__status='paid'
        )
        .aggregate(sum=Sum(F('quantity') * F('unit_price')))
    )['sum'] or 0
    month_revenue = float(month_revenue_agg)

    # 9) Build context. JSON-dump only the Python lists (floats/ints)
    context = {
        'start_date': start_date.isoformat(),
        'end_date':   end_date.isoformat(),

        'total_orders':     total_orders,
        'total_revenue':    total_revenue,   # Decimal or 0; safe to render in template
        'today_total':      today_revenue,   # Now a float
        'this_month_total': month_revenue,   # Now a float

        # JSON strings for Chart.js
        'daily_labels': json.dumps(daily_labels),
        'daily_data':   json.dumps(daily_data),
        'top_labels':   json.dumps(top_labels),
        'top_data':     json.dumps(top_data),
    }

    return render(request, 'reports.html', context)


# your_app/views.py
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Max
from datetime import datetime, time, timedelta

from .models import OrderItem

def sales_report(request):
    sd = request.GET.get('start_date')
    ed = request.GET.get('end_date')
    if not sd or not ed:
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        start_date = datetime.strptime(sd, "%Y-%m-%d").date()
        end_date   = datetime.strptime(ed, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    start_dt = timezone.make_aware(datetime.combine(start_date, time(hour=12)))
    next_day = end_date + timedelta(days=1)
    end_dt   = timezone.make_aware(datetime.combine(next_day, time(hour=12)))

    qs = (
        OrderItem.objects
        .filter(order__created_at__gte=start_dt,
                order__created_at__lt=end_dt)
        .values('menu_item__name')
        .annotate(
            total_qty=Sum('quantity'),
            last_sold=Max('order__created_at')
        )
        .order_by('menu_item__name')
    )

    data = []
    for entry in qs:
        # convert to localtime and format
        last_sold_dt = timezone.localtime(entry['last_sold'])
        formatted = last_sold_dt.strftime("%Y-%m-%d")
        print(f"Date formate: {formatted}")
        data.append({
            'name':      entry['menu_item__name'],
            'total_qty': entry['total_qty'],
            'last_sold': formatted
        })

    return JsonResponse(data, safe=False)


# table
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from .models import Table
from .forms import TableForm

class TableListView(ListView):
    model = Table
    template_name = 'tables/table_list.html'
    context_object_name = 'tables'
    paginate_by = 20

class TableCreateView(CreateView):
    model = Table
    form_class = TableForm
    template_name = 'tables/table_form.html'
    success_url = reverse_lazy('table_list')

class TableUpdateView(UpdateView):
    model = Table
    form_class = TableForm
    template_name = 'tables/table_form.html'
    success_url = reverse_lazy('table_list')


import json
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import Table, Order

class TableSwitchView(LoginRequiredMixin, View):
    """
    GET /orders/table-switch/?table_id=<id or empty>
      - If table_id is missing, blank, or 'null' → return empty walk-in payload
      - Else → fetch (or create) pending Order for that table,
        mark table occupied, and return its items + charges.
    """

    def get(self, request):
        raw = request.GET.get('table_id')

        # ---- Walk-in (no table) ----
        if raw is None or raw == "" or raw.lower() == "null":
            return JsonResponse({
                "order_id": None,
                "table_id": None,
                "items": [],
                "discount": 0,
                "tax_percentage": 0,
                "service_charge": 0,
            })

        # ---- Otherwise try to parse a valid integer ----
        try:
            table_id = int(raw)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid table_id"}, status=400)

        # ---- Lookup table and its pending order ----
        table = get_object_or_404(Table, pk=table_id)
        order, _ = Order.objects.get_or_create(
            table=table, status="pending",
            defaults={"created_by": request.user}
        )

        # Mark it occupied in the DB
        table.is_occupied = True
        table.save()

        # Build items array
        items_data = []
        for oi in order.items.all():
            items_data.append({
                "type":         "menu" if oi.menu_item_id else "deal",
                "menu_item_id": oi.menu_item_id,
                "deal_id":      oi.deal_id,
                "name":         oi.menu_item.name if oi.menu_item_id else oi.deal.name,
                "quantity":     oi.quantity,
                "unit_price":   float(oi.unit_price),
            })

        # Return JSON for the UI to load
        return JsonResponse({
            "order_id":       order.id,
            "table_id":       table.id,
            "items":          items_data,
            "discount":       float(order.discount),
            "tax_percentage": float(order.tax_percentage),
            "service_charge": float(order.service_charge),
        })
