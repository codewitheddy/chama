# Design Document — Year-End Financials

## Overview

This feature adds three tightly-coupled capabilities to the DC Welfare Group chama system:

1. **Year-End Withdrawal recording** — a new `yearend` Django app that lets the Treasurer record the annual savings distribution as an auditable transaction, including per-member interest shares and member continuation/exit status.
2. **Available Fund Balance enforcement** — a shared utility (`utils/financials.py`) that computes the lending pool balance and is used to gate both new loan creation and loan rollovers.
3. **Member active-status tracking** — a new `is_active` boolean field on `Member` that is set to `False` when a member exits at year-end, filtering them out of active contribution and loan workflows.

The design follows the existing project conventions: class-based views, `TreasurerRequiredMixin` for write access, Bootstrap 5 templates, and the existing `utils/exports.py` pattern.

---

## Architecture

```
chama_system/
├── utils/
│   ├── exports.py          (existing)
│   └── financials.py       (NEW — shared get_available_fund_balance())
├── members/
│   └── models.py           (MODIFIED — add is_active field + migration)
├── loans/
│   ├── views.py            (MODIFIED — fund check on create + rollover)
│   └── forms.py            (MODIFIED — show balance on loan form)
├── dashboard/
│   └── views.py            (MODIFIED — use shared utility)
└── yearend/                (NEW Django app)
    ├── apps.py
    ├── models.py           (YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus)
    ├── forms.py
    ├── views.py
    ├── urls.py
    ├── admin.py
    └── migrations/
```

```
chama_system/chama_system/
├── settings.py             (MODIFIED — add 'yearend' to INSTALLED_APPS)
└── urls.py                 (MODIFIED — include yearend.urls at /yearend/)
```

```
chama_system/templates/
├── base.html               (MODIFIED — add Year-End nav item)
└── yearend/
    ├── yearend_list.html
    ├── yearend_form.html
    └── yearend_detail.html
```

### Data flow

```
Request → View → get_available_fund_balance() ← utils/financials.py
                        ↓
              YearEndWithdrawal.objects.aggregate(amount_withdrawn)
              Contribution.objects.aggregate(amount)
              Member.objects.aggregate(registration_fee)
              Loan interest collected (per-row min)
              Penalty.objects.filter(paid=True).aggregate(amount)
              Loan active/late balance aggregate
```

---

## Components and Interfaces

### 1. `utils/financials.py` — `get_available_fund_balance()`

Single function that all views call. Returns a `Decimal`.

```python
def get_available_fund_balance() -> Decimal:
    """
    Available_Fund_Balance =
        Total_Income
        − Principal_Outstanding
        − Total_Year_End_Withdrawals

    Total_Income =
        SUM(Contribution.amount)
        + SUM(Member.registration_fee)
        + SUM(interest_collected per loan)   # min(amount_paid, total_payable - loan_amount)
        + SUM(Penalty.amount where paid=True)

    Principal_Outstanding =
        SUM(total_payable - amount_paid) for Loans with status in ('active', 'late')

    Total_Year_End_Withdrawals =
        SUM(YearEndWithdrawal.amount_withdrawn)
    """
```

The dashboard's existing inline computation is replaced by a call to this function. The loan creation view and rollover view also call it.

### 2. `yearend` Django app

**Models** (see Data Models section below):
- `YearEndWithdrawal`
- `MemberInterestShare`
- `YearEndMemberStatus`

**Views**:

| View class | URL | Access | Description |
|---|---|---|---|
| `YearEndListView` | `/yearend/` | `TreasurerRequiredMixin` | Paginated list ordered by `financial_year` desc |
| `YearEndCreateView` | `/yearend/create/` | `TreasurerRequiredMixin` | Multi-section form: withdrawal + per-member shares + per-member status |
| `YearEndDetailView` | `/yearend/<pk>/` | `TreasurerRequiredMixin` | Detail with share breakdown and member status table |

**Forms**:
- `YearEndWithdrawalForm` — validates `amount_withdrawn > 0`, `interest_shared <= amount_withdrawn`, unique `financial_year`
- `MemberInterestShareFormSet` — inline formset; total of `amount` fields validated ≤ `interest_shared`
- `YearEndMemberStatusFormSet` — inline formset; validates no exiting member has an active/late loan

### 3. `members/models.py` — `is_active` field

```python
is_active = models.BooleanField(default=True)
```

Migration: `members/migrations/0004_member_is_active.py`

All existing members default to `True`. The `YearEndCreateView` sets this to `False` for exiting members inside a `transaction.atomic()` block.

### 4. `loans/views.py` — fund check on create and rollover

`LoanCreateView.form_valid()` calls `get_available_fund_balance()` before `super().form_valid()`. If `loan_amount > balance`, it calls `transaction.set_rollback(True)` and returns `form_invalid`.

`LoanRolloverView.post()` calls `get_available_fund_balance()` before `loan.do_rollover()`. If `outstanding > balance`, it redirects with an error message.

`LoanCreateView.get_context_data()` and `LoanRolloverView.get()` both inject `available_fund_balance` into the template context.

### 5. `dashboard/views.py` — use shared utility

The inline `treasurer_balance` computation is replaced:

```python
from utils.financials import get_available_fund_balance
available_fund_balance = get_available_fund_balance()
```

The template variable is renamed from `treasurer_balance` to `available_fund_balance` and the dashboard template is updated accordingly.

### 6. `base.html` — sidebar navigation

A new "Year-End" section is added to the sidebar between "Reports" and "System":

```html
<li class="nav-section">Year-End</li>
<li class="nav-item">
    <a href="{% url 'yearend:list' %}" class="nav-link {% if request.resolver_match.app_name == 'yearend' %}active{% endif %}">
        <i class="bi bi-calendar-check me-2"></i>Year-End Withdrawals
    </a>
</li>
```

---

## Data Models

### `YearEndWithdrawal`

```python
class YearEndWithdrawal(models.Model):
    financial_year   = models.PositiveIntegerField(unique=True)
    amount_withdrawn = models.DecimalField(max_digits=14, decimal_places=2,
                           validators=[MinValueValidator(Decimal('0.01'))])
    interest_shared  = models.DecimalField(max_digits=14, decimal_places=2,
                           default=Decimal('0.00'),
                           validators=[MinValueValidator(Decimal('0.00'))])
    date             = models.DateField()
    notes            = models.TextField(blank=True)
    recorded_by      = models.ForeignKey(settings.AUTH_USER_MODEL,
                           on_delete=models.PROTECT,
                           editable=False)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-financial_year']

    def __str__(self):
        return f"Year-End {self.financial_year} — KES {self.amount_withdrawn}"
```

Constraints enforced at the model/form level:
- `interest_shared <= amount_withdrawn` (form `clean()`)
- `financial_year` uniqueness (DB `unique=True` + form validation)

### `MemberInterestShare`

```python
class MemberInterestShare(models.Model):
    withdrawal = models.ForeignKey(YearEndWithdrawal,
                     on_delete=models.CASCADE, related_name='interest_shares')
    member     = models.ForeignKey('members.Member',
                     on_delete=models.PROTECT, related_name='interest_shares')
    amount     = models.DecimalField(max_digits=12, decimal_places=2,
                     default=Decimal('0.00'),
                     validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        unique_together = ('withdrawal', 'member')
        ordering = ['member__name']

    def __str__(self):
        return f"{self.member.name} — KES {self.amount} ({self.withdrawal.financial_year})"
```

Cascade delete is handled by `on_delete=models.CASCADE` on the `withdrawal` FK.

### `YearEndMemberStatus`

```python
class YearEndMemberStatus(models.Model):
    STATUS_CHOICES = [('continuing', 'Continuing'), ('exiting', 'Exiting')]

    withdrawal = models.ForeignKey(YearEndWithdrawal,
                     on_delete=models.CASCADE, related_name='member_statuses')
    member     = models.ForeignKey('members.Member',
                     on_delete=models.PROTECT, related_name='year_end_statuses')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES,
                     default='continuing')

    class Meta:
        unique_together = ('withdrawal', 'member')
        ordering = ['member__name']

    def __str__(self):
        return f"{self.member.name} — {self.status} ({self.withdrawal.financial_year})"
```

### `Member.is_active` (migration)

```python
# members/migrations/0004_member_is_active.py
operations = [
    migrations.AddField(
        model_name='member',
        name='is_active',
        field=models.BooleanField(default=True),
    ),
]
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Valid withdrawal persists with correct values

*For any* valid combination of `financial_year`, `amount_withdrawn` (> 0), `interest_shared` (≤ `amount_withdrawn`), and `date`, creating a `YearEndWithdrawal` should result in a persisted record whose stored field values exactly match the submitted values.

**Validates: Requirements 1.2**

---

### Property 2: Non-positive amount_withdrawn is always rejected

*For any* `amount_withdrawn` value that is zero or negative, the `YearEndWithdrawalForm` SHALL fail validation and no record SHALL be persisted.

**Validates: Requirements 1.3**

---

### Property 3: interest_shared > amount_withdrawn is always rejected

*For any* pair `(amount_withdrawn, interest_shared)` where `interest_shared > amount_withdrawn`, the form SHALL fail validation and no record SHALL be persisted.

**Validates: Requirements 1.4**

---

### Property 4: financial_year uniqueness is always enforced

*For any* `financial_year` value for which a `YearEndWithdrawal` already exists, attempting to create a second `YearEndWithdrawal` for the same year SHALL be rejected — regardless of the other field values.

**Validates: Requirements 1.5**

---

### Property 5: Per-member share total exceeding interest_shared is always rejected

*For any* `YearEndWithdrawal` with `interest_shared = S`, if the sum of all submitted `MemberInterestShare.amount` values exceeds `S`, the submission SHALL be rejected and no records SHALL be persisted.

**Validates: Requirements 2.3**

---

### Property 6: Cascade delete removes all associated shares

*For any* `YearEndWithdrawal` with any number N ≥ 0 of associated `MemberInterestShare` records, deleting the `YearEndWithdrawal` SHALL result in exactly zero `MemberInterestShare` records remaining for that withdrawal.

**Validates: Requirements 2.5**

---

### Property 7: Exiting member always has is_active set to False

*For any* `Member` (regardless of their current `is_active` state or contribution/loan history), marking them as `exiting` in a `YearEndMemberStatus` record SHALL set `Member.is_active = False`.

**Validates: Requirements 3.3**

---

### Property 8: Continuing member always retains is_active = True

*For any* `Member`, marking them as `continuing` in a `YearEndMemberStatus` record SHALL leave `Member.is_active = True`.

**Validates: Requirements 3.4**

---

### Property 9: Historical records are preserved for exiting members

*For any* `Member` with N contributions, M loans, P payments, and Q penalties, marking them as `exiting` SHALL NOT change those counts — only `is_active` changes.

**Validates: Requirements 3.5**

---

### Property 10: Member with outstanding loan cannot be marked as exiting

*For any* `Member` who has at least one `Loan` with status `active` or `late`, attempting to mark that member as `exiting` SHALL be rejected with a validation error.

**Validates: Requirements 3.7**

---

### Property 11: Available Fund Balance formula correctness

*For any* database state with arbitrary contributions, registration fees, loans, payments, penalties, and year-end withdrawals, `get_available_fund_balance()` SHALL return exactly `Total_Income − Principal_Outstanding − Total_Year_End_Withdrawals`.

**Validates: Requirements 4.1, 8.1**

---

### Property 12: Balance decreases by exactly amount_withdrawn after a withdrawal

*For any* `YearEndWithdrawal` with `amount_withdrawn = W`, the `Available_Fund_Balance` after saving the record SHALL equal the balance before saving minus `W`.

**Validates: Requirements 4.2**

---

### Property 13: Zero withdrawals preserves backward compatibility

*For any* database state where no `YearEndWithdrawal` records exist, `get_available_fund_balance()` SHALL return the same value as `Total_Income − Principal_Outstanding` (the previous `treasurer_balance` formula).

**Validates: Requirements 4.4**

---

### Property 14: Loan creation is rejected when amount exceeds available balance

*For any* loan creation attempt where `loan_amount > get_available_fund_balance()`, the system SHALL reject the loan and no `Loan` record SHALL be persisted.

**Validates: Requirements 6.1, 6.2, 6.5**

---

### Property 15: Loan rollover is rejected when outstanding balance exceeds available balance

*For any* loan rollover attempt where `loan.balance > get_available_fund_balance()`, the system SHALL reject the rollover and the `Loan` record SHALL remain unchanged.

**Validates: Requirements 7.1, 7.2, 7.5**

---

### Property 16: Available Fund Balance is consistent across all views

*For any* database state, the `available_fund_balance` value present in the dashboard context, the loan creation form context, and the rollover confirmation context SHALL all be equal (since they all call the same `get_available_fund_balance()` function).

**Validates: Requirements 8.1**

---

## Error Handling

| Scenario | Handling |
|---|---|
| `amount_withdrawn <= 0` | `YearEndWithdrawalForm.clean_amount_withdrawn()` raises `ValidationError` |
| `interest_shared > amount_withdrawn` | `YearEndWithdrawalForm.clean()` raises `ValidationError` |
| Duplicate `financial_year` | `YearEndWithdrawalForm.clean_financial_year()` raises `ValidationError`; DB `unique=True` is a safety net |
| Per-member share sum > `interest_shared` | `YearEndCreateView.form_valid()` validates formset totals before saving |
| Exiting member has active/late loan | `YearEndCreateView.form_valid()` checks each exiting member's loan status; rejects with message |
| `loan_amount > available_fund_balance` | `LoanCreateView.form_valid()` calls `get_available_fund_balance()`, calls `transaction.set_rollback(True)`, returns `form_invalid` with error message |
| `loan.balance > available_fund_balance` on rollover | `LoanRolloverView.post()` calls `get_available_fund_balance()`, redirects with `messages.error` |
| `available_fund_balance <= 0` on loan create/rollover | Same path as above — zero/negative balance fails the `>` check for any positive loan amount |
| DB integrity error on `YearEndWithdrawal` save | Wrapped in `transaction.atomic()`; exception surfaces as a 500 or caught and shown as a form error |

---

## Testing Strategy

### Unit tests (example-based)

- `YearEndWithdrawalForm` with valid data → passes
- `YearEndWithdrawalForm` with `amount_withdrawn=0` → fails
- `YearEndWithdrawalForm` with `interest_shared > amount_withdrawn` → fails
- `YearEndWithdrawalForm` duplicate `financial_year` → fails
- `YearEndListView` with no records → renders empty-state message
- `YearEndListView` with records → ordered by `financial_year` descending
- `YearEndDetailView` → renders `MemberInterestShare` and `YearEndMemberStatus` rows
- `LoanCreateView` context → contains `available_fund_balance`
- `LoanRolloverView` GET context → contains `available_fund_balance`
- Dashboard context → contains `available_fund_balance`
- Non-treasurer user accessing `/yearend/create/` → 403
- `recorded_by` is set from `request.user`, not from POST data

### Property-based tests (hypothesis)

Use [Hypothesis](https://hypothesis.readthedocs.io/) with Django integration (`hypothesis[django]`). Each property test runs a minimum of 100 iterations.

**Tag format:** `# Feature: year-end-financials, Property {N}: {property_text}`

| Property | Test description |
|---|---|
| P1 | `@given` valid withdrawal fields → record persists with matching values |
| P2 | `@given` `amount_withdrawn` drawn from `st.decimals(max_value=0)` → form invalid |
| P3 | `@given` `(amount, interest)` where `interest > amount` → form invalid |
| P4 | `@given` any `financial_year` → second withdrawal for same year rejected |
| P5 | `@given` list of share amounts whose sum > `interest_shared` → submission rejected |
| P6 | `@given` withdrawal with N shares → after deletion, 0 shares remain |
| P7 | `@given` any member → mark exiting → `is_active == False` |
| P8 | `@given` any member → mark continuing → `is_active == True` |
| P9 | `@given` member with N contributions/loans → mark exiting → counts unchanged |
| P10 | `@given` member with active/late loan → mark exiting → rejected |
| P11 | `@given` arbitrary DB state → `get_available_fund_balance()` == formula |
| P12 | `@given` withdrawal amount W → balance decreases by exactly W |
| P13 | `@given` DB state with no withdrawals → balance == `Total_Income - Principal_Outstanding` |
| P14 | `@given` `loan_amount > available_balance` → loan creation rejected, no record created |
| P15 | `@given` loan where `balance > available_balance` → rollover rejected, loan unchanged |
| P16 | `@given` any DB state → dashboard, loan form, rollover form all show same balance |

### Integration tests

- Full year-end creation flow: submit form with shares and statuses → verify all three model records created, `is_active` updated, balance reduced
- Loan creation with sufficient funds → loan created, balance reduced on next dashboard load
- Loan rollover with sufficient funds → rollover completes, balance updated
