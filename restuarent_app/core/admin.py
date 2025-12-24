from django.contrib import admin
from django.contrib import admin
from .models import Unit, RawMaterialUnitConversion


from django.contrib import admin
from .models import POSSettings, PrintStation, TokenSequence, Category, MenuItem

@admin.register(POSSettings)
class POSSettingsAdmin(admin.ModelAdmin):
    list_display = ('restaurant_name', 'start_of_day_time', 'updated_at')

@admin.register(PrintStation)
class PrintStationAdmin(admin.ModelAdmin):
    list_display = ('name', 'print_separate_slip', 'use_separate_sequence')

@admin.register(TokenSequence)
class TokenSequenceAdmin(admin.ModelAdmin):
    list_display = ('business_date', 'station', 'last')
    list_filter = ('station',)

# Make sure Category and MenuItem admins allow selecting the Station
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'default_station', 'show_in_orders')

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'station', 'price')
    list_filter = ('category', 'station')


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

