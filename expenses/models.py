from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
from decimal import Decimal

class Category(models.Model):
    DEFAULT_CATEGORIES = [
        ('Food', 'Food & Dining'),
        ('Transport', 'Transportation'),
        ('Shopping', 'Shopping'),
        ('Entertainment', 'Entertainment'),
        ('Health', 'Healthcare'),
        ('Bills', 'Bills & Utilities'),
        ('Education', 'Education'),
        ('Other', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='custom_categories')
    name = models.CharField(max_length=50)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses', null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        category_name = self.category.name if self.category else 'Uncategorized'
        return f"{category_name} - ₹{self.amount} on {self.date}"


class BudgetCap(models.Model):
    PERIOD_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budget_caps')
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default='monthly')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='budget_caps')
    start_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        category_text = f" ({self.category})" if self.category else " (All Categories)"
        return f"{self.name} - ₹{self.amount}/{self.period}{category_text}"
    
    def get_period_dates(self):
        today = timezone.now().date()
        
        if today < self.start_date:
            return self.start_date, self.start_date
        
        if self.period == 'weekly':
            days_since_start = (today - self.start_date).days
            current_period = days_since_start // 7
            period_start = self.start_date + timedelta(days=current_period * 7)
            period_end = period_start + timedelta(days=6)
        elif self.period == 'monthly':
            months_since_start = (today.year - self.start_date.year) * 12 + (today.month - self.start_date.month)
            start_year = self.start_date.year + (self.start_date.month + months_since_start - 1) // 12
            start_month = (self.start_date.month + months_since_start - 1) % 12 + 1
            try:
                period_start = self.start_date.replace(year=start_year, month=start_month)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(start_year, start_month)[1]
                period_start = self.start_date.replace(year=start_year, month=start_month, day=min(self.start_date.day, last_day))
            
            if start_month == 12:
                end_year = start_year + 1
                end_month = 1
            else:
                end_year = start_year
                end_month = start_month + 1
            try:
                period_end = self.start_date.replace(year=end_year, month=end_month) - timedelta(days=1)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(end_year, end_month)[1]
                period_end = self.start_date.replace(year=end_year, month=end_month, day=min(self.start_date.day, last_day)) - timedelta(days=1)
        else:
            years_since_start = today.year - self.start_date.year
            try:
                period_start = self.start_date.replace(year=self.start_date.year + years_since_start)
            except ValueError:
                period_start = self.start_date.replace(year=self.start_date.year + years_since_start, day=28)
            try:
                period_end = self.start_date.replace(year=self.start_date.year + years_since_start + 1) - timedelta(days=1)
            except ValueError:
                period_end = self.start_date.replace(year=self.start_date.year + years_since_start + 1, day=28) - timedelta(days=1)
        
        return period_start, period_end
    
    def get_current_spending(self):
        period_start, period_end = self.get_period_dates()
        expenses = self.user.expenses.filter(date__gte=period_start, date__lte=period_end)
        
        if self.category:
            expenses = expenses.filter(category=self.category)
        
        total = expenses.aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0')
        return total
    
    @property
    def get_remaining(self):
        spent = self.get_current_spending()
        return self.amount - spent
    
    def is_exceeded(self):
        return self.get_current_spending() > self.amount
    
    def get_percentage_used(self):
        spent = self.get_current_spending()
        if self.amount > 0:
            return min(100, int((spent / self.amount) * 100))
        return 0
    
    @property
    def over_amount(self):
        """Return positive amount over budget, or 0 if under"""
        remaining = self.get_remaining
        return abs(remaining) if remaining < 0 else 0
