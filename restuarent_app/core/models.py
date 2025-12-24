from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models import Max
from django.utils import timezone
from django.db import IntegrityError, transaction
import logging

from django.db import models
from django.db.models import Max
from django.conf import settings
from django.utils import timezone
import datetime

logger = logging.getLogger(__name__)

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


class PrintStation(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="e.g. Main Kitchen, BBQ Section, Bar")
    printer_name = models.CharField(max_length=200, blank=True, null=True, help_text="Windows Printer Name (optional)")
    
    # Feature: Separate Token Slip
    print_separate_slip = models.BooleanField(default=True, help_text="If True, items for this station print on a separate paper slip.")
    
    # Feature: Separate Counting Sequence (1, 2, 3...)
    use_separate_sequence = models.BooleanField(default=False, help_text="If True, this station has its own Token #1, #2... independent of Main Kitchen.")

    def __str__(self):
        return self.name
    

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
    show_in_orders = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rank = models.IntegerField(null=True, blank=True)
    
    # Default station for items in this category
    default_station = models.ForeignKey(PrintStation, on_delete=models.SET_NULL, null=True, blank=True, related_name="categories")

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name
    

class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    food_panda_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rank = models.IntegerField(null=True, blank=True)

    # Allow overriding station per item
    station = models.ForeignKey(PrintStation, on_delete=models.SET_NULL, null=True, blank=True, related_name="menu_items")

    def __str__(self):
        return f"{self.name} – {self.category.name}"

    def get_effective_station(self):
        """Returns item specific station, or falls back to category station."""
        if self.station:
            return self.station
        if self.category.default_station:
            return self.category.default_station
        return None


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
    rank = models.IntegerField(null=True, blank=True)

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
    customer_name = models.CharField(max_length=50, null=True, blank=True)
    mobile_no = models.CharField(max_length=20, null=True, blank=True)
    customer_address = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Token number resets each day at 12:00 PM
    token_number = models.PositiveIntegerField(default=0, blank=True, null=True)

    source = models.CharField(max_length=20, choices=[('food_panda', 'Food Panda'), ('walk_in','Walk-in')], null=True, blank=True)

    def __str__(self):
        return f"Order #{self.number} – {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        import time, random
        from django.db import IntegrityError, transaction
        from django.utils import timezone
        
        # Import the new utilities for dynamic timing and tokens
        # Ensure core/utils.py exists with the code provided in the previous step
        from .utils import get_business_date, get_next_token_number

        logger.debug(f"Order save started for {self.number} at {timezone.now()}")

        # Pin created_at for stable window math (auto_now_add will set DB value; this keeps our logic stable)
        if not self.created_at:
            self.created_at = timezone.localtime(timezone.now())

        # Only auto-generate if missing
        if not self.number:
            # === CHANGED: Use dynamic business date from settings ===
            # This replaces the hardcoded "noon_today" logic to support any start time (e.g. 6AM)
            business_date = get_business_date(self.created_at)

            prefix = f"ORD{business_date:%Y%m%d}"

            # Retry to avoid race on unique(number)
            max_attempts = 25
            backoff = 0.01

            for attempt in range(1, max_attempts + 1):
                try:
                    with transaction.atomic():
                        # Find the last sequence for *this prefix*, ignoring created_at.
                        last_with_prefix = (
                            Order.objects
                            .select_for_update()  # effective on Postgres/MySQL; harmless on SQLite
                            .filter(number__startswith=prefix)
                            .order_by('-number')
                            .first()
                        )

                        if last_with_prefix and '-' in last_with_prefix.number:
                            try:
                                last_seq = int(last_with_prefix.number.rsplit('-', 1)[-1])
                            except ValueError:
                                last_seq = 0
                        else:
                            last_seq = 0

                        # Next order number
                        self.number = f"{prefix}-{last_seq + 1:04d}"

                        # ── TOKEN: only if one wasn't pre-supplied (tables pass session token) ──
                        if not self.token_number:
                            # === CHANGED: Use the centralized token utility ===
                            # This ensures it respects the dynamic day start time and global sequence
                            # station=None means it grabs the "Global/Main" token number
                            self.token_number = get_next_token_number(station=None)
                            
                        logger.debug(f"Attempt {attempt}: number={self.number}, token={self.token_number}")
                        super().save(*args, **kwargs)
                    break  # success
                except IntegrityError as e:
                    # If number collided, back off and try the next sequence
                    if 'core_order.number' in str(e):
                        time.sleep(random.uniform(backoff, backoff * 4))
                        # Exponential-ish backoff cap
                        backoff = min(backoff * 1.5, 0.2)
                        continue
                    raise
            else:
                # Extremely unlikely unless >25 concurrent collisions
                raise IntegrityError("Could not generate a unique Order.number after multiple attempts.")
        else:
            super().save(*args, **kwargs)

        logger.debug(f"Token number set to {self.token_number}")

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

        # loop each raw-material line on the recipe
        for ingr in recipe.raw_ingredients.select_related('raw_material', 'unit').all():
            # look up the conversion factor for this raw_material + unit
            try:
                conv_obj = RawMaterialUnitConversion.objects.get(
                    raw_material=ingr.raw_material,
                    unit=ingr.unit
                )
                conv = Decimal(conv_obj.to_base_factor)
            except RawMaterialUnitConversion.DoesNotExist:
                # fallback to 1:1 if no conversion is defined
                conv = Decimal('1')

            # total raw needed = (recipe-line qty × unit→base) × order quantity
            used_qty = Decimal(ingr.quantity) * conv * self.quantity

            InventoryTransaction.objects.create(
                raw_material     = ingr.raw_material,
                transaction_type = 'out',
                quantity         = used_qty,
                order_item       = self,
                notes            = f"Used in {self.menu_item.name} (Order #{self.order.number})"
            )

    def save(self, *args, **kwargs):
        # Save the OrderItem first
        super().save(*args, **kwargs)
        
        # Then update inventory usage
        self.update_inventory_usage()

    def __str__(self):
        if self.deal:
            return f"{self.quantity} x {self.deal.name} (Deal)"
        return f"{self.quantity} x {self.menu_item.name}"

# ---------- Payments & Billing ----------
class Payment(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('jazz cash', 'Jazz Cash'),
        ('easypaisa', 'Easypaisa'),
        ('bank', 'Bank'),
        ('card', 'Card'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    details = models.CharField(max_length=100, null=True, blank=True)
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
    theme_color = models.CharField(max_length=7, default='#ff5722')
    
    # Feature: Configurable Day Start Time
    start_of_day_time = models.TimeField(default=datetime.time(6, 0), help_text="The time a new business day starts (e.g., 06:00 AM or 12:00 PM). Token numbers reset at this time.")

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
        return f"{self.name} ({self.unit})"



from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# core/models.py  (add fields to your existing PurchaseOrder)
class PurchaseOrder(models.Model):
    supplier   = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_orders")
    created_at = models.DateTimeField(auto_now_add=True)

    # Existing:
    total_cost  = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # treat as Subtotal (sum of lines)
    status      = models.CharField(max_length=20, choices=[('pending','Pending'), ('received','Received')], default='received')

    # NEW (all optional with defaults)
    tax_percent       = models.DecimalField(max_digits=5, decimal_places=2, default=0)   # e.g. 5.00 (%)
    discount_percent  = models.DecimalField(max_digits=5, decimal_places=2, default=0)   # e.g. 10.00 (%)
    net_total         = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # computed subtotal + tax - discount

    def __str__(self):
        return f"PO #{self.id} - {self.supplier.name}"

    def recompute_totals(self):
        """
        Recalculate subtotal (total_cost) from items and recompute net_total
        using % tax and % discount. Keeps compatibility with existing code that
        reads/writes `total_cost`.
        """
        from decimal import Decimal, ROUND_HALF_UP
        subtotal = sum((it.total_cost() for it in self.items.all()), Decimal('0'))
        self.total_cost = subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        tax_amt = (self.total_cost * (self.tax_percent or 0) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        disc_amt = (self.total_cost * (self.discount_percent or 0) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        self.net_total = (self.total_cost + tax_amt - disc_amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_total_cost(self):  # keep your old API intact
        self.recompute_totals()
        self.save(update_fields=['total_cost', 'net_total'])


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
    def delete(self, *args, **kwargs):
        # create a 'return' to reverse previous 'in'
        InventoryTransaction.objects.create(
            raw_material=self.raw_material,
            transaction_type='return',
            quantity=self.quantity,
            purchase_order_item=None,
            notes=f"Reversal (delete) PO #{self.purchase_order.id}"
        )
        super().delete(*args, **kwargs)

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
    date = models.DateField(default=timezone.localdate, null=True, blank=True)
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



from django.db import models
from django.utils import timezone

class TableSession(models.Model):
    table = models.OneToOneField(
        'Table', on_delete=models.CASCADE, related_name='session'
    )
    waiter = models.ForeignKey(
        'Waiter', on_delete=models.PROTECT, related_name='table_sessions',
        null=True, blank=True
    )
    home_delivery = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    token_number = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Table {self.table.number} Session"

class TableMenuItem(models.Model):
    TABLE_SOURCE_CHOICES = [
        ('menu', 'MenuItem'),
        ('deal', 'Deal'),
    ]
    session = models.ForeignKey(
        TableSession, on_delete=models.CASCADE, related_name='picked_items', null=True, blank=True
    )
    source_type = models.CharField(max_length=10, choices=TABLE_SOURCE_CHOICES)
    source_id = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    printed_quantity = models.PositiveIntegerField(default=0, blank=True, null=True)

    created_at = models.DateTimeField(null=True, blank=True)   # when the row was first created
    updated_at = models.DateTimeField(null=True, blank=True)       # every change
    last_added_at = models.DateTimeField(null=True, blank=True)  # when qty was last increased

    def get_source_object(self):
        if self.source_type == 'menu':
            return MenuItem.objects.get(pk=self.source_id)
        return Deal.objects.get(pk=self.source_id)

    class Meta:
        unique_together = ('session', 'source_type', 'source_id')

    def __str__(self):
        label = 'Menu' if self.source_type=='menu' else 'Deal'
        return f"Table {self.session.table.number}: {self.quantity} x {label}({self.source_id})"
    

from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class BankAccount(models.Model):
    name           = models.CharField(max_length=100, help_text="e.g. HBL Current A/C")
    bank_name      = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    branch         = models.CharField(max_length=100, blank=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        label = self.bank_name or "Bank"
        return f"{label} — {self.name}"

    @property
    def current_balance(self):
        from django.db.models import Sum, F, Case, When, DecimalField
        # Sum IN minus OUT for this bank account; opening balance included
        from .models import CashFlow  # avoid circulars if you split files
        agg = (
            CashFlow.objects
            .filter(bank_account=self)
            .aggregate(
                net=Sum(
                    Case(
                        When(flow_type='in',  then=F('amount')),
                        When(flow_type='out', then=-F('amount')),
                        default=0,
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    )
                )
            )
        )['net'] or 0
        return self.opening_balance + agg


class CashFlow(models.Model):
    IN  = 'in'
    OUT = 'out'
    FLOW_TYPE = [(IN, 'Cash In'), (OUT, 'Cash Out')]

    date         = models.DateField(default=timezone.now)
    flow_type    = models.CharField(max_length=3, choices=FLOW_TYPE)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True)
    description  = models.CharField(max_length=255, blank=True)
    created_by   = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        side = "Bank" if self.bank_account else "Cash"
        return f"{self.date} — {self.get_flow_type_display()} {self.amount} ({side})"


class BankMovement(models.Model):
    """
    A single logical movement that can touch CASH and/or BANK,
    writing matching rows to CashFlow so reports stay consistent.
    """
    DEPOSIT   = 'deposit'    # cash → bank
    WITHDRAW  = 'withdraw'   # bank → cash
    TRANSFER  = 'transfer'   # bank A → bank B
    FEE       = 'fee'        # bank fee (out)
    INTEREST  = 'interest'   # bank interest (in)
    TYPES = [
        (DEPOSIT,  'Deposit (Cash → Bank)'),
        (WITHDRAW, 'Withdraw (Bank → Cash)'),
        (TRANSFER, 'Transfer (Bank → Bank)'),
        (FEE,      'Bank Fee (Out)'),
        (INTEREST, 'Interest (In)'),
    ]

    date        = models.DateField(default=timezone.now)
    movement_type = models.CharField(max_length=20, choices=TYPES)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    # actors
    from_bank   = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='outgoing_movements')
    to_bank     = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='incoming_movements')
    method      = models.CharField(max_length=30, blank=True, help_text="e.g. Cash, Cheque, Online")
    reference_no= models.CharField(max_length=100, blank=True, help_text="Cheque/Txn ref if any")
    notes       = models.CharField(max_length=255, blank=True)
    created_by  = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at  = models.DateTimeField(auto_now_add=True)

    # Link to the actual ledger rows so edits/deletes stay consistent
    cashflow_out = models.OneToOneField(CashFlow, null=True, blank=True, on_delete=models.SET_NULL, related_name='movement_out')
    cashflow_in  = models.OneToOneField(CashFlow, null=True, blank=True, on_delete=models.SET_NULL, related_name='movement_in')

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.get_movement_type_display()} — {self.amount} on {self.date}"

    def clean(self):
        # basic rule checks
        from django.core.exceptions import ValidationError
        if self.amount <= 0:
            raise ValidationError("Amount must be positive.")

        if self.movement_type == self.DEPOSIT:
            if not self.to_bank:
                raise ValidationError("Deposit requires a destination bank (to_bank).")
        elif self.movement_type == self.WITHDRAW:
            if not self.from_bank:
                raise ValidationError("Withdrawal requires a source bank (from_bank).")
        elif self.movement_type == self.TRANSFER:
            if not self.from_bank or not self.to_bank:
                raise ValidationError("Transfer requires both from_bank and to_bank.")
            if self.from_bank_id == self.to_bank_id:
                raise ValidationError("Cannot transfer to the same bank account.")
        elif self.movement_type in [self.FEE, self.INTEREST]:
            if not (self.from_bank or self.to_bank):
                raise ValidationError("Fee/Interest must reference a bank account.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Ensure the paired CashFlow entries exist/are updated atomically.
        """
        creating = self.pk is None
        super().save(*args, **kwargs)

        # (1) Figure out the two sides that must exist for this movement
        out_kwargs, in_kwargs = None, None

        if self.movement_type == self.DEPOSIT:
            # cash OUT, bank IN
            out_kwargs = dict(bank_account=None, flow_type=CashFlow.OUT,
                              description=f"Deposit to {self.to_bank}", amount=self.amount)
            in_kwargs  = dict(bank_account=self.to_bank, flow_type=CashFlow.IN,
                              description="Cash deposit", amount=self.amount)

        elif self.movement_type == self.WITHDRAW:
            # bank OUT, cash IN
            out_kwargs = dict(bank_account=self.from_bank, flow_type=CashFlow.OUT,
                              description="Cash withdrawal", amount=self.amount)
            in_kwargs  = dict(bank_account=None, flow_type=CashFlow.IN,
                              description=f"Withdraw from {self.from_bank}", amount=self.amount)

        elif self.movement_type == self.TRANSFER:
            # bank A OUT, bank B IN
            out_kwargs = dict(bank_account=self.from_bank, flow_type=CashFlow.OUT,
                              description=f"Transfer to {self.to_bank}", amount=self.amount)
            in_kwargs  = dict(bank_account=self.to_bank, flow_type=CashFlow.IN,
                              description=f"Transfer from {self.from_bank}", amount=self.amount)

        elif self.movement_type == self.FEE:
            # bank OUT only
            out_kwargs = dict(bank_account=self.from_bank or self.to_bank, flow_type=CashFlow.OUT,
                              description="Bank fee", amount=self.amount)

        elif self.movement_type == self.INTEREST:
            # bank IN only
            in_kwargs  = dict(bank_account=self.to_bank or self.from_bank, flow_type=CashFlow.IN,
                              description="Bank interest", amount=self.amount)

        # (2) Create / update linked CashFlow(s)
        if out_kwargs:
            if self.cashflow_out_id:
                cf = self.cashflow_out
                cf.date = self.date
                cf.amount = out_kwargs['amount']
                cf.flow_type = out_kwargs['flow_type']
                cf.bank_account = out_kwargs['bank_account']
                cf.description = out_kwargs['description']
                cf.save(update_fields=['date','amount','flow_type','bank_account','description'])
            else:
                self.cashflow_out = CashFlow.objects.create(
                    date=self.date,
                    created_by=self.created_by,
                    **out_kwargs
                )
        else:
            # if previously existed but now not needed, remove
            if self.cashflow_out_id:
                self.cashflow_out.delete()
                self.cashflow_out = None

        if in_kwargs:
            if self.cashflow_in_id:
                cf = self.cashflow_in
                cf.date = self.date
                cf.amount = in_kwargs['amount']
                cf.flow_type = in_kwargs['flow_type']
                cf.bank_account = in_kwargs['bank_account']
                cf.description = in_kwargs['description']
                cf.save(update_fields=['date','amount','flow_type','bank_account','description'])
            else:
                self.cashflow_in = CashFlow.objects.create(
                    date=self.date,
                    created_by=self.created_by,
                    **in_kwargs
                )
        else:
            if self.cashflow_in_id:
                self.cashflow_in.delete()
                self.cashflow_in = None

        if creating or 'force_update_links' in kwargs:
            super().save(update_fields=['cashflow_out','cashflow_in'])

from django.db import models
from django.conf import settings

class Role(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Staff(models.Model):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('manager', 'Manager'),
        ('cashier', 'Cashier'),
        ('waiter', 'Waiter'),
        ('chef', 'Chef'),
        ('security_guard', 'Security Guard'),
        ('it_manager', 'IT Manager'),
        ('helper', 'Helper'),
        ('other', 'Other'),
    ]
    full_name = models.CharField(max_length=100)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    cnic = models.CharField(max_length=25, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    has_software_access = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    access_sales = models.BooleanField(default=False)
    access_inventory = models.BooleanField(default=False)
    access_accounts = models.BooleanField(default=False)

    joined_on = models.DateField(null=True, blank=True, help_text="Staff registry date")
    salary_start = models.DateField(null=True, blank=True, help_text="Salary starts from this date (month-wise)")
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.full_name
    
# core/models.py (add/replace these bits)

from django.conf import settings
from django.db import models
from django.utils import timezone

class ExpenseCategory(models.TextChoices):
    SALARY      = 'salary',      'Salary'
    ELECTRICITY = 'electricity', 'Electricity'
    GAS         = 'gas',         'Gas'
    STATIONERY  = 'stationery',  'Stationery'
    MAINTENANCE = 'maintenance', 'Maintenance'
    SOFTWARE    = 'software',    'Software'
    PURCHASE    = 'purchase',    'Purchases/Other Items'
    OTHER       = 'other',       'Other'

class Expense(models.Model):
    PAYMENT_SOURCE = [
        ('cash', 'Cash (Restaurant Cash)'),
        ('bank', 'Bank Account'),
    ]

    date            = models.DateField(default=timezone.now)
    category        = models.CharField(max_length=20, choices=ExpenseCategory.choices)
    amount          = models.DecimalField(max_digits=12, decimal_places=2)
    description     = models.CharField(max_length=255, blank=True)
    reference       = models.CharField(max_length=100, blank=True)  # invoice/bill no (optional)
    attachment      = models.FileField(upload_to='expenses/', null=True, blank=True)

    # Links (nullable; validated by category rules)
    supplier        = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True)
    staff           = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True)

    # Payment source
    payment_source  = models.CharField(max_length=10, choices=PAYMENT_SOURCE, default='cash')
    bank_account    = models.ForeignKey('BankAccount', on_delete=models.SET_NULL, null=True, blank=True)

    # Audit
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at      = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at      = models.DateTimeField(auto_now=True)

    # Link to CashFlow so edits/deletes stay in sync
    cashflow        = models.OneToOneField('CashFlow', on_delete=models.SET_NULL, null=True, blank=True, related_name='linked_expense')

    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')

    def __str__(self):
        return f"{self.date} — {self.get_category_display()} — ₨{self.amount}"

    # --- Validation rules ---
    def clean(self):
        from django.core.exceptions import ValidationError
        # Supplier mandatory for utility bills & purchases
        supplier_required_for = {
            ExpenseCategory.ELECTRICITY,
            ExpenseCategory.GAS,
            ExpenseCategory.PURCHASE,
            ExpenseCategory.STATIONERY,
            ExpenseCategory.MAINTENANCE,
            ExpenseCategory.SOFTWARE,
        }
        if self.category in supplier_required_for and not self.supplier:
            raise ValidationError("Supplier is required for this expense category.")
        # Staff mandatory for Salary
        if self.category == ExpenseCategory.SALARY and not self.staff:
            raise ValidationError("Staff is required for Salary expenses.")
        # Bank account mandatory if payment source is bank
        if self.payment_source == 'bank' and not self.bank_account:
            raise ValidationError("Please choose a Bank Account for bank payments.")
        # Ensure no bank account set for cash payments
        if self.payment_source == 'cash':
            self.bank_account = None

    # --- CashFlow sync ---
    def save(self, *args, **kwargs):
        from .models import CashFlow  # already in your project
        creating = self.pk is None
        super().save(*args, **kwargs)

        # Create/update the CashFlow record
        desc = f"Expense: {self.get_category_display()}"
        if self.description:
            desc += f" — {self.description}"

        if not self.cashflow:
            cf = CashFlow.objects.create(
                date=self.date,
                flow_type=CashFlow.OUT,
                amount=self.amount,
                bank_account=self.bank_account if self.payment_source == 'bank' else None,
                description=desc,
                created_by=self.created_by,
            )
            self.cashflow = cf
            super().save(update_fields=['cashflow'])
        else:
            cf = self.cashflow
            cf.date = self.date
            cf.amount = self.amount
            cf.bank_account = self.bank_account if self.payment_source == 'bank' else None
            cf.description = desc
            cf.save()

    def delete(self, *args, **kwargs):
        cf = self.cashflow
        super().delete(*args, **kwargs)
        if cf:
            cf.delete()


# --- KITCHEN ISSUE / RETURN -----------------------------------------------
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class KitchenVoucher(models.Model):
    ISSUE  = 'issue'
    RETURN = 'return'
    TYPES = [(ISSUE, 'Issue to Kitchen'), (RETURN, 'Return from Kitchen')]

    date        = models.DateField(default=timezone.localdate)
    vtype       = models.CharField(max_length=10, choices=TYPES, default=ISSUE)
    handler     = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True,
                                    help_text="Kitchen/Store in-charge")
    notes       = models.CharField(max_length=255, blank=True)

    created_by  = models.ForeignKey(User, on_delete=models.PROTECT, related_name='kitchen_vouchers')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['vtype','date'])]

    def __str__(self):
        return f"KV#{self.id} — {self.get_vtype_display()} — {self.date}"

    @transaction.atomic
    def sync_transactions(self):
        """
        For each item ensure a matching InventoryTransaction exists/updated.
        ISSUE  -> OUT
        RETURN -> IN
        """
        from .models import InventoryTransaction  # avoid cycle

        for it in self.items.select_related('raw_material').all():
            # create/update the attached InventoryTransaction
            if it.transaction_id:
                t = it.transaction
                t.date = self.date  # we add a date field below in InventoryTransaction
                t.timestamp = timezone.now()
                t.transaction_type = 'out' if self.vtype == self.ISSUE else 'in'
                t.quantity = it.quantity
                t.raw_material = it.raw_material
                t.notes = f"{self.get_vtype_display()} KV#{self.id}"
                t.save(update_fields=['date','timestamp','transaction_type','quantity','raw_material','notes'])
            else:
                t = InventoryTransaction.objects.create(
                    raw_material=it.raw_material,
                    transaction_type=('out' if self.vtype == self.ISSUE else 'in'),
                    quantity=it.quantity,
                    notes=f"{self.get_vtype_display()} KV#{self.id}",
                )
                it.transaction = t
                it.save(update_fields=['transaction'])

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        # on create/update, (re)sync transactions
        self.sync_transactions()


class KitchenVoucherItem(models.Model):
    voucher      = models.ForeignKey(KitchenVoucher, on_delete=models.CASCADE, related_name='items')
    raw_material = models.ForeignKey('RawMaterial', on_delete=models.PROTECT)
    quantity     = models.DecimalField(max_digits=10, decimal_places=2)

    # Backlink so edits/deletes stay consistent in InventoryTransaction
    transaction  = models.OneToOneField('InventoryTransaction', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='kitchen_item')

    class Meta:
        unique_together = ('voucher','raw_material')  # avoid accidental duplicates

    def __str__(self):
        return f"{self.quantity} {self.raw_material.unit} of {self.raw_material.name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError("Quantity must be > 0")

    def delete(self, *args, **kwargs):
        # remove paired transaction as well
        t = self.transaction
        super().delete(*args, **kwargs)
        if t:
            t.delete()


# models.py
from django.db import models, transaction
from django.utils import timezone

class TokenSequence(models.Model):
    """
    Tracks the last token number for a specific business date.
    Optionally tracks per PrintStation if they need separate sequencing.
    """
    business_date = models.DateField(db_index=True)
    station = models.ForeignKey(PrintStation, on_delete=models.CASCADE, null=True, blank=True, help_text="Null means Global/Main sequence")
    last = models.PositiveIntegerField(default=0)

    class Meta:
        # Unique constraint: One counter per date per station (or one global counter per date)
        unique_together = ('business_date', 'station')

    def __str__(self):
        st_name = self.station.name if self.station else "Global"
        return f"{self.business_date} [{st_name}] -> {self.last}"

def business_date_for(dt):
    ref = timezone.localtime(dt)
    noon = ref.replace(hour=12, minute=0, second=0, microsecond=0)
    return ref.date() if ref >= noon else (ref - timezone.timedelta(days=1)).date()

def next_token_for(dt=None):
    """Atomically returns next token for the business day."""
    ref = dt or timezone.now()
    bday = business_date_for(ref)
    with transaction.atomic():
        row, _ = TokenSequence.objects.select_for_update().get_or_create(
            business_date=bday,
            defaults={'last': 0},
        )
        row.last += 1
        row.save(update_fields=['last'])
        return row.last


class TokenCounter(models.Model):
    service_day = models.DateField(unique=True, db_index=True)
    last        = models.PositiveIntegerField(default=0)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-service_day"]

    def __str__(self):
        return f"{self.service_day}: {self.last}"