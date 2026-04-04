# Personal Finance Management Web Application

MoneyMind is a Django-based personal finance tracker built for portfolio use and interview discussions. It includes authentication, transaction management, budgeting, spending analytics with Pandas, Chart.js dashboards, and a starter machine learning forecast using scikit-learn.

## Features

- User registration, login, and logout
- Income and expense CRUD operations
- Custom and default categories
- Monthly budget tracking with over-limit alerts
- Dashboard cards, charts, and insights
- Pandas-based monthly summaries and top-category analysis
- Linear Regression prediction for next month's expenses

## Project Structure

```text
finance_manager/
    settings.py
    urls.py
finance/
    admin.py
    forms.py
    models.py
    signals.py
    urls.py
    views.py
templates/
    base.html
    registration/
    finance/
static/
    css/styles.css
manage.py
```

## Installation

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Start the development server:

```bash
python manage.py runserver
```

5. Open `http://127.0.0.1:8000/`

## Machine Learning Logic

- Expenses are grouped month-wise using Pandas.
- A `LinearRegression` model is trained on historical monthly expense totals.
- If enough history exists, the next month's expense is predicted and displayed on the dashboard.
- If only one month exists, the latest month's amount is used as a basic starter prediction.
