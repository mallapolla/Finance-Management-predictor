from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Budget, Category, Transaction


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css_class} form-control'.strip()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ('name', 'category_type', 'description')


class TransactionForm(StyledModelForm):
    class Meta:
        model = Transaction
        fields = ('title', 'transaction_type', 'category', 'amount', 'date', 'notes')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['transaction_type'].widget.attrs['class'] = 'form-select'
        self.fields['category'].widget.attrs['class'] = 'form-select'

        if user:
            queryset = Category.objects.filter(user=user)
            selected_type = (
                self.data.get('transaction_type')
                or self.initial.get('transaction_type')
                or getattr(self.instance, 'transaction_type', None)
            )
            if selected_type in {Category.INCOME, Category.EXPENSE}:
                queryset = queryset.filter(category_type=selected_type)
            self.fields['category'].queryset = queryset.order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        transaction_type = cleaned_data.get('transaction_type')
        if category and transaction_type and category.category_type != transaction_type:
            self.add_error('category', 'Choose a category that matches the transaction type.')
        return cleaned_data


class BudgetForm(StyledModelForm):
    month = forms.DateField(
        input_formats=['%Y-%m'],
        widget=forms.DateInput(attrs={'type': 'month'}, format='%Y-%m'),
        initial=date.today().replace(day=1),
    )

    class Meta:
        model = Budget
        fields = ('month', 'limit_amount')

    def clean_month(self):
        month = self.cleaned_data['month']
        return month.replace(day=1)
