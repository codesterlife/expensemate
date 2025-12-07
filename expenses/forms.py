from django import forms
from .models import Expense, BudgetCap, Category


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name',
                'maxlength': '50'
            })
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'date', 'description']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Select category',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'placeholder': 'Enter amount'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter expense description'
            })
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter categories for the current user
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user).order_by('name')


class BudgetCapForm(forms.ModelForm):
    class Meta:
        model = BudgetCap
        fields = ['name', 'amount', 'period', 'category']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter budget name'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Enter budget amount'
            }),
            'period': forms.Select(attrs={
                'class': 'form-control'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control'
            })
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter categories for the current user
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user).order_by('name')
        
        # Make category optional
        self.fields['category'].required = False
        self.fields['category'].help_text = "Leave blank to apply to all categories"
