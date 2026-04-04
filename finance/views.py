from datetime import date

import pandas as pd
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView
from sklearn.linear_model import LinearRegression

from .forms import BudgetForm, CategoryForm, RegistrationForm, TransactionForm
from .models import Budget, Category, Transaction, create_default_categories_for_user


def month_start(value):
    return value.replace(day=1)


def build_transaction_dataframe(queryset):
    rows = list(queryset.values('date', 'amount', 'transaction_type', 'category__name'))
    if not rows:
        return pd.DataFrame(columns=['date', 'amount', 'transaction_type', 'category', 'month'])

    frame = pd.DataFrame(rows)
    frame = frame.rename(columns={'category__name': 'category'})
    frame['date'] = pd.to_datetime(frame['date'])
    frame['amount'] = frame['amount'].astype(float)
    frame['month'] = frame['date'].dt.to_period('M').astype(str)
    return frame


def calculate_monthly_prediction(expense_frame):
    if expense_frame.empty:
        return None, []

    monthly_expense = (
        expense_frame.groupby('month', as_index=False)['amount']
        .sum()
        .sort_values('month')
        .reset_index(drop=True)
    )
    monthly_expense['period_date'] = pd.to_datetime(monthly_expense['month'])
    monthly_expense['month_index'] = range(1, len(monthly_expense) + 1)

    prediction_value = monthly_expense['amount'].iloc[-1]
    if len(monthly_expense) >= 2:
        model = LinearRegression()
        model.fit(monthly_expense[['month_index']], monthly_expense['amount'])
        prediction_value = max(float(model.predict([[len(monthly_expense) + 1]])[0]), 0)

    predicted_period = (monthly_expense['period_date'].max() + pd.offsets.MonthBegin(1)).to_pydatetime()
    prediction = {
        'label': predicted_period.strftime('%B %Y'),
        'amount': round(prediction_value, 2),
        'data_points': len(monthly_expense),
    }
    return prediction, monthly_expense.to_dict(orient='records')


def generate_smart_insights(frame, current_month_total, previous_month_total):
    if frame.empty:
        return ['Start adding transactions to unlock personalized insights and forecasts.']

    insights = []
    current_month = date.today().strftime('%Y-%m')
    current_month_expenses = frame[
        (frame['month'] == current_month) & (frame['transaction_type'] == Transaction.EXPENSE)
    ]

    if not current_month_expenses.empty:
        top_category = (
            current_month_expenses.groupby('category')['amount']
            .sum()
            .sort_values(ascending=False)
            .index[0]
        )
        insights.append(f'You spent the most on {top_category} this month.')

    if previous_month_total > 0 and current_month_total > previous_month_total:
        change = ((current_month_total - previous_month_total) / previous_month_total) * 100
        insights.append(f'Your expenses increased by {change:.1f}% compared to last month.')
    elif previous_month_total > 0 and current_month_total < previous_month_total:
        change = ((previous_month_total - current_month_total) / previous_month_total) * 100
        insights.append(f'Your expenses dropped by {change:.1f}% compared to last month.')

    expense_categories = frame[frame['transaction_type'] == Transaction.EXPENSE]
    if not expense_categories.empty:
        top_overall = (
            expense_categories.groupby('category')['amount']
            .sum()
            .sort_values(ascending=False)
            .index[0]
        )
        insights.append(f'{top_overall} is your highest overall expense category so far.')

    return insights or ['Your spending is stable. Keep tracking transactions to unlock deeper insights.']


def validate_form_instance(form, request):
    try:
        form.instance.full_clean()
    except ValidationError as error:
        for field, messages_list in error.message_dict.items():
            target_field = None if field == '__all__' else field
            for message in messages_list:
                form.add_error(target_field, message)
        messages.error(request, 'Please correct the highlighted errors and try again.')
        return False
    return True


class UserOwnedQuerySetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class RegisterView(CreateView):
    model = User
    form_class = RegistrationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        create_default_categories_for_user(self.object)
        messages.success(self.request, 'Account created successfully. You can log in now.')
        return response


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'finance/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        create_default_categories_for_user(user)

        transactions = Transaction.objects.filter(user=user).select_related('category')
        income_total = transactions.filter(transaction_type=Transaction.INCOME).aggregate(total=Sum('amount'))['total'] or 0
        expense_total = transactions.filter(transaction_type=Transaction.EXPENSE).aggregate(total=Sum('amount'))['total'] or 0
        balance = income_total - expense_total

        frame = build_transaction_dataframe(transactions)
        monthly_summary = (
            frame.pivot_table(
                index='month',
                columns='transaction_type',
                values='amount',
                aggfunc='sum',
                fill_value=0,
            ).reset_index()
            if not frame.empty
            else pd.DataFrame(columns=['month', Transaction.INCOME, Transaction.EXPENSE])
        )

        monthly_labels = monthly_summary['month'].tolist()
        monthly_income = monthly_summary[Transaction.INCOME].astype(float).round(2).tolist() if Transaction.INCOME in monthly_summary else [0 for _ in monthly_labels]
        monthly_expense = monthly_summary[Transaction.EXPENSE].astype(float).round(2).tolist() if Transaction.EXPENSE in monthly_summary else [0 for _ in monthly_labels]

        expense_frame = frame[frame['transaction_type'] == Transaction.EXPENSE] if not frame.empty else frame
        category_summary = (
            expense_frame.groupby('category')['amount'].sum().sort_values(ascending=False)
            if not expense_frame.empty
            else pd.Series(dtype=float)
        )
        prediction, prediction_history = calculate_monthly_prediction(expense_frame)

        current_month = month_start(date.today())
        current_month_key = current_month.strftime('%Y-%m')
        previous_month_key = (pd.Timestamp(current_month) - pd.offsets.MonthBegin(1)).strftime('%Y-%m')

        current_month_total = float(expense_frame.loc[expense_frame['month'] == current_month_key, 'amount'].sum()) if not expense_frame.empty else 0
        previous_month_total = float(expense_frame.loc[expense_frame['month'] == previous_month_key, 'amount'].sum()) if not expense_frame.empty else 0

        monthly_budget = Budget.objects.filter(user=user, month=current_month).first()
        budget_progress = None
        budget_alert = None
        if monthly_budget:
            limit_value = float(monthly_budget.limit_amount)
            budget_progress = min(round((current_month_total / limit_value) * 100, 2), 100) if limit_value else 0
            if current_month_total > limit_value:
                budget_alert = 'You have exceeded your monthly budget limit.'

        recent_summaries = []
        if not monthly_summary.empty:
            for item in monthly_summary.tail(6).to_dict(orient='records'):
                income_value = float(item.get(Transaction.INCOME, 0))
                expense_value = float(item.get(Transaction.EXPENSE, 0))
                recent_summaries.append({
                    'month': item['month'],
                    'income': round(income_value, 2),
                    'expense': round(expense_value, 2),
                    'net': round(income_value - expense_value, 2),
                })

        context.update({
            'income_total': income_total,
            'expense_total': expense_total,
            'balance': balance,
            'transaction_count': transactions.count(),
            'monthly_chart': {
                'labels': monthly_labels,
                'income': monthly_income,
                'expense': monthly_expense,
            },
            'category_chart': {
                'labels': category_summary.index.tolist(),
                'values': category_summary.round(2).tolist(),
            },
            'prediction': prediction,
            'prediction_history': prediction_history,
            'insights': generate_smart_insights(frame, current_month_total, previous_month_total),
            'top_categories': [
                {'name': label, 'amount': round(float(value), 2)}
                for label, value in category_summary.head(5).items()
            ],
            'monthly_summaries': recent_summaries,
            'recent_transactions': transactions[:5],
            'monthly_budget': monthly_budget,
            'current_month_expense_total': round(current_month_total, 2),
            'budget_progress': budget_progress,
            'budget_alert': budget_alert,
            'analysis_snapshot': {
                'average_expense': round(float(expense_frame['amount'].mean()), 2) if not expense_frame.empty else 0,
                'highest_expense': round(float(expense_frame['amount'].max()), 2) if not expense_frame.empty else 0,
                'active_months': len(monthly_labels),
            },
        })
        return context


class TransactionListView(UserOwnedQuerySetMixin, ListView):
    model = Transaction
    template_name = 'finance/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().select_related('category')
        query = self.request.GET.get('q')
        transaction_type = self.request.GET.get('type')

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(category__name__icontains=query) | Q(notes__icontains=query)
            )
        if transaction_type in {Transaction.INCOME, Transaction.EXPENSE}:
            queryset = queryset.filter(transaction_type=transaction_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['selected_type'] = self.request.GET.get('type', '')
        return context


class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('transaction_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Transaction added successfully.')
        return super().form_valid(form)


class TransactionUpdateView(UserOwnedQuerySetMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('transaction_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Transaction updated successfully.')
        return super().form_valid(form)


class TransactionDeleteView(UserOwnedQuerySetMixin, DeleteView):
    model = Transaction
    template_name = 'finance/transaction_confirm_delete.html'
    success_url = reverse_lazy('transaction_list')

    def form_valid(self, form):
        messages.success(self.request, 'Transaction deleted successfully.')
        return super().form_valid(form)


class CategoryListView(UserOwnedQuerySetMixin, ListView):
    model = Category
    template_name = 'finance/category_list.html'
    context_object_name = 'categories'


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'finance/category_form.html'
    success_url = reverse_lazy('category_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Category created successfully.')
        return super().form_valid(form)


class CategoryUpdateView(UserOwnedQuerySetMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'finance/category_form.html'
    success_url = reverse_lazy('category_list')

    def form_valid(self, form):
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Category updated successfully.')
        return super().form_valid(form)


class CategoryDeleteView(UserOwnedQuerySetMixin, DeleteView):
    model = Category
    template_name = 'finance/category_confirm_delete.html'
    success_url = reverse_lazy('category_list')

    def form_valid(self, form):
        if self.object.transactions.exists():
            messages.error(self.request, 'This category has transactions and cannot be deleted yet.')
            return redirect('category_list')
        messages.success(self.request, 'Category deleted successfully.')
        return super().form_valid(form)


class BudgetListView(UserOwnedQuerySetMixin, ListView):
    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_month'] = month_start(date.today())
        return context


class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('budget_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Budget saved successfully.')
        return super().form_valid(form)


class BudgetUpdateView(UserOwnedQuerySetMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('budget_list')

    def form_valid(self, form):
        if not validate_form_instance(form, self.request):
            return self.form_invalid(form)
        messages.success(self.request, 'Budget updated successfully.')
        return super().form_valid(form)


class BudgetDeleteView(UserOwnedQuerySetMixin, DeleteView):
    model = Budget
    template_name = 'finance/budget_confirm_delete.html'
    success_url = reverse_lazy('budget_list')

    def form_valid(self, form):
        messages.success(self.request, 'Budget deleted successfully.')
        return super().form_valid(form)
