from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from django.http import HttpResponse
import google.generativeai as genai
import os
from dotenv import load_dotenv

from .models import Expense, BudgetCap, Category
from .forms import ExpenseForm, BudgetCapForm, CategoryForm

load_dotenv()


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully! Welcome to ExpenseMate.')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'registration/register.html', {'form': form})


@login_required
def category_list(request):
    categories = Category.objects.filter(user=request.user).order_by('name')
    context = {
        'categories': categories,
    }
    return render(request, 'expenses/category_list.html', context)


@login_required
def category_add(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('category_list')
    else:
        form = CategoryForm()
    
    context = {
        'form': form,
        'is_add': True,
    }
    return render(request, 'expenses/category_form.html', context)


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'is_add': False,
    }
    return render(request, 'expenses/category_form.html', context)


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    category_name = category.name
    category.delete()
    messages.success(request, f'Category "{category_name}" deleted successfully!')
    return redirect('category_list')


@login_required
def dashboard(request):
    expenses = Expense.objects.filter(user=request.user)
    
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_expenses = expenses.filter(date__gte=month_start).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    week_ago = now.date() - timedelta(days=7)
    week_expenses = expenses.filter(date__gte=week_ago).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    days_in_month = now.day
    avg_daily = (month_expenses / days_in_month) if days_in_month > 0 else Decimal('0')
    
    category_stats = expenses.values('category__name').annotate(total=Sum('amount')).order_by('-total')
    category_data = {
        'labels': [item['category__name'] or 'Uncategorized' for item in category_stats],
        'values': [float(item['total']) for item in category_stats]
    }
    
    last_6_months = []
    monthly_values = []
    for i in range(5, -1, -1):
        month = now - timedelta(days=30 * i)
        month_start_date = month.replace(day=1)
        if i > 0:
            next_month = (month_start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_total = expenses.filter(date__gte=month_start_date, date__lt=next_month).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        else:
            month_total = expenses.filter(date__gte=month_start_date).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        last_6_months.append(month.strftime('%b %Y'))
        monthly_values.append(float(month_total))
    
    monthly_data = {
        'labels': last_6_months,
        'values': monthly_values
    }
    
    recent_expenses = expenses[:5]
    
    budgets = BudgetCap.objects.filter(user=request.user, is_active=True)
    exceeded_budgets = [b for b in budgets if b.is_exceeded()]
    warning_budgets = [b for b in budgets if not b.is_exceeded() and b.get_percentage_used() >= 80]
    
    context = {
        'total_expenses': total_expenses,
        'month_expenses': month_expenses,
        'week_expenses': week_expenses,
        'avg_daily': round(avg_daily, 2),
        'current_month': now.strftime('%B %Y'),
        'category_data': json.dumps(category_data),
        'monthly_data': json.dumps(monthly_data),
        'recent_expenses': recent_expenses,
        'exceeded_budgets': exceeded_budgets,
        'warning_budgets': warning_budgets,
        'budgets': budgets,
    }
    
    return render(request, 'expenses/dashboard.html', context)


@login_required
def expense_list(request):
    expenses = Expense.objects.filter(user=request.user)
    
    category = request.GET.get('category')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if category:
        expenses = expenses.filter(category__id=category)
    if from_date:
        expenses = expenses.filter(date__gte=from_date)
    if to_date:
        expenses = expenses.filter(date__lte=to_date)
    
    total = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    user_categories = Category.objects.filter(user=request.user).order_by('name')
    
    context = {
        'expenses': expenses,
        'categories': user_categories,
        'total': total,
    }
    
    return render(request, 'expenses/expense_list.html', context)


@login_required
def expense_add(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            
            exceeded_budgets = check_budget_alerts(request.user)
            if exceeded_budgets:
                budget_names = ', '.join([b.name for b in exceeded_budgets])
                messages.warning(request, f'Budget alert! You have exceeded: {budget_names}')
            
            messages.success(request, 'Expense added successfully!')
            return redirect('expense_list')
    else:
        form = ExpenseForm(user=request.user)
    
    context = {
        'form': form,
        'today': timezone.now().date().isoformat(),
    }
    
    return render(request, 'expenses/expense_form.html', context)


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense, user=request.user)
        if form.is_valid():
            form.save()
            
            exceeded_budgets = check_budget_alerts(request.user)
            if exceeded_budgets:
                budget_names = ', '.join([b.name for b in exceeded_budgets])
                messages.warning(request, f'Budget alert! You have exceeded: {budget_names}')
            
            messages.success(request, 'Expense updated successfully!')
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense, user=request.user)
    
    context = {
        'form': form,
        'expense': expense,
    }
    
    return render(request, 'expenses/expense_form.html', context)


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    expense.delete()
    messages.success(request, 'Expense deleted successfully!')
    return redirect('expense_list')


@login_required
def export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="expenses.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Category', 'Amount', 'Description'])
    
    expenses = Expense.objects.filter(user=request.user)
    for expense in expenses:
        category_name = expense.category.name if expense.category else 'Uncategorized'
        writer.writerow([expense.date, category_name, expense.amount, expense.description])
    
    return response


@login_required
def export_pdf(request):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    title = Paragraph(f"<b>ExpenseMate - Expense Report for {request.user.username}</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    expenses = Expense.objects.filter(user=request.user)
    
    data = [['Date', 'Category', 'Amount', 'Description']]
    total = Decimal('0')
    
    for expense in expenses:
        category_name = expense.category.name if expense.category else 'Uncategorized'
        data.append([
            expense.date.strftime('%Y-%m-%d'),
            category_name,
            f'Rs.{expense.amount}',
            expense.description[:50]
        ])
        total += expense.amount
    
    data.append(['', '', f'Rs.{total}', 'TOTAL'])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="expenses.pdf"'
    
    return response


@login_required
def ai_predictions(request):
    prediction = None
    error = None
    
    if request.method == 'POST':
        prediction_type = request.POST.get('prediction_type')
        custom_question = request.POST.get('custom_question', '')
        
        try:
            api_key = os.environ.get('GEMINI_API_KEY')
            sys_prompt = "No Markdown syntax allowed."
            
            if not api_key:
                error = "Please set your GEMINI_API_KEY environment variable to use AI predictions."
            else:
                genai.configure(api_key=api_key)
                
                expenses = Expense.objects.filter(user=request.user)
                
                expense_summary = []
                for expense in expenses[:50]:
                    expense_summary.append(f"{expense.date}: {expense.category} - ₹{expense.amount}")
                
                category_stats = expenses.values('category').annotate(total=Sum('amount')).order_by('-total')
                category_text = ', '.join([f"{item['category']}: ₹{item['total']}" for item in category_stats])
                
                total = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                
                if prediction_type == 'next_month':
                    prompt = f"""Based on these expense records, predict next month's spending:
                    
Total expenses so far: ₹{total}
Category breakdown: {category_text}

Recent expenses:
{chr(10).join(expense_summary)}

Provide a brief prediction of next month's spending with specific amounts."""
                
                elif prediction_type == 'category_insights':
                    prompt = f"""Analyze these expenses and provide category-wise insights:
                    
Total expenses: ₹{total}
Category breakdown: {category_text}

Recent expenses:
{chr(10).join(expense_summary)}

Which categories need attention? Provide specific recommendations."""
                
                elif prediction_type == 'budget_advice':
                    prompt = f"""Based on these expenses, provide budget recommendations:
                    
Total expenses: ₹{total}
Category breakdown: {category_text}

Recent expenses:
{chr(10).join(expense_summary)}

Suggest a realistic monthly budget and saving strategies."""
                
                else:
                    prompt = f"""Based on these expense records, answer this question: {custom_question}
                    
Total expenses: ₹{total}
Category breakdown: {category_text}

Recent expenses:
{chr(10).join(expense_summary)}"""
                
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt + sys_prompt)
                prediction = response.text.replace('\n', '<br>')
        
        except Exception as e:
            error = f"Error generating predictions: {str(e)}"
    
    return render(request, 'expenses/ai_predictions.html', {
        'prediction': prediction,
        'error': error
    })


@login_required
def budget_list(request):
    budgets = BudgetCap.objects.filter(user=request.user)
    exceeded_budgets = [b for b in budgets if b.is_exceeded()]
    
    context = {
        'budgets': budgets,
        'exceeded_budgets': exceeded_budgets,
    }
    
    return render(request, 'expenses/budget_list.html', context)


@login_required
def budget_add(request):
    if request.method == 'POST':
        form = BudgetCapForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            
            messages.success(request, 'Budget cap created successfully!')
            return redirect('budget_list')
    else:
        form = BudgetCapForm(user=request.user)
    
    context = {
        'form': form,
    }
    
    return render(request, 'expenses/budget_form.html', context)


@login_required
@login_required
def budget_edit(request, pk):
    budget = get_object_or_404(BudgetCap, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = BudgetCapForm(request.POST, instance=budget, user=request.user)
        if form.is_valid():
            form.save()
            
            messages.success(request, 'Budget cap updated successfully!')
            return redirect('budget_list')
    else:
        form = BudgetCapForm(instance=budget, user=request.user)
    
    context = {
        'form': form,
        'budget': budget,
    }
    
    return render(request, 'expenses/budget_form.html', context)


@login_required
def budget_delete(request, pk):
    budget = get_object_or_404(BudgetCap, pk=pk, user=request.user)
    budget.delete()
    messages.success(request, 'Budget cap deleted successfully!')
    return redirect('budget_list')


def check_budget_alerts(user):
    budgets = BudgetCap.objects.filter(user=user, is_active=True)
    return [b for b in budgets if b.is_exceeded()]
