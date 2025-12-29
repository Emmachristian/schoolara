# finance/urls.py
from django.urls import path
from . import views, htmx_views

app_name = 'finance'

urlpatterns = [
    # =============================================================================
    # HTMX SEARCH ENDPOINTS
    # =============================================================================

    # Account Types
    path('htmx/account-types/search/', htmx_views.account_type_search, name='account_type_search'),

    # Accounts
    path('htmx/accounts/search/', htmx_views.account_search, name='account_search'),
    path('htmx/accounts/quick-stats/', htmx_views.account_quick_stats, name='account_quick_stats'),

    # Expense Categories
    path('htmx/expense-categories/search/', htmx_views.expense_category_search, name='expense_category_search'),

    # Expenses
    path('htmx/expenses/search/', htmx_views.expense_search, name='expense_search'),
    path('htmx/expenses/quick-stats/', htmx_views.expense_quick_stats, name='expense_quick_stats'),

    # Expense Payments
    path('htmx/expense-payments/search/', htmx_views.expense_payment_search, name='expense_payment_search'),

    # Journals
    path('htmx/journals/search/', htmx_views.journal_search, name='journal_search'),

    # Journal Entries
    path('htmx/journal-entries/search/', htmx_views.journal_entry_search, name='journal_entry_search'),
    path('htmx/journal-entries/quick-stats/', htmx_views.journal_entry_quick_stats, name='journal_entry_quick_stats'),

    # Journal Transactions
    path('htmx/journal-transactions/search/', htmx_views.journal_transaction_search, name='journal_transaction_search'),

    # Budgets
    path('htmx/budgets/search/', htmx_views.budget_search, name='budget_search'),
    path('htmx/budgets/quick-stats/', htmx_views.budget_quick_stats, name='budget_quick_stats'),

    # Budget Lines
    path('htmx/budget-lines/search/', htmx_views.budget_line_search, name='budget_line_search'),

]
