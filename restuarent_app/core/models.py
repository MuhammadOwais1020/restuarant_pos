from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# ---------- User & Roles (unchanged) ----------
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('cashier', 'Cashier'),
        ('kitchen', 'Kitchen'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Unit(models.Model):
    UNIT_TYPES = [
        ('mass', 'Mass'),
        ('volume', 'Volume'),
        ('count', 'Count'),
    ]
    name   = models.CharField(max_length=50, unique=True, help_text="e.g. Gram, Teaspoon, Piece")
    symbol = models.CharField(max_length=10, unique=True, help_text="e.g. g, tsp, pc")
    unit_type = models.CharField(max_length=10, choices=UNIT_TYPES)

    def __str__(self):
        return self.symbol


class RawMaterialUnitConversion(models.Model):
    raw_material = models.ForeignKey('RawMaterial', on_delete=models.CASCADE, related_name='conversions')
    unit         = models.ForeignKey(Unit, on_delete=models.PROTECT)
    to_base_factor = models.DecimalField(
        max_digits=12, decimal_places=6,
        help_text="Multiply this unit amount by factor to get grams (for mass) or ml (for volume)"
    )

    class Meta:
        unique_together = ('raw_material', 'unit')

    def __str__(self):
        return f"1 {self.unit.symbol} = {self.to_base_factor} base"


class Waiter(models.Model):
    name = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.employee_id})"
    
# ---------- Categories & Menu ----------
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_price    = models.DecimalField(
                       max_digits=10,
                       decimal_places=2,
                       default=0,
                       help_text="Auto‑calculated from recipe"
    )
    food_panda_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} – {self.category.name}"


# ---------- Deals (New) ----------
class Deal(models.Model):
    """
    A Deal bundles multiple MenuItems (with quantities).
    The price is set at creation time and overrides individual item sum.
    """
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2,
                                help_text="Total price for this deal")
    cost_price  = models.DecimalField(
                      max_digits=10,
                      decimal_places=2,
                      default=0,
                      help_text="Sum of ingredients' cost"
                  )
    food_panda_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='deals/', blank=True, null=True)
    items = models.ManyToManyField(
        MenuItem,
        through='DealItem',
        related_name='deals'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (Deal)"


class DealItem(models.Model):
    """
    The intermediate table linking a Deal to its MenuItems (with quantity).
    """
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='deal_items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} in {self.deal.name}"


# ---------- Tables & Orders ----------
class Table(models.Model):
    number = models.PositiveIntegerField(unique=True)
    seats = models.PositiveIntegerField(default=4)
    is_occupied = models.BooleanField(default=False)

    def __str__(self):
        return f"Table {self.number} ({self.seats} seats)"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),       
        ('in_kitchen', 'In Kitchen'),
        ('served', 'Served'),
        ('paid', 'Paid'),
        ('food_panda', 'Food Panda'),  
    ]
    waiter = models.ForeignKey(
        Waiter,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True, blank=True,
        help_text="Who took this order"
    )
    isHomeDelivery = models.CharField(max_length=10, null=True, blank=True, default="no")
    # Order number is autogenerated on save
    number = models.CharField(max_length=20, unique=True, blank=True)
    table = models.ForeignKey(Table, on_delete=models.PROTECT,
                              related_name='orders', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                   related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Token number resets each day at 12:00 PM
    token_number = models.PositiveIntegerField(default=0, blank=True, null=True)

    source = models.CharField(max_length=20, choices=[('food_panda', 'Food Panda'), ('walk_in','Walk‑in')], null=True, blank=True)

    def __str__(self):
        return f"Order #{self.number} – {self.get_status_display()}"

    def save(self, *args, **kwargs):
        # Auto-generate order.number if blank (e.g., ORD20250531-0001)
        if not self.number:
            today = timezone.localdate()
            prefix = today.strftime("ORD%Y%m%d")
            existing_today = Order.objects.filter(number__startswith=prefix).count() + 1
            self.number = f"{prefix}-{existing_today:04d}"

            # Determine token number: resets at 12:00 PM
            now = timezone.localtime()
            if now.hour < 12:
                # Count yesterday’s tokens
                yesterday = today - timezone.timedelta(days=1)
                last_token = Order.objects.filter(
                    created_at__date=yesterday,
                    token_number__isnull=False
                ).order_by('-token_number').first()
                self.token_number = (last_token.token_number if last_token else 0) + 1
            else:
                # Count today’s tokens
                last_token = Order.objects.filter(
                    created_at__date=today,
                    token_number__isnull=False
                ).order_by('-token_number').first()
                self.token_number = (last_token.token_number if last_token else 0) + 1

        super().save(*args, **kwargs)

from decimal import Decimal

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, null=True, blank=True)
    deal = models.ForeignKey(Deal, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    token_printed = models.BooleanField(default=False)
    printed_quantity = models.PositiveIntegerField(default=0)

    def line_total(self):
        return self.quantity * self.unit_price

    def update_inventory_usage(self):
        # only do this for a menu_item that actually has a recipe
        if not self.menu_item:
            return

        try:
            recipe = self.menu_item.recipe
        except Recipe.DoesNotExist:
            return

        # loop each raw‐material line on the recipe
        for ingr in recipe.raw_ingredients.all():
            # ingr.quantity is in ingr.unit (e.g. 'g', 'kg', 'tbsp', etc.)
            conv = ingr.unit.to_base_factor     # e.g. 250g → 250; 1kg→1000
            # total raw needed = (recipe‐line qty * unit→base) × order quantity
            used_qty = (Decimal(ingr.quantity) * Decimal(conv)) * self.quantity

            InventoryTransaction.objects.create(
                raw_material        = ingr.raw_material,
                transaction_type    = 'out',
                quantity            = used_qty,
                order_item          = self,
                notes               = (
                    f"Used in {self.menu_item.name} "
                    f"(Order #{self.order.number})"
                )
            )

    def save(self, *args, **kwargs):
        self.update_inventory_usage()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.deal:
            return f"{self.quantity} x {self.deal.name} (Deal)"
        return f"{self.quantity} x {self.menu_item.name}"


# ---------- Payments & Billing ----------
class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for Order #{self.order.number} – {self.get_method_display()}"


# ---------- Settings & Configuration (unchanged) ----------
class TaxRate(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 7.50 for 7.5%")
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class DiscountRule(models.Model):
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2,
                                 help_text="Fixed amount or % based on is_percentage")
    is_percentage = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    def __str__(self):
        disc = f"{self.amount}%" if self.is_percentage else f"{self.amount}"
        return f"{self.name} ({disc})"


class POSSettings(models.Model):
    restaurant_name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='settings/', blank=True, null=True)
    theme_color = models.CharField(max_length=7, default='#ff5722',
                                   help_text="Hex color code (e.g. #ff5722)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.restaurant_name


class PrintStatus(models.Model):
    token = models.BooleanField(default=False)
    bill  = models.BooleanField(default=False)

    def __str__(self):
        return f"PrintStatus(token={self.token}, bill={self.bill})"


class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class RawMaterial(models.Model):
    name = models.CharField(max_length=100, unique=True)
    unit = models.CharField(max_length=50, help_text="E.g. kg, liter, pc")
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="materials")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class PurchaseOrder(models.Model):
    supplier   = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_orders"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    total_cost  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status      = models.CharField(max_length=20,
                                   choices=[('pending','Pending'),
                                            ('received','Received')],
                                   default='received')

    def __str__(self):
        return f"PO #{self.id} - {self.supplier.name}"

    def calculate_total_cost(self):
        self.total_cost = sum(item.total_cost() for item in self.items.all())
        self.save()

    def mark_received(self):
        self.status = 'received'
        self.save()

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE,
                                       related_name='items')
    raw_material   = models.ForeignKey(RawMaterial, on_delete=models.PROTECT)
    quantity       = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price     = models.DecimalField(max_digits=10, decimal_places=2)

    def total_cost(self):
        return self.quantity * self.unit_price

    def save(self, *args, **kwargs):
            super().save(*args, **kwargs)
            # auto add stock‑in transaction WITH a back‑link
            InventoryTransaction.objects.create(
                raw_material       = self.raw_material,
                transaction_type   = 'in',
                quantity           = self.quantity,
                purchase_order_item= self,              # ← link back
                notes              = f"PO #{self.purchase_order.id}"
            )

    def __str__(self):
        return f"{self.quantity} x {self.raw_material.name}"
    

class Recipe(models.Model):
    menu_item  = models.OneToOneField(MenuItem, on_delete=models.CASCADE,
                                      related_name='recipe')
    name       = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Recipe for {self.menu_item.name}"

    def total_grams(self):
        """
        Sum all ingredients & sub-recipes (in grams) for cost & usage.
        """
        total = 0
        for ingr in self.raw_ingredients.all():
            conv = ingr.unit.to_base_factor
            total += ingr.quantity * conv
        for sub in self.subrecipes.all():
            total += sub.sub_recipe.total_grams() * float(sub.quantity)
        return total

class RecipeRawMaterial(models.Model):
    recipe       = models.ForeignKey(Recipe, on_delete=models.CASCADE,
                                     related_name='raw_ingredients')
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT)
    quantity     = models.DecimalField(max_digits=10, decimal_places=3,
                                       help_text="Use decimals for fractions, e.g. 0.25")
    unit         = models.ForeignKey(Unit, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.quantity} {self.unit.symbol} of {self.raw_material.name}"

class RecipeSubRecipe(models.Model):
    recipe     = models.ForeignKey(Recipe, on_delete=models.CASCADE,
                                   related_name='subrecipes')
    sub_recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT)
    quantity   = models.DecimalField(max_digits=10, decimal_places=3)
    unit       = models.ForeignKey(Unit, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.quantity} {self.unit.symbol} of {self.sub_recipe.menu_item.name}"

class InventoryTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('in', 'Stock In'),
        ('out','Stock Out'),
        ('return','Stock Return'),
    ]
    raw_material        = models.ForeignKey(RawMaterial, on_delete=models.CASCADE,
                                            related_name='transactions', null=True, blank=True)
    transaction_type    = models.CharField(max_length=6, choices=TRANSACTION_TYPES)
    quantity            = models.DecimalField(max_digits=10, decimal_places=2)
    timestamp           = models.DateTimeField(auto_now_add=True)
    notes               = models.TextField(blank=True)
    # optional back‐links
    purchase_order_item = models.ForeignKey(PurchaseOrderItem,
                                            on_delete=models.SET_NULL,
                                            null=True, blank=True)
    order_item          = models.ForeignKey(OrderItem,
                                            on_delete=models.SET_NULL,
                                            null=True, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # maintain current stock
        if self.transaction_type == 'in':
            self.raw_material.current_stock += self.quantity
        elif self.transaction_type in ['out']:
            self.raw_material.current_stock -= self.quantity
        elif self.transaction_type == 'return':
            self.raw_material.current_stock += self.quantity
        self.raw_material.save()

    def __str__(self):
        return f"{self.get_transaction_type_display()} – {self.raw_material.name}: {self.quantity} {self.raw_material.unit}"


from django.db.models.signals import post_save
from django.dispatch import receiver

# a dictionary of all the units you support, with their
# “to base” factor (base = grams for mass, milliliters for volume).
#    e.g.  1 kg → 1000 g,   1 g → 1 g
#          1 l  → 1000 ml,  1 ml→1 ml
#          1 tbsp→15 ml,    1 tsp→5 ml,  1 cup→240 ml
DEFAULT_FACTORS = {
  'kg': 1000, 'g': 1,
  'l': 1000, 'ml': 1,
  'tbsp': 15, 'tsp': 5, 'cup': 240,
  # add more if you like: 'oz': 29.5735, etc.
}

@receiver(post_save, sender=RawMaterial)
def seed_unit_conversions(sender, instance, created, **kwargs):
    from .models import Unit, RawMaterialUnitConversion
    # ensure we have Unit objects
    units = {u.symbol: u for u in Unit.objects.filter(symbol__in=DEFAULT_FACTORS)}
    for symb, factor in DEFAULT_FACTORS.items():
        unit = units.get(symb)
        if not unit:
            continue
        RawMaterialUnitConversion.objects.get_or_create(
            raw_material=instance,
            unit=unit,
            defaults={'to_base_factor': factor}
        )

