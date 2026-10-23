# Implementation Plan: Year-End Financials

## Overview

Implement the year-end financials feature in three layers:
1. Shared utility + Member model change (foundation)
2. New `yearend` Django app (models, views, forms, templates)
3. Modifications to existing apps (loans, dashboard, base template)

All views use `TreasurerRequiredMixin`. Property-based tests use Hypothesis in `yearend/tests_pbt.py`.

---

## Tasks

- [x] 1. Create shared utility and Member model migration
  - Create `chama_system/utils/financials.py` with `get_available_fund_balance()` implementing the formula: `Total_Income − Principal_Outstanding − Total_Year_End_Withdrawals`
    - `Total_Income = SUM(Contribution.amount) + SUM(Member.registration_fee) + SUM(interest_collected per loan) + SUM(Penalty.amount where paid=True)`
    - `Principal_Outstanding = SUM(total_payable − amount_paid)` for Loans with status `active` or `late`
    - `Total_Year_End_Withdrawals = SUM(YearEndWithdrawal.amount_withdrawn)` (import lazily to avoid circular imports)
  - Add `is_active = models.BooleanField(default=True)` to `members/models.py`
  - Create migration `members/migrations/0004_member_is_active.py`
  - _Requirements: 4.1, 8.1, 3.3, 3.4_

  - [ ]* 1.1 Write property test for `get_available_fund_balance()` formula correctness
    - **Property 11: Available Fund Balance formula correctness**
    - **Validates: Requirements 4.1, 8.1**

  - [ ]* 1.2 Write property test for zero-withdrawals backward compatibility
    - **Property 13: Zero withdrawals preserves backward compatibility**
    - **Validates: Requirements 4.4**

- [x] 2. Scaffold the `yearend` Django app
  - Create directory `chama_system/yearend/` with `__init__.py`, `apps.py`, `admin.py`, `migrations/__init__.py`
  - Register `'yearend'` in `INSTALLED_APPS` in `chama_system/chama_system/settings.py`
  - Add `path('yearend/', include('yearend.urls', namespace='yearend'))` to `chama_system/chama_system/urls.py`
  - _Requirements: 5.1, 5.3_

- [x] 3. Implement `yearend` models and initial migration
  - Create `yearend/models.py` with three models:
    - `YearEndWithdrawal`: `financial_year` (unique PositiveIntegerField), `amount_withdrawn`, `interest_shared`, `date`, `notes`, `recorded_by` (FK to AUTH_USER_MODEL, editable=False), `created_at`
    - `MemberInterestShare`: FK to `YearEndWithdrawal` (CASCADE), FK to `Member` (PROTECT), `amount`; unique_together `(withdrawal, member)`
    - `YearEndMemberStatus`: FK to `YearEndWithdrawal` (CASCADE), FK to `Member` (PROTECT), `status` choices `continuing`/`exiting`; unique_together `(withdrawal, member)`
  - Register all three models in `yearend/admin.py`
  - Create and run initial migration `yearend/migrations/0001_initial.py`
  - _Requirements: 1.1, 2.1, 3.1_

  - [ ]* 3.1 Write property test for valid withdrawal persistence
    - **Property 1: Valid withdrawal persists with correct values**
    - **Validates: Requirements 1.2**

  - [ ]* 3.2 Write property test for non-positive amount_withdrawn rejection
    - **Property 2: Non-positive amount_withdrawn is always rejected**
    - **Validates: Requirements 1.3**

  - [ ]* 3.3 Write property test for interest_shared > amount_withdrawn rejection
    - **Property 3: interest_shared > amount_withdrawn is always rejected**
    - **Validates: Requirements 1.4**

  - [ ]* 3.4 Write property test for financial_year uniqueness enforcement
    - **Property 4: financial_year uniqueness is always enforced**
    - **Validates: Requirements 1.5**

  - [ ]* 3.5 Write property test for cascade delete of interest shares
    - **Property 6: Cascade delete removes all associated shares**
    - **Validates: Requirements 2.5**

- [x] 4. Implement `yearend` forms
  - Create `yearend/forms.py` with:
    - `YearEndWithdrawalForm`: validates `amount_withdrawn > 0` in `clean_amount_withdrawn()`, validates `interest_shared <= amount_withdrawn` in `clean()`, validates unique `financial_year` in `clean_financial_year()`
    - `MemberInterestShareFormSet`: inline formset for `MemberInterestShare`
    - `YearEndMemberStatusFormSet`: inline formset for `YearEndMemberStatus`
  - _Requirements: 1.3, 1.4, 1.5, 2.3, 3.7_

  - [ ]* 4.1 Write property test for per-member share total exceeding interest_shared
    - **Property 5: Per-member share total exceeding interest_shared is always rejected**
    - **Validates: Requirements 2.3**

  - [ ]* 4.2 Write property test for exiting member with outstanding loan rejection
    - **Property 10: Member with outstanding loan cannot be marked as exiting**
    - **Validates: Requirements 3.7**

- [x] 5. Implement `yearend` views and URLs
  - Create `yearend/urls.py` with `app_name = 'yearend'` and three URL patterns: `''` → `YearEndListView` (name `list`), `'create/'` → `YearEndCreateView` (name `create`), `'<int:pk>/'` → `YearEndDetailView` (name `detail`)
  - Create `yearend/views.py` with:
    - `YearEndListView(TreasurerRequiredMixin, ListView)`: paginated, ordered by `financial_year` desc
    - `YearEndDetailView(TreasurerRequiredMixin, DetailView)`: passes `interest_shares` and `member_statuses` to context
    - `YearEndCreateView(TreasurerRequiredMixin, CreateView)`: handles `YearEndWithdrawalForm` + both formsets in `form_valid()` inside `transaction.atomic()`; sets `recorded_by = request.user`; validates formset share total ≤ `interest_shared`; sets `Member.is_active = False` for exiting members; rejects if exiting member has active/late loan
  - _Requirements: 1.2, 1.6, 2.2, 2.3, 3.2, 3.3, 3.7, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 5.1 Write property test for exiting member sets is_active to False
    - **Property 7: Exiting member always has is_active set to False**
    - **Validates: Requirements 3.3**

  - [ ]* 5.2 Write property test for continuing member retains is_active = True
    - **Property 8: Continuing member always retains is_active = True**
    - **Validates: Requirements 3.4**

  - [ ]* 5.3 Write property test for historical records preserved for exiting members
    - **Property 9: Historical records are preserved for exiting members**
    - **Validates: Requirements 3.5**

- [ ] 6. Checkpoint — Ensure all yearend app tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Create `yearend` templates
  - Create `chama_system/templates/yearend/` directory with three templates following Bootstrap 5 card/table layout from existing templates:
    - `yearend_list.html`: extends `base.html`; Bootstrap card with table of withdrawals ordered by year desc; empty-state message when no records; links to detail and create views
    - `yearend_form.html`: extends `base.html`; multi-section Bootstrap card form — withdrawal fields, per-member interest share inputs (one row per active member), per-member status dropdowns (continuing/exiting); shows `available_fund_balance` for reference
    - `yearend_detail.html`: extends `base.html`; withdrawal summary card; `MemberInterestShare` table; `YearEndMemberStatus` table with continuing/exiting badges
  - _Requirements: 1.1, 2.4, 3.6, 5.1, 5.2, 5.4_

- [x] 8. Modify `dashboard/views.py` to use shared utility
  - Import `get_available_fund_balance` from `utils.financials`
  - Replace the inline `treasurer_balance` computation with a call to `get_available_fund_balance()`
  - Add `available_fund_balance` to the context dict (keep `treasurer_balance` as an alias pointing to the same value for backward compatibility with any existing template references, or update the dashboard template to use `available_fund_balance`)
  - _Requirements: 4.3, 8.1_

  - [ ]* 8.1 Write property test for Available Fund Balance consistency across views
    - **Property 16: Available Fund Balance is consistent across all views**
    - **Validates: Requirements 8.1**

- [x] 9. Modify `loans/views.py` to enforce fund availability
  - In `LoanCreateView.get_context_data()`: import and call `get_available_fund_balance()`, inject as `available_fund_balance` into context
  - In `LoanCreateView.form_valid()`: call `get_available_fund_balance()` before `super().form_valid()`; if `loan_amount > balance`, call `transaction.set_rollback(True)` and return `form_invalid(form)` with an error message including the current balance in KES
  - In `LoanRolloverView.get()`: call `get_available_fund_balance()`, inject as `available_fund_balance` into context
  - In `LoanRolloverView.post()`: call `get_available_fund_balance()` before `loan.do_rollover()`; if `loan.balance > available_balance`, redirect with `messages.error` including the current balance in KES
  - Update `loans/loan_form.html` and `loans/loan_rollover_confirm.html` templates to display `available_fund_balance`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 9.1 Write property test for loan creation rejection when amount exceeds balance
    - **Property 14: Loan creation is rejected when amount exceeds available balance**
    - **Validates: Requirements 6.1, 6.2, 6.5**

  - [ ]* 9.2 Write property test for loan rollover rejection when outstanding exceeds balance
    - **Property 15: Loan rollover is rejected when outstanding balance exceeds available balance**
    - **Validates: Requirements 7.1, 7.2, 7.5**

  - [ ]* 9.3 Write property test for balance decreases by exactly amount_withdrawn
    - **Property 12: Balance decreases by exactly amount_withdrawn after a withdrawal**
    - **Validates: Requirements 4.2**

- [x] 10. Add Year-End section to `base.html` sidebar
  - Insert a new `nav-section` label "Year-End" between the "Reports" section and the "System" section
  - Add a `nav-item` link to `{% url 'yearend:list' %}` with icon `bi-calendar-check` and active class when `request.resolver_match.app_name == 'yearend'`
  - _Requirements: 5.1, 5.3_

- [ ] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All PBT tasks go in `chama_system/yearend/tests_pbt.py` using `hypothesis[django]`; each test runs a minimum of 100 iterations
- Each property test is tagged with `# Feature: year-end-financials, Property {N}: {property_text}`
- `get_available_fund_balance()` imports `YearEndWithdrawal` lazily inside the function body to avoid circular imports at module load time
- The `recorded_by` field is set from `request.user` in `YearEndCreateView.form_valid()` — never from POST data
- All three model saves in `YearEndCreateView` (withdrawal + formsets + member `is_active` updates) are wrapped in a single `transaction.atomic()` block
- Loan fund check in `LoanCreateView` must happen inside the existing `transaction.atomic()` block, before `super().form_valid()`
