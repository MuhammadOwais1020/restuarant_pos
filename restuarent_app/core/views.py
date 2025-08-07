from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .license_check import enforce_authorization
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import InventoryTransaction, PrintStatus, PurchaseOrder, RawMaterial, Recipe, RecipeRawMaterial, RecipeSubRecipe
from django.views.decorators.http import require_POST
from .models import Unit

from .printing import send_to_printer
from .utils import recipe_cost_and_weight

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

from django.db.models import Max
from django.utils import timezone

def get_next_token_number():
    last_order   = Order.objects.aggregate(m=Max('token_number'))['m'] or 0
    last_session = TableSession.objects.aggregate(m=Max('token_number'))['m'] or 0
    return max(last_order, last_session) + 1

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
    fields = ['name', 'description', 'rank',  'show_in_orders']
    template_name = 'categories/category_form.html'
    success_url = reverse_lazy('category_list')

class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'categories/category_detail.html'
    context_object_name = 'category'

class CategoryUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = Category
    fields = ['name', 'description', 'rank',  'show_in_orders']
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
    fields = ['category', 'name', 'description', 'price', 'food_panda_price', 'rank', 'is_available', 'image']
    template_name = 'menu_items/menuitem_form.html'
    success_url = reverse_lazy('menuitem_list')

class MenuItemDetailView(LoginRequiredMixin, DetailView):
    model = MenuItem
    template_name = 'menu_items/menuitem_detail.html'
    context_object_name = 'item'

class MenuItemUpdateView(LoginRequiredMixin, AjaxableResponseMixin, UpdateView):
    model = MenuItem
    fields = ['category', 'name', 'description', 'price', 'food_panda_price', 'rank', 'is_available', 'image']
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
    fields = ['name', 'description', 'price', 'food_panda_price', 'rank', 'is_available', 'image']
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
    fields = ['name', 'description', 'price', 'food_panda_price', 'rank', 'is_available', 'image']
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
from django.utils.dateparse import parse_datetime

from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import Order, Payment

class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_paginate_by(self, queryset):
        # Turn off pagination if either date filter is present
        if self.request.GET.get('date_from') or self.request.GET.get('date_to'):
            return None
        return super().get_paginate_by(queryset)

    def get_queryset(self):
        qs = super().get_queryset().select_related('table', 'created_by').order_by('-created_at')

        q         = self.request.GET.get('q')
        status    = self.request.GET.get('status')
        date_from = self.request.GET.get('date_from')
        date_to   = self.request.GET.get('date_to')

        if q:
            qs = qs.filter(number__icontains=q)
        if status:
            qs = qs.filter(status=status)

        if date_from:
            dt = parse_datetime(date_from)
            if dt:
                qs = qs.filter(created_at__gte=timezone.make_aware(dt))
        if date_to:
            dt = parse_datetime(date_to)
            if dt:
                qs = qs.filter(created_at__lte=timezone.make_aware(dt))

        line_total = ExpressionWrapper(
            F('items__quantity') * F('items__unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
        qs = qs.annotate(subtotal=Sum(line_total))
        qs = qs.annotate(
            total_amount=ExpressionWrapper(
                (F('subtotal') - F('discount'))
                + (F('subtotal') * F('tax_percentage') / 100)
                + F('service_charge'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        orders_list = ctx['orders']  # page or full list

        # serial numbering
        if ctx.get('is_paginated'):
            ctx['start_index'] = ctx['page_obj'].start_index()
        else:
            ctx['start_index'] = 1

        # per‐page (or overall) total
        ctx['page_total'] = sum(
            (o.total_amount or Decimal('0')) for o in orders_list
        )

        # summary for the entire filtered set
        full_qs = self.get_queryset()
        ctx['summary_total_orders']  = full_qs.count()
        ctx['summary_total_amount']  = full_qs.aggregate(
            total=Sum(F('items__quantity') * F('items__unit_price'))
        )['total'] or Decimal('0')
        ctx['summary_received']      = Payment.objects.filter(
            order__in=full_qs
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        ctx['summary_remaining']     = ctx['summary_total_amount'] - ctx['summary_received']

        # keep the filters in the form
        ctx['date_from'] = self.request.GET.get('date_from', '')
        ctx['date_to']   = self.request.GET.get('date_to', '')

        return ctx

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
from django.utils import timezone

class OrderCreateView(LoginRequiredMixin, View):

    def get(self, request):
        categories = (
            Category.objects
                .filter(show_in_orders=True)
                .order_by('rank')
                .prefetch_related('items')
        )
        all_waiters = Waiter.objects.order_by('name').values('id','name')
        waiters_json = json.dumps(list(all_waiters))

        # Serialize menu items
        # all_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')
        all_menu_items = MenuItem.objects.filter(is_available=True)\
        .select_related('category')\
        .order_by('rank')

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

        initial_po_items_json = json.dumps([])

        # Annotate tables with pending totals and has_items flag
        tables = list(Table.objects.all().order_by("number"))
        # prefetch all sessions + their picked_items in one go
        sessions = TableSession.objects\
            .prefetch_related('picked_items')\
            .all()\
            .in_bulk(field_name='table_id')
        
        for t in tables:
            sess = sessions.get(t.id)
            if sess:
                # sum(qty × unit_price) across all picked_items
                total = sum(
                    pi.quantity * pi.unit_price
                    for pi in sess.picked_items.all()
                )
                t.current_order_total = f"{total:.2f}"
                t.has_items = total > 0
            else:
                t.current_order_total = "0.00"
                t.has_items = False

        return render(request, "orders/order_form.html", {
            "categories": categories,
            "all_menu_items_json": all_menu_items_json,
            "all_deals_json": all_deals_json,
            "initial_po_items_json": initial_po_items_json,
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
        mobile_no  = data.get("mobileNo") or None
        customer_address = data.get("customerAddress") or None
        customer_name = data.get("customerName") or None

        # Fetch the Waiter instance (if waiter_id is provided and valid)
        if waiter_id:
            try:
                waiter = Waiter.objects.get(id=waiter_id)
            except Waiter.DoesNotExist:
                return JsonResponse({"error": "Invalid waiter_id"}, status=400)
        else:
            waiter = None  # If no waiter_id is provided, leave it as None

        source_value =  is_food_panda
        my_datetime = timezone.localtime(timezone.now())

        status_value = "paid" if action == "paid" else "pending"
        if table_id:
            status_value = "pending"

        order = Order.objects.create(
            created_by=user,
            table_id=table_id,
            discount=discount,
            tax_percentage=tax_percentage,
            service_charge=service_charge,
            status=status_value,
            source=source_value,
            waiter=waiter,
            isHomeDelivery = is_home_delivery,
            mobile_no = mobile_no,
            customer_name = customer_name,
            customer_address = customer_address,
            created_at=my_datetime,
        )
        
        # — if this was for a table, steal its session’s token_number — 
        if table_id:
            session = TableSession.objects.get(table_id=table_id)
            order.token_number = session.token_number
            order.save(update_fields=['token_number'])

            session = TableSession.objects.get(table_id=order.table_id)
            session.token_number = None
            session.save(update_fields=['token_number'])
        else:
            order.token_number = get_next_token_number()
            order.save(update_fields=['token_number'])


        print(f'Status Value: {status_value}')
        print(f"Date time now {timezone.localtime(timezone.now())}")
        if table_id and status_value != "paid":
            tbl = Table.objects.get(pk=table_id)
            tbl.is_occupied = True
            tbl.save()
            print(f"1. Table {table_id}: occupied {tbl.is_occupied} for Order # {order.pk}")
        
        total_price = 0
        
        for it in items:
            unit_price = it["unit_price"]
            # Check if the source is "Food Panda"
            if is_food_panda == "food_panda":
                if it.get("type") == "menu":
                    menu_item = MenuItem.objects.get(pk=it["menu_item_id"])
                    unit_price = menu_item.food_panda_price if menu_item.food_panda_price else menu_item.price
                    total_price += unit_price
                elif it.get("type") == "deal":
                    deal = Deal.objects.get(pk=it["deal_id"])
                    unit_price = deal.food_panda_price if deal.food_panda_price else deal.price
                    total_price += unit_price
            else:
                # Use default price if not a Food Panda order
                if it.get("type") == "menu":
                    menu_item = MenuItem.objects.get(pk=it["menu_item_id"])
                    unit_price = menu_item.price
                    total_price += unit_price
                elif it.get("type") == "deal":
                    deal = Deal.objects.get(pk=it["deal_id"])
                    unit_price = deal.price
                    total_price += unit_price

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
        
        if not table_id:
            payment = Payment.objects.create(
                    order=order,
                    amount=total_price,
                    method="cash",
                    details = ""
            )


        if status_value == "paid" or status_value == "pending":
                try:
                    ps = PrintStatus.objects.first()
                    bill_enabled  = ps.bill  if ps else False
                    token_enabled = ps.token if ps else False

                    if token_enabled:
                        if not table_id:
                            # token_data = build_token_bytes(order, is_food_panda)
                            # send_to_printer(token_data)

                            # gather only fresh (not-yet-printed) items
                            new_items = list(order.items.filter(token_printed=False))
                            # split out pizza/chai
                            pizza_chai = [
                                oi for oi in new_items
                                if "pizza" in (oi.menu_item.name if oi.menu_item else oi.deal.name).lower()
                                or "chai"  in (oi.menu_item.name if oi.menu_item else oi.deal.name).lower()
                            ]
                            others = [oi for oi in new_items if oi not in pizza_chai]

                            if pizza_chai:
                                token_data = build_token_bytes_for_items(order, pizza_chai, "PIZZA & CHAI TOKEN")
                                send_to_printer(token_data)
                                # print(f"PIZZA CHAI: {pizza_chai}")
                            if others:
                                token_data = build_token_bytes_for_items(order, others, "KITCHEN TOKEN")
                                send_to_printer(token_data)
                                # print(f"Others: {others}")

                    if bill_enabled:
                        bill_data = build_bill_bytes(order, is_food_panda, "Customer Copy")
                        send_to_printer(bill_data)
                        bill_data = build_bill_bytes(order, is_food_panda, "Office Copy")
                        send_to_printer(bill_data)

                    if table_id:

                        # Fetch the table again after making sure the changes are saved
                        tbl = Table.objects.select_for_update().get(pk=table_id)
                        tbl.is_occupied = False
                        tbl.save()
                        print(f"2. Table {table_id}: occupied {tbl.is_occupied} for Order # {order.pk}")

                        # Commit the changes to the database
                        tbl.refresh_from_db()  # This reloads the table object from the DB
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
        initial_po_items_json = json.dumps(existing_items)

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
            "initial_po_items_json": initial_po_items_json,
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
        order.isHomeDelivery = is_home_delivery
        order.save()

        # 2) Table occupancy
        if order.table_id is not None:
            tbl = Table.objects.get(pk=order.table_id)
            tbl.is_occupied = (order.status != "paid")
            tbl.save()
            print(f"1. Update Order Table {order.table_id}: occupied {tbl.is_occupied} for Order # {order.pk}")

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
                    print(f"2. Update Order Table {order.table_id}: occupied {tbl.is_occupied} for Order # {order.pk}")


            except Exception as e:
                return JsonResponse({"error": f"Print failed: {e}"}, status=500)

        return JsonResponse({"message": "Order Updated", "order_id": order.id})



# core/views.py
# core/views.py

from decimal import Decimal
from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import Order

class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.object

        # 1) Compute subtotal as a Decimal
        subtotal = sum(
            oi.quantity * oi.unit_price
            for oi in order.items.all()
        ) or Decimal('0')

        # 2) Pull discounts, tax%, service as Decimals
        discount       = order.discount       or Decimal('0')
        tax_percentage = order.tax_percentage or Decimal('0')
        service_charge = order.service_charge or Decimal('0')

        # 3) Compute tax on (subtotal – discount)
        tax_amount = (subtotal - discount) * tax_percentage / Decimal('100')

        # 4) Grand total
        grand_total = subtotal - discount + tax_amount + service_charge

        ctx.update({
            'subtotal':   subtotal,
            'tax_amount': tax_amount,
            'grand_total': grand_total,
        })
        return ctx



class OrderDeleteView(LoginRequiredMixin, AjaxableResponseMixin, DeleteView):
    model = Order
    success_url = reverse_lazy('order_list')



from decimal import Decimal
from .utils import compute_recipe_cost

import os
from django.conf import settings
from .escpos_logo import logo_to_escpos_bytes

def build_token_bytes(order, is_food_panda = "walk_in"):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Restaurant name, larger/bold ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center alignment
    # lines.append(esc + b"\x21" + b"\x30")   # double height & width
    lines.append(b"Cafe Kunj\n")
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
    

    lines.append(esc + b"\x61" + b"\x01")
    lines.append(esc + b"\x21" + b"\x30")

    if order.isHomeDelivery == "yes":
        lines.append(b"HOME DELIVERY\n\n")
    if order.isHomeDelivery == "no":
        lines.append(b"TAKE AWAY\n\n")

    lines.append(esc + b"\x21" + b"\x00")   # back to normal
    if order.waiter:
        waiter_bytes = f"Waiter: {order.waiter.name}\n".encode("ascii", "ignore")
        lines.append(waiter_bytes)

    
    now_str = order.created_at.strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"Date: " + now_str + b"\n")
    lines.append(b"-" * 32 + b"\n")         # 32-char full width separator
    lines.append(esc + b"\x21" + b"\x10") 

    # ─── Order Items List (left name, right qty) ─────────────────────────
    new_items = order.items.filter(token_printed=False)
    i = 1
    for oi in new_items:
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        serial_number = str(i).encode("ascii", "ignore")
        qty_bytes = str(oi.quantity).rjust(3).encode("ascii")
        lines.append(serial_number + b". " + name_field + b"  x" + qty_bytes + b"\n")
        i += 1

    lines.append(b"\n\n\n\n\n")
    # ─── Feed + Cut ────────────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")    # full cut

    return b"".join(lines)


def build_bill_bytes(order, is_food_panda = "walk_in", copy = ""):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Restaurant name, double size ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")
    lines.append(esc + b"\x21" + b"\x30")
    lines.append(b"Cafe Kunj\n")
    lines.append(esc + b"\x21" + b"\x00")
    lines.append(b"\n")
    
    
    # ─── Order metadata (left) ────────────────────────────────────────────
    order_number_str = str(order.number).encode("ascii")
    token_str = str(order.token_number).encode("ascii")
    copy = str(copy).encode("ascii")
    dt = order.created_at.strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")

    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"" + copy + b"\n")
    lines.append(b"Order #: " + order_number_str + b"\n")
    lines.append(b"Date    : " + dt + b"\n")
    lines.append(b"Token # : " + token_str + b"\n")
    table_number = False
    try:
        table_number = str(order.table.number).encode("ascii")
    except:
        print('')
    if table_number:
        lines.append(b"Table #: "+ table_number + b"\n")
    else:
        if order.isHomeDelivery == "yes":
            lines.append(b"HOME DELIVERY\n\n")
        if order.isHomeDelivery == "no":
            lines.append(b"TAKE AWAY\n\n")
        if order.customer_name:
            customerName = str(order.customer_name).encode("ascii")
            lines.append(b"Customer Name: " + customerName + b"\n")
        if order.mobile_no:
            mobileNo = str(order.mobile_no).encode("ascii")
            lines.append(b"Customer Mobile: " + mobileNo + b"\n")
        if order.customer_address:
            customerAddress = str(order.customer_address).encode("ascii")
            lines.append(b"Customer Add: " + customerAddress + b"\n")

    if order.waiter:
        waiter_bytes = f"Waiter: {order.waiter.name}\n".encode("ascii", "ignore")
        lines.append(waiter_bytes)

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
    lines.append(b"Home Delivery Contact: +92 311 1227749\n\n")
    lines.append(esc + b"\x61" + b"\x00")   # left align
    lines.append(b"-" * 40 + b"\n\n")
    lines.append(esc + b"\x61" + b"\x01")   # center
    # Company name
    lines.append(esc + b"\x21" + b"\x20")   # ESC ! 0x20 → double‐width
    lines.append(b"Barkat Smart POS\n")
    lines.append(esc + b"\x21" + b"\x00")   # back to normal

    # Developer / tagline / contact
    lines.append(b"Developed by Qonkar Technologies\n")
    lines.append(b"www.qonkar.com | +92 305 8214945\n")
    lines.append(b"\n" * 5)

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
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []
    
    # ─── Restaurant name, larger/bold ────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x01")   # center alignment
    lines.append(b"Cafe Kunj\n")
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
    now_str = order.created_at.strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")  # left align
    lines.append(b"Date: " + now_str + b"\n")
    if order.waiter:
        waiter_bytes = f"Waiter: {order.waiter.name}\n".encode("ascii", "ignore")
        lines.append(waiter_bytes)
    lines.append(b"-" * 32 + b"\n")         # 32-char full width separator

    # ─── Only the new items ─────────────────────────────────────────────
    for oi, delta in items_with_delta:
        # truncate name to 20 chars
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        qty_bytes  = str(delta).rjust(3).encode("ascii")
        lines.append(name_field + b"  x" + qty_bytes + b"\n")

    lines.append(b"\n\n\n\n\n")
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

from django.db.models import Q

class TableSwitchView(LoginRequiredMixin, View):

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
        
        # Try to get the first order with 'pending' status for this table, or create one if none exists
        order = Order.objects.filter(table=table, status="pending").first()

        if not order:
            order = Order.objects.create(
                table=table,
                status="pending",
                created_by=request.user
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

from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q


# --- Raw Materials CRUD ---
class RawMaterialListView(LoginRequiredMixin, ListView):
    model = RawMaterial
    template_name = 'raw_materials/rawmaterial_list.html'
    context_object_name = 'materials'
    paginate_by = 300

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier').order_by('-created_at')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q)
        # annotate average unit price from received PurchaseOrderItems
        qs = qs.annotate(
            total_cost=Sum(
                F('purchaseorderitem__quantity') * F('purchaseorderitem__unit_price'),
                filter=Q(purchaseorderitem__purchase_order__status='received'),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            ),
            total_qty=Sum(
                'purchaseorderitem__quantity',
                filter=Q(purchaseorderitem__purchase_order__status='received')
            )
        ).annotate(
            avg_unit_price=ExpressionWrapper(
                F('total_cost') / F('total_qty'),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        )
        return qs

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

import json
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse

from .models import RawMaterial, PurchaseOrder, PurchaseOrderItem
from .views import AjaxableResponseMixin  # your existing mixin

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
        # no existing items on create
        ctx['initial_po_items_json'] = json.dumps([])
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        data = json.loads(self.request.POST.get('po_items_json', '[]'))
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
        # serialize raw materials
        rms = RawMaterial.objects.select_related('supplier').order_by('name')
        ctx['raw_materials_json'] = json.dumps([
            {'pk': rm.pk, 'name': rm.name, 'unit': rm.unit}
            for rm in rms
        ])
        # existing line items → JSON for JS
        existing_items = [
            {
                'raw_material_id': pi.raw_material_id,
                'quantity': float(pi.quantity),
                'unit_price': float(pi.unit_price)
            }
            for pi in self.object.items.all()
        ]
        ctx['initial_po_items_json'] = json.dumps(existing_items)
        return ctx

    def form_valid(self, form):
        # delete old items
        PurchaseOrderItem.objects.filter(purchase_order=self.object).delete()
        resp = super().form_valid(form)
        data = json.loads(self.request.POST.get('po_items_json', '[]'))
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
        # now uses the new weight-aware logic
        item_rows = []
        for mi in MenuItem.objects.prefetch_related(
                 'recipe__raw_ingredients', 'recipe__subrecipes__sub_recipe'):
            if hasattr(mi, 'recipe'):
                 cost = compute_recipe_cost(mi.recipe)
            else:
                 cost = Decimal('0')
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


# core/views.py
from django.shortcuts import render
from decimal import Decimal, getcontext

from .models import MenuItem, RawMaterialUnitConversion, PurchaseOrderItem

# bump precision a bit
getcontext().prec = 28

def debug_costs(request):
    # 1) Build conversion map: (raw_material_id, unit_symbol) -> to_base_factor
    convs = {
        (c.raw_material_id, c.unit.symbol): Decimal(c.to_base_factor)
        for c in RawMaterialUnitConversion.objects.select_related('unit').all()
    }

    # 2) Helper: average cost per **base** unit (g, ml, pcs) for a raw material
    _cache = {}
    def cost_per_base(rm_id):
        if rm_id in _cache:
            return _cache[rm_id]
        pois = PurchaseOrderItem.objects.filter(raw_material_id=rm_id)
        total_cost = Decimal('0')
        total_base = Decimal('0')
        for poi in pois:
            q      = Decimal(poi.quantity)
            p      = Decimal(poi.unit_price)
            symbol = poi.raw_material.unit             # e.g. 'kg' or 'pcs'
            factor = convs.get((rm_id, symbol), Decimal('1'))
            total_base += q * factor
            total_cost += q * p
        avg = (total_cost / total_base) if total_base else Decimal('0')
        _cache[rm_id] = avg
        return avg

    # 3) Recursive breakdown of a recipe
    def breakdown_recipe(recipe):
        raw_lines = []
        for ingr in recipe.raw_ingredients.select_related('raw_material','unit').all():
            rm        = ingr.raw_material
            qty       = Decimal(ingr.quantity)
            symbol    = ingr.unit.symbol
            factor    = convs.get((rm.id, symbol), Decimal('1'))
            base_qty  = qty * factor
            avg_cost  = cost_per_base(rm.id)
            line_cost = base_qty * avg_cost

            # collect PO‐lines for inspection
            po_lines = []
            for poi in PurchaseOrderItem.objects.filter(raw_material_id=rm.id):
                pq     = Decimal(poi.quantity)
                pp     = Decimal(poi.unit_price)
                pf     = convs.get((rm.id, rm.unit), Decimal('1'))
                po_lines.append({
                    'po_qty':            pq,
                    'po_unit_price':     pp,
                    'po_to_base_factor': pf,
                    'po_base_qty':       pq * pf,
                    'po_line_cost':      pq * pp,
                })

            raw_lines.append({
                'name':       rm.name,
                'unit':       symbol,
                'recipe_qty': qty,
                'to_base':    factor,
                'base_qty':   base_qty,
                'avg_cost':   avg_cost,
                'line_cost':  line_cost,
                'po_lines':   po_lines,
            })

        subrecipes = []
        for sub in recipe.subrecipes.select_related('sub_recipe').all():
            sr = sub.sub_recipe
            detail = breakdown_recipe(sr)
            # cost of the FULL sub‐recipe definition
            sub_full_cost = sum(r['line_cost'] for r in detail['raw_lines'])
            # now scale per‐gram
            req = Decimal(sub.quantity)  # interpreted as grams
            per_g = (sub_full_cost / sum(r['base_qty'] for r in detail['raw_lines'])
                     ) if detail['raw_lines'] else Decimal('0')
            subrecipes.append({
                'name':     sr.menu_item.name,
                'qty':      req,
                'detail':   detail,
                'sub_cost': (per_g * req).quantize(Decimal('0.01')),
            })

        total = sum(r['line_cost'] for r in raw_lines) \
              + sum(s['sub_cost']    for s in subrecipes)
        return {
            'raw_lines':  raw_lines,
            'subrecipes': subrecipes,
            'total':      total.quantize(Decimal('0.01')),
        }

    # 4) Assemble per‐MenuItem
    items_debug = []
    for mi in MenuItem.objects.select_related('recipe').all():
        if not hasattr(mi, 'recipe'):
            continue
        detail = breakdown_recipe(mi.recipe)
        items_debug.append({
            'menu_item': mi,
            'detail':    detail,
        })

    return render(request, 'debug_cost.html', {
        'items_debug': items_debug,
    })



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Order, Payment

@csrf_exempt
@login_required
def close_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            order_id = data['order_id']
            payment_method = data['payment_method']
            amount = data['amount']
            details = data['details']

            # Get the order
            order = Order.objects.get(id=order_id, status='pending')
            
            # Create the payment
            payment = Payment.objects.create(
                order=order,
                amount=amount,
                method=payment_method,
                details = details
            )

            # Update order status to 'paid'
            order.status = 'paid'
            order.save()

            # Return success response
            return JsonResponse({'success': True})

        except Order.DoesNotExist:
            return JsonResponse({'error': 'Order not found or already closed'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)


from django.views import View
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from .models import Table, TableSession, TableMenuItem, MenuItem, Deal
from django.db.models import F

class TableSessionView(View):
    """GET session data; POST to set waiter & home_delivery"""
    def get(self, request, table_id):
        table = get_object_or_404(Table, pk=table_id)
        session, created = TableSession.objects.get_or_create(table=table)
        # if brand new (or no token yet), allocate one now
        if created or session.token_number is None:
            session.token_number = get_next_token_number()
            session.save(update_fields=['token_number'])
        data = {
            'waiter_id': session.waiter_id,
            'home_delivery': session.home_delivery,
            'token_number': session.token_number,
        }
        return JsonResponse(data)

    def post(self, request, table_id):
        import json
        payload = json.loads(request.body)
        table = get_object_or_404(Table, pk=table_id)
        session, _ = TableSession.objects.get_or_create(table=table)
        session.waiter_id    = payload.get('waiter_id')
        session.home_delivery = bool(payload.get('home_delivery'))
        session.save()
        return JsonResponse({'status':'ok'})

class TableItemsView(View):
    """GET items; POST to upsert quantity"""
    def get(self, request, table_id):
        session = get_object_or_404(TableSession, table_id=table_id)
        items = session.picked_items.all()
        data = []
        for ti in items:
            model = MenuItem if ti.source_type == 'menu' else Deal
            obj = model.objects.get(pk=ti.source_id)
            data.append({
                'source_type': ti.source_type,
                'source_id': ti.source_id,
                'name': obj.name,
                'quantity': ti.quantity,
                'unit_price': float(ti.unit_price),
                'printed_quantity': ti.printed_quantity,
            })
        return JsonResponse({'items': data})

    def post(self, request, table_id):
        import json
        payload = json.loads(request.body)
        session = get_object_or_404(TableSession, table_id=table_id)
        st = payload['source_type']
        sid = payload['source_id']
        qty = payload.get('quantity', 1)
        up = payload['unit_price']
        obj, created = TableMenuItem.objects.get_or_create(
            session=session,
            source_type=st,
            source_id=sid,
            defaults={'quantity': qty, 'unit_price': up}
        )
        if not created:
            obj.quantity = F('quantity') + qty
            obj.unit_price = up
            obj.save()
        return JsonResponse({'status':'ok'})
    
    def delete(self, request, table_id):
        session = get_object_or_404(TableSession, table_id=table_id)

        # 1) parse and delete
        try:
            payload = json.loads(request.body)
            st = payload['source_type']
            sid = payload['source_id']
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid payload'}, status=400)

        deleted, _ = TableMenuItem.objects.filter(
            session=session,
            source_type=st,
            source_id=sid
        ).delete()

        if not deleted:
            return JsonResponse({'error': 'Item not found'}, status=404)

        # 2) fetch ALL remaining items
        remaining = list(session.picked_items.all())

        # 3) debug‐print to console
        # print(f"[Table {table_id}] after delete, remaining items:")
        # for ti in remaining:
        #     Model = MenuItem if ti.source_type=='menu' else Deal
        #     obj   = Model.objects.get(pk=ti.source_id)
        #     print(f"    • {ti.quantity}× {obj.name} @ {ti.unit_price}")

        # 4) build & send full‐token payload
        # payload = build_full_session_token_bytes(session, remaining)
        # send_to_printer(payload)

        # 5) mark all as printed
        for ti in remaining:
            ti.printed_quantity = 0
            ti.save(update_fields=['printed_quantity'])

        # 6) respond
        return JsonResponse({
            'status': 'deleted_and_printed',
            'count': len(remaining)
        })
    
    def put(self, request, table_id):
        """
        JSON body: { source_type, source_id, quantity }
        Overwrites the quantity on the TableMenuItem for this table.
        """
        import json
        from django.shortcuts import get_object_or_404
        from .models import TableSession, TableMenuItem

        session = get_object_or_404(TableSession, table_id=table_id)
        try:
            payload = json.loads(request.body)
            st  = payload['source_type']
            sid = payload['source_id']
            qty = int(payload['quantity'])
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid payload'}, status=400)

        try:
            tmi = TableMenuItem.objects.get(
                session=session,
                source_type=st,
                source_id=sid
            )
        except TableMenuItem.DoesNotExist:
            return JsonResponse({'error': 'Item not found'}, status=404)

        tmi.quantity = qty
        tmi.save(update_fields=['quantity'])
        return JsonResponse({'status': 'updated'})

def build_full_session_token_bytes(session, items):
    from django.utils import timezone
    from .models import MenuItem, Deal

    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # — Header —
    lines.append(esc + b"\x61" + b"\x01")        # center
    lines.append(esc + b"\x21" + b"\x20")        # double-width
    lines.append(b"UPDATED KITCHEN TOKEN\n")
    lines.append(esc + b"\x21" + b"\x00")        # normal
    lines.append(b"\n")

    token_str = str(session.token_number).encode("ascii")
    lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x10 → double width, normal height
    lines.append(b"TOKEN #: " + token_str + b"\n\n")
    lines.append(esc + b"\x21" + b"\x00")     # back to normal
    lines.append(esc + b"\x61" + b"\x00")     # left

    # — Table # (large) —
    table_no = str(session.table.number).encode("ascii")
    lines.append(esc + b"\x61" + b"\x01")        # center
    lines.append(esc + b"\x21" + b"\x30")        # double-height
    lines.append(b"TABLE #: " + table_no + b"\n\n")
    lines.append(esc + b"\x21" + b"\x00")        # normal

    # — Date / Waiter —
    now = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")        # left
    lines.append(b"Date   : " + now + b"\n")
    if session.waiter:
        waiter = session.waiter.name.encode("ascii", "ignore")
        lines.append(b"Waiter : " + waiter + b"\n")
    lines.append(b"-" * 32 + b"\n")

    # — Columns —
    lines.append(b"#  Item                 Qty\n")
    lines.append(b"-" * 32 + b"\n")

    # — Items —
    for idx, ti in enumerate(items, start=1):
        Model   = MenuItem if ti.source_type == "menu" else Deal
        name    = Model.objects.get(pk=ti.source_id).name[:18]
        idx_f   = str(idx).rjust(2).encode()                     # " 1", " 2", ...
        name_f  = name.ljust(18).encode("ascii", "ignore")       # pad to 18 chars
        qty_f   = str(ti.quantity).rjust(3).encode()             # "  3", etc.
        lines.append(idx_f + b"  " + name_f + b"  " + qty_f + b"\n")

    lines.append(b"\n\n\n\n\n")
    # — Cut —
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")  # full cut

    return b"".join(lines)

class ClearTableItemsView(View):
    """DELETE all items (e.g. after paid)"""
    def delete(self, request, table_id):
        session = get_object_or_404(TableSession, table_id=table_id)
        session.picked_items.all().delete()
        return JsonResponse({'status': 'cleared'})



from django.shortcuts import get_object_or_404
from django.http      import JsonResponse
from django.views     import View
from django.utils     import timezone

from .models          import TableSession, MenuItem, Deal
from .printing        import send_to_printer

class TablePrintTokenView(View):
    def post(self, request, table_id):
        # 1) Load the session
        session = get_object_or_404(TableSession, table_id=table_id)

        if session.token_number is None:
            session.token_number = get_next_token_number()
            session.save(update_fields=['token_number'])

        # 2) Gather all picked_items & compute deltas
        items = session.picked_items.all()
        deltas = [
            (ti, ti.quantity - (ti.printed_quantity or 0))
            for ti in items
        ]
        items_with_delta = [(ti, d) for ti, d in deltas if d != 0]

        # 3) Nothing to print?
        if not items_with_delta:
            # print("[TOKEN DEBUG] nothing to print")
            return JsonResponse({'status': 'nothing_to_print'})
        
        # 3) Split into pizza/chai vs others
        pizza_chai, others = [], []
        for ti, d in items_with_delta:
            Model = MenuItem if ti.source_type=='menu' else Deal
            name  = Model.objects.get(pk=ti.source_id).name.lower()
            if 'pizza' in name or 'chai' in name:
                pizza_chai.append((ti, d))
            else:
                others.append((ti, d))

        # 4) Print each group with a custom header
        if pizza_chai:
            payload = build_group_token_bytes(
                session,
                pizza_chai,
                header_label="PIZZA & CHAI TOKEN"
            )
            print(f"Pizza: {pizza_chai}")
            send_to_printer(payload)

        if others:
            payload = build_group_token_bytes(
                session,
                others,
                header_label="KITCHEN TOKEN"
            )
            print(f"Others: {others}")
            send_to_printer(payload)
        

        # 4) Debug: log each delta
        # print("[TOKEN DEBUG] will print deltas:")
        for ti, delta in items_with_delta:
            Model  = MenuItem if ti.source_type == "menu" else Deal
            name   = Model.objects.get(pk=ti.source_id).name
            action = "Added" if delta > 0 else "Removed"
            # print(f"  • {action} {abs(delta)} × {name} ({ti.source_type})")

        # 5) Build payload
        # payload = build_session_token_bytes(session, items_with_delta)

        # 6) Debug: dump the full payload line-by-line
        # print("[TOKEN DEBUG] full payload:")
        # for line in payload.split(b"\n"):
        #     try:
        #         print("    " + line.decode("ascii"))
        #     except UnicodeDecodeError:
        #         print("    " + repr(line))

        # 7) Send to printer & mark printed
        # send_to_printer(payload)
        for ti, _ in items_with_delta:
            ti.printed_quantity = ti.quantity
            ti.save(update_fields=['printed_quantity'])

        # print(f"[TOKEN DEBUG] sent {len(items_with_delta)} lines to printer")
        return JsonResponse({
            'status': 'printed',
            'count': len(items_with_delta)
        })


def build_session_token_bytes(session, items_with_delta):
    esc = b"\x1B"
    gs  = b"\x1D"
    lines = []

    # ─── Header ─────────────────────────────────────────────────────────────
    has_removal = any(delta < 0 for _, delta in items_with_delta)
    lines.append(esc + b"\x61" + b"\x01")     # center
    lines.append(esc + b"\x21" + b"\x20")     # double-width
    lines.append(
        b"UPDATED KITCHEN TOKEN\n" if has_removal
        else b"KITCHEN TOKEN\n"
    )
    lines.append(b"\n")
    token_str = str(session.token_number).encode("ascii")
    lines.append(esc + b"\x21" + b"\x30")   # ESC ! 0x10 → double width, normal height
    lines.append(b"TOKEN #: " + token_str + b"\n\n")

    lines.append(esc + b"\x21" + b"\x00")     # back to normal
    # ─── Table Number (large) ─────────────────────────────────────────────
    lines.append(esc + b"\x61" + b"\x00")     # left
    table_no = str(session.table.number).encode("ascii")
    lines.append(esc + b"\x61" + b"\x01")     # center
    lines.append(esc + b"\x21" + b"\x30")     # double height & width
    lines.append(b"TABLE #: " + table_no + b"\n\n")
    lines.append(esc + b"\x21" + b"\x00")     # normal

    # ─── Date / Waiter / Mode ─────────────────────────────────────────────
    now = timezone.localtime(timezone.now())\
                   .strftime("%Y-%m-%d %I:%M:%S %p")\
                   .encode("ascii")
    lines.append(esc + b"\x61" + b"\x00")     # left
    lines.append(b"Date  : " + now + b"\n")
    if session.waiter:
        waiter = session.waiter.name.encode("ascii", "ignore")
        lines.append(b"Waiter: " + waiter + b"\n")
    lines.append(b"-" * 32 + b"\n")

    # ─── Column Headers ───────────────────────────────────────────────────
    lines.append(b"#  Item                 Qty\n")
    lines.append(b"-" * 32 + b"\n")

    # ─── Items Section ────────────────────────────────────────────────────
    if has_removal:
        # re-print full current list
        full = session.picked_items.all()
        for idx, ti in enumerate(full, start=1):
            Model = MenuItem if ti.source_type == "menu" else Deal
            name  = Model.objects.get(pk=ti.source_id).name[:18]
            qty   = ti.quantity
            lines.append(
                str(idx).rjust(2).encode() + b"  " +
                name.ljust(18).encode("ascii","ignore") + b"  " +
                str(qty).rjust(3).encode() + b"\n"
            )
    else:
        # only newly added (positive deltas)
        adds = [(ti, d) for ti, d in items_with_delta if d > 0]
        for idx, (ti, d) in enumerate(adds, start=1):
            Model = MenuItem if ti.source_type == "menu" else Deal
            name  = Model.objects.get(pk=ti.source_id).name[:18]
            lines.append(
                str(idx).rjust(2).encode() + b"  " +
                name.ljust(18).encode("ascii","ignore") + b"  " +
                str(d).rjust(3).encode() + b"\n"
            )
    
    lines.append(b"\n\n\n\n\n")
    # ─── Feed + Cut ────────────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(gs + b"\x56" + b"\x00")      # full cut

    return b"".join(lines)



# from django.shortcuts import get_object_or_404
# from django.http      import JsonResponse
# from django.views     import View
# from django.utils     import timezone

# from .models          import TableSession, MenuItem, Deal
# from .printing        import send_to_printer

# class TablePrintTokenView(View):
#     def post(self, request, table_id):
#         # 1) Load the session
#         session = get_object_or_404(TableSession, table_id=table_id)

#         # 2) Compute deltas for every picked_item
#         items = session.picked_items.all()
#         deltas = [
#             (ti, ti.quantity - (ti.printed_quantity or 0))
#             for ti in items
#         ]
#         items_with_delta = [(ti, d) for ti, d in deltas if d != 0]

#         # 3) Nothing changed → nothing to print
#         if not items_with_delta:
#             print("[TOKEN DEBUG] nothing to print")
#             return JsonResponse({'status': 'nothing_to_print'})

#         # 4) Debug output
#         print("[TOKEN DEBUG] will print:")
#         for ti, delta in items_with_delta:
#             Model  = MenuItem if ti.source_type == "menu" else Deal
#             name   = Model.objects.get(pk=ti.source_id).name
#             action = "Added" if delta > 0 else "Removed"
#             print(f" • {action} {abs(delta)} × {name}")

#         # 5) Build & send
#         payload = build_session_token_bytes(session, items_with_delta)
#         send_to_printer(payload)

#         # 6) Mark printed
#         for ti, _ in items_with_delta:
#             ti.printed_quantity = ti.quantity
#             ti.save(update_fields=['printed_quantity'])

#         print(f"[TOKEN DEBUG] sent {len(items_with_delta)} lines")
#         return JsonResponse({'status': 'printed', 'count': len(items_with_delta)})


# def build_session_token_bytes(session, items_with_delta):
#     esc = b"\x1B"
#     gs  = b"\x1D"
#     lines = []

#     # header
#     has_removal = any(delta < 0 for _, delta in items_with_delta)
#     lines.append(esc + b"\x61" + b"\x01")   # center
#     lines.append(esc + b"\x21" + b"\x20")   # double-width
#     lines.append(b"UPDATED KITCHEN TOKEN\n" if has_removal else b"KITCHEN TOKEN\n")
#     lines.append(esc + b"\x21" + b"\x00")   # normal
#     lines.append(b"\n")

#     # table #
#     table_no = str(session.table.number).encode("ascii")
#     lines.append(esc + b"\x61" + b"\x01")
#     lines.append(esc + b"\x21" + b"\x30")
#     lines.append(b"TABLE #: " + table_no + b"\n\n")
#     lines.append(esc + b"\x21" + b"\x00")

#     # date / waiter / mode
#     now = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")
#     lines.append(esc + b"\x61" + b"\x00")
#     lines.append(b"Date  : " + now + b"\n")
#     if session.waiter:
#         wk = session.waiter.name.encode("ascii","ignore")
#         lines.append(b"Waiter: " + wk + b"\n")
#     lines.append(b"-" * 32 + b"\n")

#     # columns
#     lines.append(b"#  Item                 Qty\n")
#     lines.append(b"-" * 32 + b"\n")

#     # items
#     if has_removal:
#         current = session.picked_items.all()
#         for idx, ti in enumerate(current, start=1):
#             Model = MenuItem if ti.source_type=="menu" else Deal
#             name  = Model.objects.get(pk=ti.source_id).name[:18]
#             qty   = ti.quantity
#             lines.append(
#                 str(idx).rjust(2).encode() + b"  " +
#                 name.ljust(18).encode("ascii","ignore") + b"  " +
#                 str(qty).rjust(3).encode() + b"\n"
#             )
#     else:
#         added = [(ti,d) for ti,d in items_with_delta if d>0]
#         for idx,(ti,d) in enumerate(added, start=1):
#             Model = MenuItem if ti.source_type=="menu" else Deal
#             name  = Model.objects.get(pk=ti.source_id).name[:18]
#             lines.append(
#                 str(idx).rjust(2).encode() + b"  " +
#                 name.ljust(18).encode("ascii","ignore") + b"  " +
#                 str(d).rjust(3).encode() + b"\n"
#             )

#     # cut
#     lines.append(b"\n" * 4)
#     lines.append(gs + b"\x56" + b"\x00")

#     return b"".join(lines)


from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from .models import Order, PrintStatus
from .printing import send_to_printer

class OrderReprintView(LoginRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)

        bill_data = build_bill_bytes(order, order.source or 'walk_in', 'Reprint Copy')
        send_to_printer(bill_data)

        return JsonResponse({'status': 'reprinted'})


ESC = b"\x1B"
GS  = b"\x1D"

def build_token_bytes_for_items(order, items, header_label):
    """Builds an ESC/POS kitchen token for a given list of OrderItem."""
    lines = []
    # 1) Header
    lines.append(ESC + b"\x61" + b"\x01")   # center alignment
    # lines.append(esc + b"\x21" + b"\x30")   # double height & width
    lines.append(b"Cafe Kunj\n")
    lines.append(ESC + b"\x21" + b"\x00")   # back to normal
    lines.append(b"\n")

    lines.append(ESC + b"\x61" + b"\x01")              # center
    lines.append(header_label.encode("ascii") + b"\n\n")
    # 2) Token #
    token_str = str(order.token_number).encode("ascii")
    lines.append(ESC + b"\x21" + b"\x30")              # double width
    lines.append(b"TOKEN #: " + token_str + b"\n\n")
    lines.append(ESC + b"\x21" + b"\x00")              # back to normal
    # 3) Date/Time
    dt = order.created_at.strftime("%Y-%m-%d %I:%M:%S %p").encode("ascii")
    lines.append(ESC + b"\x61" + b"\x00")              # left
    lines.append(b"Date: " + dt + b"\n")
    if order.waiter:
        lines.append(f"Waiter: {order.waiter.name}\n".encode("ascii", "ignore"))
    # 4) Delivery / Take-Away
    if order.isHomeDelivery == "yes":
        lines.append(b"HOME DELIVERY\n\n")
    elif order.isHomeDelivery == "no":
        lines.append(b"TAKE AWAY\n\n")
    lines.append(b"-" * 32 + b"\n")
    # 5) Items
    for idx, oi in enumerate(items, 1):
        name = (oi.menu_item.name if oi.menu_item else oi.deal.name)[:20]
        name_field = name.ljust(20).encode("ascii", "ignore")
        qty = str(oi.quantity).rjust(3).encode("ascii")
        lines.append(f"{idx}. ".encode("ascii") + name_field + b" x" + qty + b"\n")
    # 6) Cut

    lines.append(b"\n\n")
    lines.append(b"\n\n\n\n" + GS + b"\x56" + b"\x00")
    return b"".join(lines)


from django.shortcuts import get_object_or_404
from django.http      import JsonResponse
from django.views     import View
from django.utils     import timezone

from .models          import TableSession, MenuItem, Deal
from .printing        import send_to_printer
from .utils           import get_next_token_number

ESC = b"\x1B"
GS  = b"\x1D"

class TablePrintTokenView(View):
    def post(self, request, table_id):
        # 1) Load or create the session token
        session = get_object_or_404(TableSession, table_id=table_id)
        if session.token_number is None:
            session.token_number = get_next_token_number()
            session.save(update_fields=['token_number'])

        # 2) Compute deltas
        items = session.picked_items.all()
        deltas = [(ti, ti.quantity - (ti.printed_quantity or 0)) for ti in items]
        items_with_delta = [(ti, d) for ti, d in deltas if d != 0]
        if not items_with_delta:
            return JsonResponse({'status': 'nothing_to_print'})

        # 3) Split into pizza/chai vs others
        pizza_chai_pairs = []
        other_pairs      = []
        for ti, d in items_with_delta:
            Model = MenuItem if ti.source_type == 'menu' else Deal
            name  = Model.objects.get(pk=ti.source_id).name.lower()
            if 'pizza' in name or 'chai' in name:
                pizza_chai_pairs.append((ti, d))
            else:
                other_pairs.append((ti, d))

        # 4) Print Pizza & Chai token
        if pizza_chai_pairs:
            payload = build_group_token_bytes(
                session,
                pizza_chai_pairs,
                header_label="PIZZA & CHAI TOKEN"
            )
            print(f"Pizza: {pizza_chai_pairs}")
            send_to_printer(payload)

        # 5) Print normal Kitchen token
        if other_pairs:
            payload = build_group_token_bytes(
                session,
                other_pairs,
                header_label="KITCHEN TOKEN"
            )
            print(f"Others: {other_pairs}")
            send_to_printer(payload)

        # 6) Mark printed_quantity
        for ti, _ in items_with_delta:
            ti.printed_quantity = ti.quantity
            ti.save(update_fields=['printed_quantity'])

        return JsonResponse({
            'status': 'printed',
            'count': len(items_with_delta)
        })


def build_group_token_bytes(session, items_with_delta, header_label):
    lines = []

    # ── Header ─────────────────────────────────────────────
    lines.append(ESC + b"\x61" + b"\x01")            # center
    lines.append(ESC + b"\x21" + b"\x20")            # double-width
    lines.append(header_label.encode("ascii") + b"\n")
    lines.append(ESC + b"\x21" + b"\x00")            # normal
    lines.append(b"\n")

    # ── Token # ────────────────────────────────────────────
    token_str = str(session.token_number).encode("ascii")
    lines.append(ESC + b"\x21" + b"\x30")            # double width
    lines.append(b"TOKEN #: " + token_str + b"\n\n")
    lines.append(ESC + b"\x21" + b"\x00")            # normal

    # ── Table # ────────────────────────────────────────────
    table_no = str(session.table.number).encode("ascii")
    lines.append(ESC + b"\x61" + b"\x01")
    lines.append(ESC + b"\x21" + b"\x30")
    lines.append(b"TABLE #: " + table_no + b"\n\n")
    lines.append(ESC + b"\x21" + b"\x00")

    # ── Date / Waiter ───────────────────────────────────────
    now = timezone.localtime(timezone.now())\
                   .strftime("%Y-%m-%d %I:%M:%S %p")\
                   .encode("ascii")
    lines.append(ESC + b"\x61" + b"\x00")
    lines.append(b"Date  : " + now + b"\n")
    if session.waiter:
        waiter = session.waiter.name.encode("ascii", "ignore")
        lines.append(b"Waiter: " + waiter + b"\n")
    lines.append(b"-" * 32 + b"\n")

    # ── Columns ─────────────────────────────────────────────
    lines.append(b"#  Item                 Qty\n")
    lines.append(b"-" * 32 + b"\n")

    # ── Items Section ───────────────────────────────────────
    for idx, (ti, delta) in enumerate(items_with_delta, start=1):
        Model = MenuItem if ti.source_type=='menu' else Deal
        name  = Model.objects.get(pk=ti.source_id).name[:18]
        idx_b = str(idx).rjust(2).encode()
        name_b= name.ljust(18).encode("ascii","ignore")
        qty_b = str(delta).rjust(3).encode()
        lines.append(idx_b + b"  " + name_b + b"  " + qty_b + b"\n")

    lines.append(b"\n\n\n\n\n")
    # ── Cut ───────────────────────────────────────────────────
    lines.append(b"\n" * 4)
    lines.append(GS + b"\x56" + b"\x00")              # full cut

    return b"".join(lines)



# core/views.py

import json
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import TableSession, Table

class TableSessionSwitchView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            old_id = data['from_table']
            new_id = data['to_table']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid payload'}, status=400)

        # 1) Fetch the existing session on the old table
        try:
            session = TableSession.objects.get(table_id=old_id)
        except TableSession.DoesNotExist:
            return JsonResponse({'error': 'No active session on your current table.'}, status=400)

        # 2) Ensure target table is truly available
        #    (if a session exists there, it must have no picked_items)
        existing = TableSession.objects.filter(table_id=new_id).first()
        if existing and existing.picked_items.exists():
            return JsonResponse({'error': 'That table is not available.'}, status=400)
        # delete any empty session
        if existing:
            existing.delete()

        # 3) Re-assign our session to the new table
        session.table_id = new_id
        session.save(update_fields=['table'])

        # 4) Update occupancy flags
        Table.objects.filter(pk=old_id).update(is_occupied=False)
        Table.objects.filter(pk=new_id).update(is_occupied=True)

        return JsonResponse({'status': 'ok', 'new_table': new_id})
