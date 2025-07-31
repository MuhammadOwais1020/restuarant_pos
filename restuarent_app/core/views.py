from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .license_check import enforce_authorization
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import InventoryTransaction, PrintStatus, PurchaseOrder, RawMaterial, Recipe
from django.views.decorators.http import require_POST

from .printing import send_to_printer


import json
from decimal import Decimal
from django.db.models import Sum, F
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import (
    RawMaterialUnitConversion,
    PurchaseOrderItem,
    MenuItem, Deal
)


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
    fields = ['category', 'name', 'description', 'price', 'food_panda_price', 'is_available', 'image']
    template_name = 'menu_items/menuitem_form.html'
    success_url = reverse_lazy('menuitem_list')

class MenuItemDetailView(LoginRequiredMixin, DetailView):
    model = MenuItem
    template_name = 'menu_items/menuitem_detail.html'
    context_object_name = 'item'

class MenuItemUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = MenuItem
    fields = ['category', 'name', 'description', 'price', 'food_panda_price', 'is_available', 'image']
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
    fields = ['name', 'description', 'price', 'food_panda_price', 'is_available', 'image']
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
    fields = ['name', 'description', 'price', 'food_panda_price', 'is_available', 'image']
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
from .models import Waiter

class OrderCreateView(LoginRequiredMixin, View):

    def get(self, request):
        categories = Category.objects.prefetch_related('items').order_by('name')
        all_waiters = Waiter.objects.order_by('name').values('id','name')
        waiters_json = json.dumps(list(all_waiters))

        # Serialize menu items
        all_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')
        menu_items_list = [
            {
                "id": mi.id,
                "name": mi.name,
                "price": float(mi.price),
                "food_panda_price": float(mi.food_panda_price) if mi.food_panda_price is not None else 0.0,
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
                "food_panda_price": float(dl.food_panda_price) if dl.food_panda_price is not None else 0.0,
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
            "waiters_json": waiters_json,
        })

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        user = request.user
        discount = data.get("discount", 0) or 0
        tax_percentage = data.get("tax_percentage", 0) or 0
        service_charge = data.get("service_charge", 0) or 0
        items = data.get("items", [])
        action = data.get("action", "create")
        table_id = data.get("table_id")
        is_food_panda = data.get("source")
        waiter_id = data.get("waiter_id") or None
        is_home_delivery = data.get("isHomeDelivery") or None

        source_value =  is_food_panda

        status_value = "paid" if action == "paid" else "pending"

        order = Order.objects.create(
            created_by=user,
            table_id=table_id,
            discount=discount,
            tax_percentage=tax_percentage,
            service_charge=service_charge,
            status=status_value,
            source=source_value,
            waiter=waiter_id,
            is_home_delivery = is_home_delivery,
        )

        if table_id and status_value != "paid":
            tbl = Table.objects.get(pk=table_id)
            tbl.is_occupied = True
            tbl.save()

        for it in items:
            unit_price = it["unit_price"]
            # Check if the source is "Food Panda"
            if is_food_panda == "food_panda":
                if it.get("type") == "menu":
                    menu_item = MenuItem.objects.get(pk=it["menu_item_id"])
                    unit_price = menu_item.food_panda_price if menu_item.food_panda_price else menu_item.price
                elif it.get("type") == "deal":
                    deal = Deal.objects.get(pk=it["deal_id"])
                    unit_price = deal.food_panda_price if deal.food_panda_price else deal.price
            else:
                # Use default price if not a Food Panda order
                if it.get("type") == "menu":
                    menu_item = MenuItem.objects.get(pk=it["menu_item_id"])
                    unit_price = menu_item.price
                elif it.get("type") == "deal":
                    deal = Deal.objects.get(pk=it["deal_id"])
                    unit_price = deal.price

            if it.get("type") == "menu":
                OrderItem.objects.create(
                    order=order,
                    menu_item_id=it["menu_item_id"],
                    quantity=it["quantity"],
                    unit_price=unit_price
                )
            elif it.get("type") == "deal":
                OrderItem.objects.create(
                    order=order,
                    deal_id=it["deal_id"],
                    quantity=it["quantity"],
                    unit_price=unit_price
                )

            if status_value == "paid":
                try:
                    ps = PrintStatus.objects.first()
                    bill_enabled  = ps.bill  if ps else False
                    token_enabled = ps.token if ps else False

                    if token_enabled:
                        token_data = build_token_bytes(order, is_food_panda)
                        send_to_printer(token_data)
                    if bill_enabled:
                        bill_data = build_bill_bytes(order, is_food_panda)
                        send_to_printer(bill_data)

                    if table_id:
                        tbl = Table.objects.get(pk=table_id)
                        tbl.is_occupied = False
                        tbl.save()
                except Exception as e:
                    return JsonResponse({"error": f"Print failed: {e}"}, status=500)

        return JsonResponse({"message": "Order Created", "order_id": order.id})

# core/views.py

import json
from django.shortcuts      import render, get_object_or_404
from django.http           import JsonResponse, HttpResponseBadRequest
from django.views          import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import (
    Category, MenuItem, Deal,
    Table, Order, OrderItem, PrintStatus
)
from .printing import send_to_printer


class OrderUpdateView(LoginRequiredMixin, View):
    """
    GET:  Render “Edit Order” form pre-populated + table‑selector annotated.
    POST: Accept JSON (with table_id), diff OrderItems, print if paid.
    """

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        # … your existing GET logic unchanged …
        categories = Category.objects.prefetch_related('items').order_by('name')
        all_waiters = Waiter.objects.order_by('name').values('id','name')
        waiters_json = json.dumps(list(all_waiters))

        # Serialize menu items
        all_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')
        menu_items_list = [
            {
                "id": mi.id,
                "name": mi.name,
                "price": float(mi.price),
                "food_panda_price": float(mi.food_panda_price) if mi.food_panda_price is not None else 0.0,
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
                "food_panda_price": float(dl.food_panda_price) if dl.food_panda_price is not None else 0.0,
                "image_url": dl.image.url if dl.image else "",
                "items": items,
            })
        all_deals_json = json.dumps(deals_list)

        # Existing items for JS
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
            total   = sum(oi.quantity * oi.unit_price for oi in (pending.items.all() if pending else []))
            t.current_order_total = f"{total:.2f}"
            t.has_items           = (total > 0)

        return render(request, "orders/order_form.html", {
            "categories":          categories,
            "all_menu_items_json": all_menu_items_json,
            "all_deals_json":      all_deals_json,
            "existing_items_json": existing_items_json,
            "order":               order,
            "tables":              tables,
            "waiters_json": waiters_json,
        })


    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        # 1) Update order fields
        waiter_id = data.get("waiter_id") or None
        is_home_delivery = data.get("isHomeDelivery") or None
        order.discount       = data.get("discount", 0) or 0
        order.tax_percentage = data.get("tax_percentage", 0) or 0
        order.service_charge = data.get("service_charge", 0) or 0
        order.table_id     = data.get("table_id")
        action               = data.get("action", "update")
        order.status         = "paid" if action == "paid" else "pending"
        order.waiter_id = waiter_id
        order.is_home_delivery = is_home_delivery
        order.save()

        # 2) Table occupancy
        if order.table_id is not None:
            tbl = Table.objects.get(pk=order.table_id)
            tbl.is_occupied = (order.status != "paid")
            tbl.save()

        # 3) Diff algorithm for OrderItems
        incoming = data.get("items", [])
        # build map of existing items by (menu_id, deal_id)
        existing_map = {
            (oi.menu_item_id, oi.deal_id): oi
            for oi in order.items.all()
        }

        # process incoming items
        for it in incoming:
            if it.get("type") == "menu":
                key = (it["menu_item_id"], None)
                m_id, d_id = it["menu_item_id"], None
            else:
                key = (None, it["deal_id"])
                m_id, d_id = None, it["deal_id"]

            if key in existing_map:
                # update existing
                oi = existing_map.pop(key)
                oi.quantity   = it["quantity"]
                oi.unit_price = it["unit_price"]
                oi.save()   # preserves token_printed
            else:
                # create brand‑new → token_printed defaults to False
                OrderItem.objects.create(
                    order=order,
                    menu_item_id=m_id,
                    deal_id=d_id,
                    quantity=it["quantity"],
                    unit_price=it["unit_price"]
                )

        # anything still in existing_map was removed by user → delete
        for oi in existing_map.values():
            oi.delete()

        # 4) If marking paid, print receipts
        if order.status == "paid":
            try:
                ps           = PrintStatus.objects.first()
                token_on     = ps.token if ps else False
                bill_on      = ps.bill  if ps else False

                if token_on:
                    token_data = build_token_bytes(order)
                    send_to_printer(token_data)
                if bill_on:
                    bill_data  = build_bill_bytes(order)
                    send_to_printer(bill_data)

                # free the table
                if order.table_id is not None:
                    tbl = Table.objects.get(pk=order.table_id)
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



from decimal import Decimal

import os
from django.conf import settings
from .escpos_logo import logo_to_escpos_bytes

def build_token_bytes(order, is_food_panda = "walk_in"):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Insert the logo at the very top ───────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "static/img/logo.png")
    try:
        logo_bytes = logo_to_escpos_bytes(logo_path)
        # lines.append(logo_bytes)
        # Add a blank line after logo so text doesn't overlap
        lines.append(b"\n")
    except Exception as e:
        # If logo read fails, skip gracefully
        lines.append(b"")  

    # ─── Restaurant name, larger/bold ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center alignment
    lines.append(esc + b"\x21" + b"\x30")   # double height & width
    lines.append(b"Cafe Kunj\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal
    lines.append(b"\n")

    # ─── Header “KITCHEN TOKEN” ───────────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center
    lines.append(b"KITCHEN TOKEN\n\n")

    if is_food_panda == "food_panda":
        lines.append(esc + b"\x61" + b"\x01")   # center
        lines.append(b"FOOD PANDA Order\n\n")
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
    if order.waiter:
        waiter_bytes = f"Waiter: {order.waiter.name}\n".encode("ascii", "ignore")
        lines.append(waiter_bytes)
    lines.append(b"-" * 32 + b"\n")         # 32-char full width separator


    # ─── Order Items List (left name, right qty) ─────────────────────────
    new_items = order.items.filter(token_printed=False)
    for oi in new_items:
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        qty_bytes = str(oi.quantity).rjust(3).encode("ascii")
        lines.append(name_field + b"  x" + qty_bytes + b"\n")

    lines.append(b"\n\n")
    # ─── Feed + Cut ────────────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")    # full cut

    return b"".join(lines)



def build_bill_bytes(order, is_food_panda = "walk_in"):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Logo at top ──────────────────────────────────────────────────────
    logo_path = os.path.join(settings.BASE_DIR, "media\img\logo.png")
    print(f"Logo Path: {logo_path}")
    try:
        image_data = logo_to_escpos_bytes(logo_path)
        print(f"Image Data: {image_data.hex()[:100]}...")  # Print the first 200 bytes of the image data

        # lines.append(image_data)
        lines.append(b"\n")
    except Exception as e:
        print(f"Error converting logo: {e}")
        lines.append(b"")

    # ─── Restaurant name, double size ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")
    lines.append(esc + b"\x21" + b"\x30")
    lines.append(b"Cafe Kunj\n")
    lines.append(esc + b"\x21" + b"\x00")
    lines.append(b"\n")
    
    if is_food_panda == "food_panda":
        lines.append(esc + b"\x61" + b"\x01")   # center
        lines.append(b"FOOD PANDA Order\n\n")
    
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
    lines.append(b"-" * 40 + b"\n\n")
    lines.append(b"Home Delivery Contact: +92 303 6686039\n\n")
    lines.append(esc + b"\x61" + b"\x00")   # left align
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
    lines.append(b"Thank you for your support!\n\n\n")
    lines.append(b"\n" * 4)

    # ─── Cut paper (full) ─────────────────────────────────────────────────
    lines.append(gs + b"\x56" + b"\x00")

    return b"".join(lines)


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



def build_token_bytes_for_deltas(order, items_with_delta):
    """
    Build an ESC/POS payload containing only the given OrderItem queryset.
    """
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []
    
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
    table_number = str(order.table.number).encode("ascii")
    lines.append(esc + b"\x61" + b"\x01")   # center
    lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x10 → double width, normal height
    lines.append(b"TOKEN #: " + token_str + b"\n\n")
    lines.append(b"Table #: "+ table_number + b"\n\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal

    # ─── Date / Time ──────────────────────────────────────────────────────
    now_str = order.created_at.strftime("%Y-%m-%d %H:%M").encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"Date: " + now_str + b"\n")
    lines.append(b"-" * 32 + b"\n")         # 32-char full width separator

    # ─── Only the new items ─────────────────────────────────────────────
    for oi, delta in items_with_delta:
        # truncate name to 20 chars
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        qty_bytes  = str(delta).rjust(3).encode("ascii")
        lines.append(name_field + b"  x" + qty_bytes + b"\n")

    lines.append(b"\n\n\n\n")
    # ─── feed + cut ─────────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")    # full cut

    return b"".join(lines)

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

        # ─── NEW: fetch only items not yet printed ──────────────────────
        items_to_print = []
        for oi in order.items.all():
            delta = oi.quantity - oi.printed_quantity
            if delta > 0:
                items_to_print.append((oi, delta))

        if items_to_print:
            payload = build_token_bytes_for_deltas(order, items_to_print)
            send_to_printer(payload)
            # mark them as “now fully printed”
            for oi, _ in items_to_print:
                oi.printed_quantity = oi.quantity
                oi.save(update_fields=['printed_quantity'])
        
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


from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.http import JsonResponse
from .models import Supplier
from .views import AjaxableResponseMixin  # reuse your existing mixin
from django.contrib.auth.mixins import LoginRequiredMixin

# --- Suppliers CRUD ---
class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = 'suppliers/supplier_list.html'
    context_object_name = 'suppliers'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by('-created_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs

class SupplierCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = Supplier
    fields = ['name','contact_number','email','address']
    template_name = 'suppliers/supplier_form.html'
    success_url = reverse_lazy('supplier_list')

class SupplierDetailView(LoginRequiredMixin, DetailView):
    model = Supplier
    template_name = 'suppliers/supplier_detail.html'
    context_object_name = 'supplier'

class SupplierUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = Supplier
    fields = ['name','contact_number','email','address']
    template_name = 'suppliers/supplier_form.html'
    success_url = reverse_lazy('supplier_list')

class SupplierDeleteView(LoginRequiredMixin, DeleteView):
    model = Supplier
    success_url = reverse_lazy('supplier_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message': 'Deleted'})
        return super().delete(request, *args, **kwargs)


from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import RawMaterial
from .views import AjaxableResponseMixin  # your existing mixin

# --- Raw Materials CRUD ---
class RawMaterialListView(LoginRequiredMixin, ListView):
    model = RawMaterial
    template_name = 'raw_materials/rawmaterial_list.html'
    context_object_name = 'materials'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier').order_by('-created_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs

class RawMaterialCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = RawMaterial
    fields = ['name', 'unit', 'supplier', 'current_stock', 'reorder_level']
    template_name = 'raw_materials/rawmaterial_form.html'
    success_url = reverse_lazy('raw_material_list')

class RawMaterialDetailView(LoginRequiredMixin, DetailView):
    model = RawMaterial
    template_name = 'raw_materials/rawmaterial_detail.html'
    context_object_name = 'material'

class RawMaterialUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = RawMaterial
    fields = ['name', 'unit', 'supplier', 'current_stock', 'reorder_level']
    template_name = 'raw_materials/rawmaterial_form.html'
    success_url = reverse_lazy('raw_material_list')

class RawMaterialDeleteView(LoginRequiredMixin, DeleteView):
    model = RawMaterial
    success_url = reverse_lazy('raw_material_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message': 'Deleted'})
        return super().delete(request, *args, **kwargs)


import json
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import RawMaterial, PurchaseOrder, PurchaseOrderItem, InventoryTransaction
from .views import AjaxableResponseMixin  # your existing mixin

# --- Purchase Orders CRUD ---
class PurchaseOrderListView(LoginRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = 'purchase_orders/purchaseorder_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier','created_by').order_by('-created_at')
        q = self.request.GET.get('q')
        if q:
            return qs.filter(supplier__name__icontains=q)
        return qs

class PurchaseOrderCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = PurchaseOrder
    fields = ['supplier']
    template_name = 'purchase_orders/purchaseorder_form.html'
    success_url = reverse_lazy('purchase_order_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # serialize raw materials
        rms = RawMaterial.objects.select_related('supplier').order_by('name')
        ctx['raw_materials_json'] = json.dumps([
            {'pk': rm.pk, 'name': rm.name, 'unit': rm.unit}
            for rm in rms
        ])
        ctx['initial_po_items'] = []
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        data = json.loads(self.request.POST.get('po_items_json','[]'))
        total = 0
        for it in data:
            qty = it['quantity']
            up  = it['unit_price']
            PurchaseOrderItem.objects.create(
                purchase_order=self.object,
                raw_material_id=it['raw_material_id'],
                quantity=qty,
                unit_price=up
            )
            total += qty * up
        self.object.total_cost = total
        self.object.save()
        return resp

class PurchaseOrderUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = PurchaseOrder
    fields = ['supplier']
    template_name = 'purchase_orders/purchaseorder_form.html'
    success_url = reverse_lazy('purchase_order_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rms = RawMaterial.objects.select_related('supplier').order_by('name')
        ctx['raw_materials_json'] = json.dumps([
            {'pk': rm.pk, 'name': rm.name, 'unit': rm.unit}
            for rm in rms
        ])
        ctx['initial_po_items'] = [
            {
                'raw_material_id': pi.raw_material_id,
                'quantity': float(pi.quantity),
                'unit_price': float(pi.unit_price)
            }
            for pi in self.object.items.all()
        ]
        return ctx

    def form_valid(self, form):
        # delete old items
        PurchaseOrderItem.objects.filter(purchase_order=self.object).delete()
        resp = super().form_valid(form)
        data = json.loads(self.request.POST.get('po_items_json','[]'))
        total = 0
        for it in data:
            qty = it['quantity']
            up  = it['unit_price']
            poi = PurchaseOrderItem.objects.create(
                purchase_order=self.object,
                raw_material_id=it['raw_material_id'],
                quantity=qty,
                unit_price=up
            )
            total += qty * up
        self.object.total_cost = total
        self.object.save()
        return resp

class PurchaseOrderDetailView(LoginRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = 'purchase_orders/purchaseorder_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # stock‑in transactions for this PO
        ctx['transactions'] = InventoryTransaction.objects.filter(
            purchase_order_item__purchase_order=self.object
        ).order_by('-timestamp')
        return ctx

class PurchaseOrderDeleteView(LoginRequiredMixin, DeleteView):
    model = PurchaseOrder
    success_url = reverse_lazy('purchase_order_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message':'Deleted'})
        return super().delete(request, *args, **kwargs)

@require_POST
def purchase_order_receive(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    po.mark_received()
    return JsonResponse({'status':'success'})


def get_avg_unit_cost(raw_material):
    agg = PurchaseOrderItem.objects.filter(
        purchase_order__status='received',
        raw_material=raw_material
    ).aggregate(
        total_cost=Sum(F('quantity') * F('unit_price')),
        total_qty=Sum('quantity')
    )
    total_cost = agg['total_cost'] or Decimal('0')
    total_qty  = agg['total_qty']  or Decimal('0')
    return (total_cost / total_qty) if total_qty else Decimal('0')

def recipe_cost(recipe):
    cost = Decimal('0')
    # raw-material ingredients
    for ingr in recipe.raw_ingredients.all():
        rm    = ingr.raw_material
        # find conversion to base unit (e.g. grams)
        conv  = RawMaterialUnitConversion.objects.get(
                    raw_material=rm, unit=ingr.unit
               ).to_base_factor
        qty   = ingr.quantity * Decimal(conv)
        avg_c = get_avg_unit_cost(rm)
        cost += qty * avg_c
    # nested sub-recipes
    for sub in recipe.subrecipes.all():
        cost += recipe_cost(sub.sub_recipe) * Decimal(sub.quantity)
    return cost


from decimal import Decimal
from datetime import date

from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, F, DecimalField

from .models import (
    RawMaterial,
    RawMaterialUnitConversion,
    MenuItem,
    Deal,
    OrderItem,
)

class CostReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/cost_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()

        # reuse compute_recipe_cost for menu items
        item_rows = []
        for mi in MenuItem.objects.prefetch_related('recipe__raw_ingredients',
                                                      'recipe__subrecipes__sub_recipe'):
            cost = compute_recipe_cost(mi.recipe) if hasattr(mi, 'recipe') else Decimal('0')
            sold = OrderItem.objects.filter(menu_item=mi,
                                            order__created_at__date=today)\
                                     .aggregate(q=Sum('quantity'))['q'] or 0
            item_rows.append({
                'name': mi.name,
                'avg_cost_price': cost,
                'sold_qty_today': sold,
                'total_cost_today': cost * sold,
            })

        deal_rows = []
        for dl in Deal.objects.prefetch_related('deal_items__menu_item'):
            dcost = sum((next((r['avg_cost_price'] for r in item_rows if r['name']==di.menu_item.name), Decimal('0')) * di.quantity)
                        for di in dl.deal_items.all())
            sold = OrderItem.objects.filter(deal=dl,
                                            order__created_at__date=today)\
                                     .aggregate(q=Sum('quantity'))['q'] or 0
            deal_rows.append({
                'name': dl.name,
                'avg_cost_price': dcost,
                'sold_qty_today': sold,
                'total_cost_today': dcost * sold,
            })

        ctx.update({
            'today': today,
            'item_rows': item_rows,
            'deal_rows': deal_rows,
        })
        return ctx

#recipe

import json
from decimal import Decimal
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import (
    ListView, CreateView, DetailView, UpdateView, DeleteView
)
from django.contrib.auth.mixins import LoginRequiredMixin
from .views import AjaxableResponseMixin
from .models import (
    Recipe, RecipeRawMaterial, RecipeSubRecipe,
    RawMaterial, RawMaterialUnitConversion,
    InventoryTransaction, MenuItem, Unit
)

# core/views.py (at top of file)
import json
from decimal import Decimal
from django.db.models import Sum, F, DecimalField
from .models import (
    RawMaterial,
    RawMaterialUnitConversion,
    Unit,
    PurchaseOrderItem,
    Recipe, RecipeRawMaterial, RecipeSubRecipe
)

from decimal import Decimal, getcontext
from django.db import models

from .models import (
    RawMaterialUnitConversion,
    PurchaseOrderItem,
    RawMaterial,
    Unit,
)

# bump precision a bit
getcontext().prec = 28

def compute_recipe_cost(recipe):
    """
    1) Build a (raw_material, unit) → base‑factor map
    2) For each raw_material in this recipe, scan ALL its PO‑lines:
         • convert each PO.quantity into base units
         • sum cost = qty * unit_price
       then avg_cost_per_base = total_cost ÷ total_base_qty
    3) Multiply each ingredient’s recipe.quantity (in its own unit) 
       × that same base factor × avg_cost_per_base
    4) Recurse into any sub‑recipes
    """
    # 1) load all unit conversions into memory
    convs = {
        (c.raw_material_id, c.unit_id): Decimal(c.to_base_factor)
        for c in RawMaterialUnitConversion.objects.all()
    }

    # helper to get the average cost per **base** unit for a given raw_material
    _cache = {}
    def cost_per_base(rm_id):
        if rm_id in _cache:
            return _cache[rm_id]

        # gather all PO‑lines for this material
        pois = PurchaseOrderItem.objects.filter(raw_material_id=rm_id)
        total_cost = Decimal('0')
        total_base_qty = Decimal('0')

        # figure out which unit they used on purchase
        raw = RawMaterial.objects.get(pk=rm_id)
        try:
            pu = Unit.objects.get(symbol=raw.unit)
        except Unit.DoesNotExist:
            # fallback: assume 1:1
            pu = None

        for poi in pois:
            q = Decimal(poi.quantity)
            p = Decimal(poi.unit_price)
            total_cost += q * p

            # convert that PO quantity into base units
            if pu:
                factor = convs.get((rm_id, pu.pk), Decimal('1'))
            else:
                factor = Decimal('1')
            total_base_qty += q * factor

        avg = (total_cost / total_base_qty) if total_base_qty else Decimal('0')
        _cache[rm_id] = avg
        return avg

    # 2) now compute this recipe’s cost
    total = Decimal('0')
    for ingr in recipe.raw_ingredients.all():
        rm_id = ingr.raw_material_id
        qty   = Decimal(ingr.quantity)

        # convert recipe qty → base
        factor = convs.get((rm_id, ingr.unit_id), Decimal('1'))
        base_qty = qty * factor

        # cost per base
        cpb = cost_per_base(rm_id)
        total += base_qty * cpb

    # 3) nested sub‑recipes
    for sub in recipe.subrecipes.all():
        sub_cost = compute_recipe_cost(sub.sub_recipe)
        total   += sub_cost * Decimal(sub.quantity)

    return total.quantize(Decimal('0.01'))

# --- List & Detail ---
class RecipeListView(LoginRequiredMixin, ListView):
    model = Recipe
    template_name = 'recipes/recipe_list.html'
    context_object_name = 'recipes'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('menu_item')
        q = self.request.GET.get('q')
        return qs.filter(menu_item__name__icontains=q) if q else qs

class RecipeDetailView(LoginRequiredMixin, DetailView):
    model = Recipe
    template_name = 'recipes/recipe_detail.html'
    context_object_name = 'recipe'


# --- Create & Update ---
class RecipeCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = Recipe
    fields = ['menu_item', 'name']
    template_name = 'recipes/recipe_form.html'
    success_url = reverse_lazy('recipe_list')

    def get_context_data(self, **ctx):
        data = super().get_context_data(**ctx)
        # raw materials
        rms = RawMaterial.objects.order_by('name')
        data['raw_materials_json'] = json.dumps([
            {'pk': rm.pk, 'name': rm.name, 'unit': rm.unit}
            for rm in rms
        ])
        # units
        from .models import Unit
        units = Unit.objects.all()
        data['units_json'] = json.dumps([
            {'pk': u.pk, 'symbol': u.symbol} for u in units
        ])
        # existing recipes for nesting
        recs = Recipe.objects.all()
        data['recipes_json'] = json.dumps([
            {'pk': r.pk, 'name': r.menu_item.name} for r in recs
        ])
        data['initial_raw'] = []
        data['initial_sub'] = []
        return data

    def form_valid(self, form):
        resp = super().form_valid(form)
        recipe = self.object
        # clear old if any (should be none)
        RecipeRawMaterial.objects.filter(recipe=recipe).delete()
        RecipeSubRecipe.objects.filter(recipe=recipe).delete()

        raw_data = json.loads(self.request.POST.get('raw_json','[]'))
        for it in raw_data:
            RecipeRawMaterial.objects.create(
                recipe=recipe,
                raw_material_id=it['raw_material_id'],
                quantity=Decimal(str(it['quantity'])),
                unit_id=it['unit_id']
            )

        sub_data = json.loads(self.request.POST.get('sub_json','[]'))
        for it in sub_data:
            RecipeSubRecipe.objects.create(
                recipe=recipe,
                sub_recipe_id=it['sub_recipe_id'],
                quantity=Decimal(str(it['quantity'])),
                unit_id=it['unit_id']
            )

        # update menu_item.cost_price
        cost = compute_recipe_cost(recipe)
        mi = recipe.menu_item
        mi.cost_price = cost
        mi.save(update_fields=['cost_price'])

        return resp

class RecipeUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = Recipe
    fields = ['menu_item', 'name']
    template_name = 'recipes/recipe_form.html'
    success_url = reverse_lazy('recipe_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        # 1) All raw materials
        rms = RawMaterial.objects.order_by('name')
        data['raw_materials_json'] = json.dumps([
            {'pk': rm.pk, 'name': rm.name, 'unit': rm.unit}
            for rm in rms
        ])

        # 2) All units
        units = Unit.objects.all()
        data['units_json'] = json.dumps([
            {'pk': u.pk, 'symbol': u.symbol}
            for u in units
        ])

        # 3) All other recipes (for nesting), excluding this one
        recs = Recipe.objects.exclude(pk=self.object.pk)
        data['recipes_json'] = json.dumps([
            {'pk': r.pk, 'name': r.menu_item.name}
            for r in recs
        ])

        # 4) Existing raw‑ingredient lines, as JSON
        initial_raw = [
            {
                'raw_material_id': ri.raw_material_id,
                'quantity': float(ri.quantity),
                'unit_id': ri.unit_id
            }
            for ri in self.object.raw_ingredients.all()
        ]
        data['initial_raw_json'] = json.dumps(initial_raw)

        # 5) Existing sub‑recipe lines, as JSON
        initial_sub = [
            {
                'sub_recipe_id': sr.sub_recipe_id,
                'quantity': float(sr.quantity),
                'unit_id': sr.unit_id
            }
            for sr in self.object.subrecipes.all()
        ]
        data['initial_sub_json'] = json.dumps(initial_sub)

        return data

    def form_valid(self, form):
        # 1) Save the Recipe core fields
        response = super().form_valid(form)
        recipe = self.object

        # 2) Wipe & recreate all raw‑material links
        RecipeRawMaterial.objects.filter(recipe=recipe).delete()
        raw_data = json.loads(self.request.POST.get('raw_json', '[]'))
        for it in raw_data:
            RecipeRawMaterial.objects.create(
                recipe=recipe,
                raw_material_id=it['raw_material_id'],
                quantity=Decimal(str(it['quantity'])),
                unit_id=it['unit_id']
            )

        # 3) Wipe & recreate all sub‑recipe links
        RecipeSubRecipe.objects.filter(recipe=recipe).delete()
        sub_data = json.loads(self.request.POST.get('sub_json', '[]'))
        for it in sub_data:
            RecipeSubRecipe.objects.create(
                recipe=recipe,
                sub_recipe_id=it['sub_recipe_id'],
                quantity=Decimal(str(it['quantity'])),
                unit_id=it['unit_id']
            )

        # 4) Recompute & store the MenuItem's cost_price
        cost = compute_recipe_cost(recipe)
        mi = recipe.menu_item
        mi.cost_price = cost
        mi.save(update_fields=['cost_price'])

        return response

class RecipeDeleteView(LoginRequiredMixin, AjaxableResponseMixin, DeleteView):
    model = Recipe
    success_url = reverse_lazy('recipe_list')


import json
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import Waiter
from .views import AjaxableResponseMixin  # your existing mixin

# — Waiters CRUD —

class WaiterListView(LoginRequiredMixin, ListView):
    model = Waiter
    template_name = 'waiters/waiter_list.html'
    context_object_name = 'waiters'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().order_by('-created_at')
        q = self.request.GET.get('q')
        return qs.filter(name__icontains=q) if q else qs


class WaiterCreateView(LoginRequiredMixin, AjaxableResponseMixin, CreateView):
    model = Waiter
    fields = ['name', 'employee_id', 'phone']
    template_name = 'waiters/waiter_form.html'
    success_url = reverse_lazy('waiter_list')


class WaiterDetailView(LoginRequiredMixin, DetailView):
    model = Waiter
    template_name = 'waiters/waiter_detail.html'
    context_object_name = 'waiter'


class WaiterUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = Waiter
    fields = ['name', 'employee_id', 'phone']
    template_name = 'waiters/waiter_form.html'
    success_url = reverse_lazy('waiter_list')


class WaiterDeleteView(LoginRequiredMixin, DeleteView):
    model = Waiter
    success_url = reverse_lazy('waiter_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.is_ajax():
            return JsonResponse({'message':'Deleted'})
        return super().delete(request, *args, **kwargs)
