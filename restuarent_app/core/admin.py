from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Unit, RawMaterialUnitConversion

@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('symbol','name','unit_type')
    list_filter  = ('unit_type',)
    search_fields = ('symbol','name')

@admin.register(RawMaterialUnitConversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display = ('raw_material','unit','to_base_factor')
    list_filter  = ('unit','raw_material')
    search_fields = ('raw_material__name',)


# core/admin.py
from django.contrib import admin
from .models import Expense, CashFlow, BankAccount

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date','category','amount','created_by')
    list_filter  = ('category','date')

@admin.register(CashFlow)
class CashFlowAdmin(admin.ModelAdmin):
    list_display = ('date','flow_type','amount','bank_account','created_by')
    list_filter  = ('flow_type','bank_account','date')

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name','account_number')

# admin.py
from .models import Staff, Role

admin.site.register(Staff)
admin.site.register(Role)

