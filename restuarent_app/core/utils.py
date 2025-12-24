# core/utils.py
from decimal import Decimal, getcontext
from .models import RawMaterialUnitConversion, PurchaseOrderItem

# bump precision to avoid rounding errors
getcontext().prec = 28

def recipe_cost_and_weight(recipe):
    """
    Returns a tuple:
      ( total_cost_for_this_recipe_definition,
        total_base_qty_produced_by_this_recipe  )
    where base_qty is in the recipe's base unit (e.g. grams or ml).
    """
    # preload conversion factors: (raw_material_id, unit_symbol) → to_base_factor
    convs = {
        (c.raw_material_id, c.unit.symbol): Decimal(c.to_base_factor)
        for c in RawMaterialUnitConversion.objects.select_related('unit').all()
    }

    # helper: avg cost **per base unit** for a raw material
    _cache = {}
    def avg_cost_per_base(rm):
        if rm.id in _cache:
            return _cache[rm.id]
        pois = PurchaseOrderItem.objects.filter(raw_material=rm)
        total_cost = Decimal('0')
        total_base = Decimal('0')
        for poi in pois:
            q = Decimal(poi.quantity)
            p = Decimal(poi.unit_price)
            factor = convs.get((rm.id, rm.unit), Decimal('1'))
            total_base += q * factor
            total_cost += q * p
        avg = (total_cost / total_base) if total_base else Decimal('0')
        _cache[rm.id] = avg
        return avg

    # 1) sum raw-material lines
    total_cost = Decimal('0')
    total_base = Decimal('0')
    for ri in recipe.raw_ingredients.select_related('raw_material','unit'):
        rm     = ri.raw_material
        qty    = Decimal(ri.quantity)         # e.g. 150
        symbol = ri.unit.symbol               # e.g. 'g'
        factor = convs.get((rm.id, symbol), Decimal('1'))
        base   = qty * factor                 # e.g. 150g→150
        total_base += base
        total_cost += base * avg_cost_per_base(rm)

    # 2) recurse into sub-recipes as **weight** portions
    for sub in recipe.subrecipes.select_related('sub_recipe'):
        sub_recipe = sub.sub_recipe
        sub_cost, sub_base = recipe_cost_and_weight(sub_recipe)
        # cost per base-unit (e.g. per gram) of the FULL sub-recipe
        cpb = (sub_cost / sub_base) if sub_base else Decimal('0')
        req = Decimal(sub.quantity)  # NOW interpreted as grams
        total_base += req
        total_cost += cpb * req

    return total_cost.quantize(Decimal('0.01')), total_base

def compute_recipe_cost(recipe):
    """Back-compat: returns just the cost for the full recipe definition."""
    cost, _ = recipe_cost_and_weight(recipe)
    return cost


# core/utils.py
from django.utils import timezone
from django.db.models import Max
from .models import Order, TableSession

def _business_window(ref=None):
    ref = timezone.localtime(ref or timezone.now())
    noon = ref.replace(hour=12, minute=0, second=0, microsecond=0)
    if ref >= noon:
        start = noon
        end   = noon + timezone.timedelta(days=1)
    else:
        start = noon - timezone.timedelta(days=1)
        end   = noon
    return start, end


# core/utils.py
from datetime import time, timedelta, datetime
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from .models import TokenCounter
from .models import Order        # adjust import path
from .models import TableSession # adjust import path

def _service_day(ref=None):
    """
    Returns the 'day' for your business window (12:00 → 11:59 next day).
    Stored as a date (the date of the 12:00 start).
    """
    now = timezone.localtime(ref or timezone.now())
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if now >= noon:
        return now.date()            # starts today at 12:00
    else:
        return (now - timedelta(days=1)).date()  # started yesterday 12:00

def _window_bounds(day):
    """
    Convert a service_day (date) into [start, end) datetimes in local tz.
    """
    start_naive = datetime.combine(day, time(12, 0))
    start = timezone.make_aware(start_naive, timezone.get_current_timezone())
    return start, start + timedelta(days=1)

def _bootstrap_from_history(day) -> int:
    """
    When a counter row is created for a past/current day, initialise it from
    existing records (safe for restarts, imports, etc.). Uses CREATED time.
    """
    start, end = _window_bounds(day)
    m1 = (Order.objects
          .filter(created_at__gte=start, created_at__lt=end, token_number__isnull=False)
          .aggregate(m=Max("token_number"))["m"] or 0)
    m2 = (TableSession.objects
          .filter(created_at__gte=start, created_at__lt=end, token_number__isnull=False)
          .aggregate(m=Max("token_number"))["m"] or 0)
    return max(m1, m2)


from django.utils import timezone
from django.db import transaction
import datetime

def get_business_date(dt=None):
    """
    Calculates the 'Business Date' based on POSSettings.start_of_day_time.
    If current time < start_time, it belongs to the previous calendar day.
    """
    from .models import POSSettings  # delayed import to avoid circular dep
    
    ref = dt or timezone.localtime(timezone.now())
    
    # Get setting or default to 06:00 AM
    try:
        settings_obj = POSSettings.objects.first()
        start_time = settings_obj.start_of_day_time if settings_obj else datetime.time(6, 0)
    except:
        start_time = datetime.time(6, 0)

    # Create a timestamp for Today at Start Time
    today_start = ref.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)

    if ref >= today_start:
        return ref.date()
    else:
        return (ref - datetime.timedelta(days=1)).date()
    

def get_next_token_number(station=None):
    """
    Atomically generates the next token number.
    If 'station' is provided and has 'use_separate_sequence=True', generates from that station's counter.
    Otherwise, generates from the Global (None) counter.
    """
    from .models import TokenSequence, PrintStation

    # Determine if we need a specific sequence or the global one
    target_station = None
    if station and station.use_separate_sequence:
        target_station = station

    b_date = get_business_date()

    with transaction.atomic():
        # Lock the row for this date + station
        row, created = TokenSequence.objects.select_for_update().get_or_create(
            business_date=b_date,
            station=target_station,
            defaults={'last': 0}
        )
        row.last += 1
        row.save(update_fields=['last'])
        return row.last