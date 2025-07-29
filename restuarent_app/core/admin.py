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
