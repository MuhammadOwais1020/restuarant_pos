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

from django.db.models import Max
from django.utils import timezone
from .models import Order, TableSession

def get_next_token_number():
    today = timezone.localtime(timezone.now()).date()

    max_order = (
        Order.objects
             .filter(created_at__date=today)
             .aggregate(Max('token_number'))
        ['token_number__max']
        or 0
    )
    max_session = (
        TableSession.objects
             .filter(created_at__date=today)
             .aggregate(Max('token_number'))
        ['token_number__max']
        or 0
    )
    return max(max_order, max_session) + 1
