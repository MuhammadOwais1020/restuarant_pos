from django.urls import path
from django.views.generic import RedirectView
from django.contrib import admin

from .views import LoginView, LogoutView, DashboardView, update_print_status, reports_view, sales_report
from .views import TableListView, TableCreateView, TableUpdateView, TableSwitchView

from .views import (
    CategoryListView, CategoryCreateView, CategoryDetailView,
    CategoryUpdateView, CategoryDeleteView,
    MenuItemListView, MenuItemCreateView, MenuItemDetailView,
    MenuItemUpdateView, MenuItemDeleteView,
    OrderListView, OrderDetailView, OrderCreateView, OrderUpdateView, OrderDeleteView,
    DealListView, DealCreateView, DealDetailView, DealUpdateView, DealDeleteView
)

from .escpos_test import(
        simple_win32print_test
)

from .views import (
    SupplierListView, SupplierCreateView,
    SupplierDetailView, SupplierUpdateView, SupplierDeleteView, close_order
)


urlpatterns = [
    
        
    path('orders/close_order/', close_order, name='close_order'),   
    path(
        "",
        RedirectView.as_view(pattern_name="login", permanent=False),
        name="home",
    ),
    path("admin/", admin.site.urls),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # Categories CRUD
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('categories/create/', CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/', CategoryDetailView.as_view(), name='category_detail'),
    path('categories/<int:pk>/edit/', CategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', CategoryDeleteView.as_view(), name='category_delete'),

    # Menu Items CRUD
    path('menu-items/', MenuItemListView.as_view(), name='menuitem_list'),
    path('menu-items/create/', MenuItemCreateView.as_view(), name='menuitem_create'),
    path('menu-items/<int:pk>/', MenuItemDetailView.as_view(), name='menuitem_detail'),
    path('menu-items/<int:pk>/edit/', MenuItemUpdateView.as_view(), name='menuitem_edit'),
    path('menu-items/<int:pk>/delete/', MenuItemDeleteView.as_view(), name='menuitem_delete'),

    # ======== Deals CRUD ========
    path('deals/', DealListView.as_view(), name='deal_list'),
    path('deals/create/', DealCreateView.as_view(), name='deal_create'),
    path('deals/<int:pk>/', DealDetailView.as_view(), name='deal_detail'),
    path('deals/<int:pk>/edit/', DealUpdateView.as_view(), name='deal_edit'),
    path('deals/<int:pk>/delete/', DealDeleteView.as_view(), name='deal_delete'),

    # ======== Orders & Printing ========
    path('orders/', OrderListView.as_view(), name='order_list'),
    path('orders/create/', OrderCreateView.as_view(), name='order_create'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/edit/', OrderUpdateView.as_view(), name='order_edit'),
    path('orders/<int:pk>/delete/', OrderDeleteView.as_view(), name='order_delete'),
    path('orders/<int:pk>/update/', OrderUpdateView.as_view(), name='order_update'),  # ← Here
    path('print/', simple_win32print_test, name="simple_windows_test_print"),

    path(
        "printstatus/update/",
        update_print_status,
        name="update_print_status"
    ),

    path('reports/', reports_view, name='reports'),

    path('api/sales-report/', sales_report, name='sales-report'),

    path('tables/',          TableListView.as_view(),   name='table_list'),
    path('tables/create/',   TableCreateView.as_view(), name='table_create'),
    path('tables/<int:pk>/edit/', TableUpdateView.as_view(), name='table_edit'),
    
    path(
      'orders/table-switch/',
      TableSwitchView.as_view(),
      name='table_switch'
    ),
    
]

urlpatterns += [
    # Suppliers CRUD
    path('suppliers/', SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/create/', SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/', SupplierDetailView.as_view(), name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', SupplierDeleteView.as_view(), name='supplier_delete'),
]


from .views import (
    # … other imports …
    RawMaterialListView, RawMaterialCreateView,
    RawMaterialDetailView, RawMaterialUpdateView, RawMaterialDeleteView,
)

urlpatterns += [
    # Raw Materials CRUD
    path('raw-materials/', RawMaterialListView.as_view(), name='raw_material_list'),
    path('raw-materials/create/', RawMaterialCreateView.as_view(), name='raw_material_create'),
    path('raw-materials/<int:pk>/', RawMaterialDetailView.as_view(), name='raw_material_detail'),
    path('raw-materials/<int:pk>/edit/', RawMaterialUpdateView.as_view(), name='raw_material_edit'),
    path('raw-materials/<int:pk>/delete/', RawMaterialDeleteView.as_view(), name='raw_material_delete'),
]


from .views import (
    # … other imports …
    PurchaseOrderListView,
    PurchaseOrderCreateView,
    PurchaseOrderDetailView,
    PurchaseOrderUpdateView,
    PurchaseOrderDeleteView,
    purchase_order_receive,
)

urlpatterns += [
    # Purchase Orders CRUD
    path('purchase-orders/', PurchaseOrderListView.as_view(), name='purchase_order_list'),
    path('purchase-orders/create/', PurchaseOrderCreateView.as_view(), name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', PurchaseOrderDetailView.as_view(), name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/edit/', PurchaseOrderUpdateView.as_view(), name='purchase_order_edit'),
    path('purchase-orders/<int:pk>/delete/', PurchaseOrderDeleteView.as_view(), name='purchase_order_delete'),
    # mark received
    path('purchase-orders/<int:pk>/receive/', purchase_order_receive, name='purchase_order_receive'),
]

from .views import CostReportView

urlpatterns += [
    # …
    path('cost-report/', CostReportView.as_view(), name='cost_report'),
]

from .views import (
    RecipeListView,
    RecipeCreateView, RecipeDetailView,
    RecipeUpdateView, RecipeDeleteView,
)

urlpatterns += [
    # Recipes CRUD
    path('recipes/',         RecipeListView.as_view(),   name='recipe_list'),
    path('recipes/create/',  RecipeCreateView.as_view(), name='recipe_create'),
    path('recipes/<int:pk>/',RecipeDetailView.as_view(), name='recipe_detail'),
    path('recipes/<int:pk>/edit/',  RecipeUpdateView.as_view(), name='recipe_edit'),
    path('recipes/<int:pk>/delete/',RecipeDeleteView.as_view(), name='recipe_delete'),
]


from django.urls import path
from .views import (
    WaiterListView, WaiterCreateView, WaiterDetailView,
    WaiterUpdateView, WaiterDeleteView, debug_costs
    # … your other imports …
)

urlpatterns += [
    # … your existing patterns …

    # Waiters
    path('waiters/', WaiterListView.as_view(),     name='waiter_list'),
    path('waiters/create/', WaiterCreateView.as_view(), name='waiter_create'),
    path('waiters/<int:pk>/', WaiterDetailView.as_view(), name='waiter_detail'),
    path('waiters/<int:pk>/edit/',  WaiterUpdateView.as_view(), name='waiter_edit'),
    path('waiters/<int:pk>/delete/',WaiterDeleteView.as_view(), name='waiter_delete'),

    path('debug-cost/', debug_costs, name='debug_costs'),
]


from .views import (
    TableSessionView, TableItemsView,
    ClearTableItemsView, TablePrintTokenView, OrderReprintView,TableSessionSwitchView
)
urlpatterns += [
    path('tables/<int:table_id>/session/', TableSessionView.as_view(), name='table_session'),
    path('tables/<int:table_id>/items/', TableItemsView.as_view(), name='table_items'),
    path('tables/<int:table_id>/items/clear/', ClearTableItemsView.as_view(), name='clear_table_items'),
    path('tables/<int:table_id>/print-token/', TablePrintTokenView.as_view(), name='print_token'),
    path('orders/<int:pk>/reprint/', OrderReprintView.as_view(), name='order_reprint'),
    path('tables/switch/', TableSessionSwitchView.as_view(), name='table_session_switch'),
]