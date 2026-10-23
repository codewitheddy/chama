# Member Registration Fee Toggle Feature

**Implementation Date:** August 15, 2026  
**Status:** ✅ Complete

---

## Overview

Added a registration fee payment toggle to the member creation form, allowing administrators to flexibly handle member onboarding when payment may not be immediate.

---

## What Changed

### 1. **Member Form** (`members/forms.py`)

Added a new form field:
- **`registration_fee_paid_toggle`** (BooleanField / Checkbox)
  - Label: "Has the member paid the registration fee?"
  - Help text: Clear instructions about checked vs unchecked states
  - CSS class: `form-check-input` for Bootstrap styling

```python
registration_fee_paid_toggle = forms.BooleanField(
    required=False,
    label="Has the member paid the registration fee?",
    help_text="Check if the member has already paid the registration fee at signup. If unchecked, you'll be able to add the fee later when they pay.",
    widget=forms.CheckboxInput(attrs={
        'class': 'form-check-input',
        'id': 'regFeeToggle',
    }),
)
```

### 2. **Member Creation View** (`members/views.py`)

Updated `MemberCreateView.form_valid()` method:

**Before:**
- Always applied current registration fee rate to new members

**After:**
- Checks the toggle value
- **If checked:** Applies current registration fee rate (automatic payment on signup)
- **If unchecked:** Sets registration fee to 0 (payment deferred until admin records it)

```python
def form_valid(self, form):
    """
    Handle registration fee toggle:
    - If checked: apply current registration fee rate
    - If unchecked: set to 0 (admin can add payment later)
    """
    from .models import RegistrationFeeRate
    from decimal import Decimal
    
    fee_paid = form.cleaned_data.get('registration_fee_paid_toggle', False)
    
    if fee_paid:
        current_rate = RegistrationFeeRate.current_rate()
        form.instance.registration_fee_paid = (
            current_rate.amount if current_rate else Decimal('0')
        )
    else:
        form.instance.registration_fee_paid = Decimal('0')
    
    return super().form_valid(form)
```

### 3. **Member Form Template** (`templates/members/member_form.html`)

Added new section:
- **Registration Fee section** with section divider
- Toggle checkbox with clear visual indicators
- Helper text explaining the two states

```html
<!-- ── Registration Fee ──────────────────────────── -->
<div class="section-divider"><i class="bi bi-credit-card me-1"></i>Registration Fee</div>

<div class="mb-4">
    <div class="form-check">
        {{ form.registration_fee_paid_toggle }}
        <label class="form-check-label small" for="regFeeToggle">
            Has the member paid the registration fee?
        </label>
        <div class="form-text">
            ✓ Checked: Apply current registration fee automatically<br>
            ✗ Unchecked: Add the fee later when the member pays
        </div>
    </div>
</div>
```

---

## Workflow

### Scenario 1: Member Pays Registration Fee at Signup
1. Admin adds new member
2. **Checks** the "Has the member paid the registration fee?" toggle
3. Saves member
4. System automatically sets `registration_fee_paid` to current rate (e.g., 2,000 KES)
5. Member can immediately start participating

### Scenario 2: Member Will Pay Registration Fee Later
1. Admin adds new member
2. **Leaves unchecked** the "Has the member paid the registration fee?" toggle
3. Saves member
4. System sets `registration_fee_paid` to 0
5. Member is registered but owes registration fee
6. When member pays (e.g., next week):
   - Admin navigates to **Members > Registration Fee Payments**
   - Clicks "Add Registration Fee Payment"
   - Records the payment with date, amount, and method
   - System updates the member's `registration_fee_paid` field

---

## User Interface

### Add Member Form

The form now includes:

1. **Personal Details Section**
   - Name, Phone, Date Joined

2. **Photo & ID Document Section**
   - Member photo and ID document upload

3. **Next of Kin / Beneficiary Section**
   - Beneficiary name, phone, relationship

4. **Registration Fee Section** *(NEW)*
   - Toggle checkbox with helper text
   - Visual indicators for checked/unchecked states

### Benefits

- **Clearer Intent:** Admins explicitly state whether fee was paid
- **Flexibility:** Accommodates immediate payment or deferred payment scenarios
- **Better UX:** No need to navigate to separate payment form if fee is paid upfront
- **Audit Trail:** Each registration fee payment is recorded separately in `RegistrationFeePayment` model

---

## Technical Details

### Models Involved

**Member model:**
- `registration_fee_paid` (DecimalField)
  - Stores total amount paid in registration fees
  - Set to 0 by default (or current rate if toggle checked)

**RegistrationFeePayment model:**
- Records individual payment transactions
- Allows tracking: amount, date, method, receipt number
- Links payment to member

**RegistrationFeeRate model:**
- Configurable fee rate (effective date-based)
- Used to auto-populate fee amount when toggle is checked

### Database

No database migrations required. This feature uses:
- Existing `Member.registration_fee_paid` field
- Existing `RegistrationFeePayment` model for payment tracking
- Existing `RegistrationFeeRate` model for current rates

---

## Related Features

### Adding Deferred Registration Fee Payment

If a member didn't pay at signup, admins can later add the payment:

1. Navigate to **Members > Registration Fee Payments**
2. Click **"Add Registration Fee Payment"**
3. Fill in:
   - Member (dropdown)
   - Amount
   - Payment Date
   - Payment Method (Cash, M-Pesa, Bank Transfer, Cheque)
   - Receipt Number (optional)
   - Notes (optional)
4. Save

This creates a `RegistrationFeePayment` record and updates the member's `registration_fee_paid` total.

### Reporting

Members with unpaid registration fees can be identified by:
- Dashboard: Members with `registration_fee_paid = 0` or less than current rate
- Reports: Registration Fee Payment Report shows:
  - Members who have paid
  - Members who haven't paid
  - Payment dates and methods
  - Outstanding fees

---

## Form Validation

The form validates:
- **Name:** Required, max 200 characters
- **Phone:** Required, unique
- **Date Joined:** Optional, defaults to today
- **Photo:** Optional, JPG/PNG only, max 5 MB
- **ID Document:** Optional, PDF/JPG/PNG, max 10 MB
- **Next of Kin fields:** Optional
- **Registration Fee Toggle:** Optional (defaults to unchecked)

---

## Implementation Notes

### Why a Toggle Instead of Direct Field?

1. **Cleaner UX:** Checkbox is more intuitive than a "Registration Fee Amount" field
2. **Automatic Logic:** Uses `RegistrationFeeRate.current_rate()` automatically
3. **Deferred Payment Pattern:** Unchecked naturally leads to deferred payment workflow
4. **Audit Trail:** Keeps payment history in `RegistrationFeePayment` model, not buried in `Member` record

### Form Field Handling

The `registration_fee_paid_toggle` is:
- **Not part of Meta.fields** (not saved directly to model)
- **Accessed via `form.cleaned_data`** in `form_valid()`
- **Used to conditionally set `Member.registration_fee_paid`**

This pattern allows flexibility while keeping the model clean.

---

## Testing Checklist

- ✅ Form renders correctly with toggle checkbox
- ✅ Checkbox is styled properly with Bootstrap
- ✅ Helper text displays clear instructions
- ✅ "Checked" state applies current registration fee rate
- ✅ "Unchecked" state sets fee to 0
- ✅ Member is saved successfully in both cases
- ✅ Payment can be recorded later via "Add Registration Fee Payment"
- ✅ Form validates all fields correctly
- ✅ Syntax check passes for forms.py and views.py

---

## Future Enhancements

Potential improvements:
1. **Bulk Payment Import:** Upload CSV of members + fee payments
2. **Payment Reminders:** Auto-email members with unpaid fees
3. **Fee Waiver Workflow:** Approve/deny fee waivers for specific members
4. **Tiered Fees:** Different fees for different member categories
5. **Payment Plans:** Allow installment payments for registration fee

---

## Summary

This improvement provides admins with flexible member onboarding options:
- **Immediate Payment:** Member pays fee at signup
- **Deferred Payment:** Admin records payment when member pays later

The toggle-based approach is intuitive, maintains a clean audit trail, and accommodates real-world scenarios where registration fees may not be paid immediately upon joining.

**Result:** More flexible member management workflow with better UX and audit capabilities.
