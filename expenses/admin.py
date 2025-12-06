from django.contrib import admin
from .models import Expense, BudgetCap

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'category', 'amount', 'description')
    list_filter = ('category', 'date', 'user')
    search_fields = ('description',)
    date_hierarchy = 'date'

@admin.register(BudgetCap)
class BudgetCapAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'amount', 'period', 'category', 'is_active')
    list_filter = ('period', 'category', 'is_active', 'user')
    search_fields = ('name',)
