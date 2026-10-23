# Investments Management Module - Complete Guide

## Overview

The **Investments** module extends the Chama system with comprehensive investment tracking and management capabilities. Groups can now track investments in real estate, stocks, bonds, mutual funds, fixed deposits, and other assets, monitor their valuations over time, record returns/dividends, and manage withdrawals/liquidations.

## Features

### 1. **Investment Recording**
- Record new investments with comprehensive details
- Support for multiple fund sources (group funds, bank accounts, other sources)
- Track initial investment amount, date, quantity/units, and description
- Store certificate numbers and supporting documents (PDF/image uploads)
- Payment method tracking (cash or M-Pesa with confirmation codes)
- Investment status management (active, completed, suspended)

### 2. **Valuation Management**
- Record periodic valuations of investments
- Track both total value and per-unit value (for shares, land plots, etc.)
- View valuation history with performance metrics
- Calculate gain/loss from purchase price
- Monitor ROI percentage over time

### 3. **Return/Dividend Tracking**
- Record dividends, interest, rental income, bonuses, and other returns
- Multiple payment methods (cash, M-Pesa, bank transfer)
- Link returns to specific bank accounts when applicable
- Track total returns received on each investment
- Detailed descriptions of return types

### 4. **Withdrawal Management**
- Record partial or full withdrawals/liquidations
- Track sale proceeds and buyer information
- Calculate gain/loss on each withdrawal
- Support for multiple payment methods
- Automatic status update to "completed" on full liquidation

### 5. **Performance Analytics**
- Dashboard showing total invested amount
- Current valuation tracking
- Total returns earned
- Net gain/loss calculations
- Return on Investment (ROI) percentage
- Summary statistics across all investments

### 6. **Role-Based Access Control**
- **Admin**: Full access including deletion with password confirmation
- **Treasurer**: Can create, update, record valuations and returns
- **Read-Only**: Can view investment details and reports
- All deletions require admin password for security

---

## Data Models

### InvestmentType
Admin-defined investment product templates for standardization.

**Fields:**
- `name` (CharField): Unique investment type name
- `description` (TextField): Details about the investment type
- `category` (CharField): Category (real_estate, stocks, bonds, mutual_fund, fixed_deposit, savings, cooperative, business, other)
- `expected_return_rate` (DecimalField): Expected annual return percentage
- `is_active` (BooleanField): Whether the type is available for new investments
- `created_at`, `updated_at` (DateTimeField): Timestamps

**Usage:**
Admins create investment types via Django admin, then treasurers select them when recording new investments.

---

### Investment
Core investment transaction model.

**Key Fields:**
- `investment_type` (ForeignKey): Link to InvestmentType
- `initial_amount` (DecimalField): Capital invested
- `date_invested` (DateField): When the investment was made
- `quantity` (DecimalField): Number of units/shares/plots (default: 1)
- `description` (TextField): Investment details (location, property info, etc.)
- `status` (CharField): active, completed, or suspended

**Fund Source:**
- `fund_source` (CharField): group_funds, bank_account, or other
- `fund_source_bank` (ForeignKey): Bank account (if fund_source is bank_account)
- `fund_source_label` (CharField): Description (if fund_source is other)

**Payment & Documentation:**
- `payment_type` (CharField): cash or mpesa
- `mpesa_code` (CharField): M-Pesa confirmation code
- `certificate_number` (CharField): Certificate/deed number
- `document` (FileField): Supporting document upload

**Audit:**
- `recorded_by` (ForeignKey to User): Who recorded it
- `created_at`, `updated_at` (DateTimeField): Timestamps

**Computed Properties:**
- `current_value`: Latest valuation or initial amount
- `total_returns_received`: Sum of all returns
- `total_withdrawn`: Sum of all withdrawals
- `net_gain_loss`: Current value + returns - initial
- `roi_percentage`: Return on investment percentage

---

### InvestmentValuation
Periodic revaluation snapshots.

**Fields:**
- `investment` (ForeignKey): The investment being valued
- `valuation_date` (DateField): When the valuation was done
- `current_value` (DecimalField): Total current value
- `value_per_unit` (DecimalField, optional): Price per unit
- `notes` (TextField): Market conditions, valuation method, appraiser name
- `valuation_by` (ForeignKey to User): Who recorded the valuation
- `created_at` (DateTimeField): Timestamp

**Computed Properties:**
- `gain_loss_from_purchase`: Difference vs. initial investment
- `gain_loss_percentage`: Percentage change from initial

---

### InvestmentReturn
Dividends, interest, or other returns from investments.

**Fields:**
- `investment` (ForeignKey): The investment generating returns
- `return_type` (CharField): dividend, interest, rental, bonus, or other
- `amount` (DecimalField): Amount of return
- `return_date` (DateField): When the return was paid
- `payment_type` (CharField): cash, mpesa, or bank_transfer
- `mpesa_code`, `bank_account` (optional): Payment details
- `description` (TextField): Details about the return
- `recorded_by` (ForeignKey to User): Who recorded it
- `created_at` (DateTimeField): Timestamp

---

### InvestmentWithdrawal
Partial or full withdrawals/liquidations.

**Fields:**
- `investment` (ForeignKey): The investment being withdrawn
- `withdrawal_type` (CharField): partial or full
- `quantity_withdrawn` (DecimalField): Amount of units withdrawn
- `amount_received` (DecimalField): Proceeds from sale
- `withdrawal_date` (DateField): When the withdrawal occurred
- `payment_type` (CharField): How payment was received
- `mpesa_code`, `bank_account` (optional): Payment details
- `buyer_name` (CharField, optional): Who bought it
- `notes` (TextField): Sale terms and conditions
- `recorded_by` (ForeignKey to User): Who recorded it
- `created_at`, `updated_at` (DateTimeField): Timestamps

**Computed Properties:**
- `gain_loss`: Proceeds minus cost basis

---

## Views & URL Routing

### URL Structure
```
/investments/                          # Investment list
/investments/add/                      # Add investment form
/investments/<id>/                     # Investment detail view
/investments/<id>/edit/                # Edit investment
/investments/<id>/delete/              # Delete investment
/investments/<id>/valuations/add/      # Record valuation
/investments/valuations/<id>/delete/   # Delete valuation
/investments/<id>/returns/add/         # Record return
/investments/returns/<id>/delete/      # Delete return
/investments/<id>/withdrawals/add/     # Record withdrawal
/investments/withdrawals/<id>/delete/  # Delete withdrawal
```

### Key Views

**InvestmentListView**
- Role: MemberAccessMixin (read access for all)
- Features: Filtering by status and search, summary cards (total invested, current value, returns, net position)
- Pagination: 20 items per page

**InvestmentDetailView**
- Shows complete investment profile with all related data
- Tabbed sections for valuations, returns, and withdrawals
- Performance metrics (gain/loss, ROI)

**InvestmentCreateView / InvestmentUpdateView**
- Role: TreasurerRequiredMixin
- Comprehensive form with conditional fields based on fund source and payment type
- Auto-recorded user tracking

**InvestmentDeleteView**
- Role: AdminRequiredMixin + AdminPasswordDeleteMixin
- Requires deletion reason and admin password
- Soft delete via recycle bin

**Valuation/Return/Withdrawal Views**
- Specialized create views for each transaction type
- Auto-redirect to investment detail on success
- Delete confirmations with password requirement

---

## Forms

### InvestmentForm
Complete investment recording form with:
- Investment type selection
- Amount, date, and quantity fields
- Fund source conditional fields (bank account or other label)
- Payment method with M-Pesa code validation
- Document upload
- Status selection

### InvestmentValuationForm
Valuation recording with:
- Valuation date
- Current total value
- Optional per-unit value
- Notes field

### InvestmentReturnForm
Return tracking with:
- Return type selection (dividend, interest, rental, bonus, other)
- Amount and date
- Payment method with conditional fields
- Description

### InvestmentWithdrawalForm
Withdrawal recording with:
- Withdrawal type (partial or full)
- Quantity and amount received
- Payment method
- Buyer name and notes

---

## Admin Interface

### InvestmentTypeAdmin
- List view with category, return rate, and active status
- Search by name and description
- Filter by category and active status

### InvestmentAdmin
- List display with investment type, amounts, values, status, recorder
- Inline editors for valuations, returns, and withdrawals
- Readonly performance summary fields
- Color-coded gain/loss display
- Comprehensive fieldsets with collapsible sections

### InvestmentValuationAdmin
- Track all valuations with date and performance metrics
- Search and filter by investment type and date

### InvestmentReturnAdmin
- List all returns by investment type and date
- Filter by return type and payment method

### InvestmentWithdrawalAdmin
- Track all withdrawals with performance metrics
- Identify gain/loss on each sale

---

## Templates

### list.html
Summary dashboard with:
- Total invested, current value, returns, and net position cards
- Filter form (search, status)
- Investments table with performance metrics
- Action buttons (view, edit, delete)
- Pagination

### detail.html
Complete investment profile with:
- Investment header with status badge
- Performance summary cards
- Investment details section
- Quick actions sidebar
- Valuations, returns, and withdrawals tables
- Add/edit/delete buttons for related records

### form.html
Investment recording form with:
- Fieldsets for organization (details, fund source, payment, documentation, status)
- Conditional field visibility (JavaScript-driven)
- Bootstrap styling and validation

### Specialized Forms
- `valuation_form.html` - Clean, minimal valuation recording
- `return_form.html` - Return recording with payment method options
- `withdrawal_form.html` - Withdrawal with buyer and payment info
- `*_confirm_delete.html` - Deletion confirmations with password requirement

---

## Signals & Audit Trail

The module includes Django signals that automatically:
- Log investment creation/deletion to AuditLog
- Track who performed each action
- Record key transaction details (amounts, types)
- Enable audit trail for compliance

---

## Usage Examples

### Recording an Investment
1. Navigate to `/investments/add/`
2. Select investment type (e.g., "Land - Residential Plot")
3. Enter initial amount and date
4. Select fund source (e.g., Bank Account → select KCB)
5. Choose payment method and enter M-Pesa code if applicable
6. Upload property document
7. Click "Save Investment"

### Tracking Valuations
1. From investment detail page, click "Add Valuation"
2. Enter new valuation date
3. Enter current total value
4. Optionally add per-unit value
5. Add notes about valuation method
6. System calculates and displays gain/loss

### Recording Dividend Income
1. From investment detail, click "Record Return"
2. Select return type (e.g., "Dividend")
3. Enter amount and date received
4. Choose payment method
5. Add notes (e.g., per share amount)
6. Returns are immediately added to total returns received

### Withdrawing/Liquidating
1. Click "Withdraw" from investment detail
2. Choose withdrawal type (partial or full)
3. Enter quantity and amount received
4. Record buyer information
5. On full withdrawal, investment status automatically updates to "Completed"

---

## Integration with Other Modules

### Bank Accounts
- Investments can be funded from specific bank accounts
- Investment returns and withdrawals can be linked to bank accounts
- BankBalance model updated when investments are liquidated

### Audit Module
- All investment transactions logged automatically
- User actions tracked for compliance

### Dashboard
- Can add investment summary widgets to main dashboard
- Display total investments and performance metrics

---

## Business Rules

1. **Fund Source Validation**: When fund_source is "bank_account", a specific account must be selected
2. **Payment Type**: M-Pesa payments require a valid confirmation code
3. **Quantity Tracking**: Cannot withdraw more quantity than invested
4. **Status Management**: Automatically transitions to "completed" on full liquidation
5. **Valuation**: Current value defaults to initial amount until first valuation
6. **Deletion**: Requires admin password and deletion reason for audit trail

---

## Database Schema Summary

```
InvestmentType
  ├─ id (PK)
  ├─ name (unique)
  ├─ category
  ├─ expected_return_rate
  └─ is_active

Investment
  ├─ id (PK)
  ├─ investment_type_id (FK → InvestmentType)
  ├─ initial_amount
  ├─ date_invested
  ├─ quantity
  ├─ status
  ├─ fund_source
  ├─ fund_source_bank_id (FK → BankAccount, nullable)
  ├─ payment_type
  ├─ mpesa_code
  ├─ recorded_by_id (FK → User)
  └─ timestamps

InvestmentValuation (OneToMany → Investment)
  ├─ id (PK)
  ├─ investment_id (FK)
  ├─ valuation_date
  ├─ current_value
  ├─ value_per_unit
  ├─ valuation_by_id
  └─ created_at

InvestmentReturn (OneToMany → Investment)
  ├─ id (PK)
  ├─ investment_id (FK)
  ├─ return_type
  ├─ amount
  ├─ return_date
  ├─ payment_type
  ├─ bank_account_id (FK, nullable)
  ├─ recorded_by_id
  └─ created_at

InvestmentWithdrawal (OneToMany → Investment)
  ├─ id (PK)
  ├─ investment_id (FK)
  ├─ withdrawal_type
  ├─ quantity_withdrawn
  ├─ amount_received
  ├─ withdrawal_date
  ├─ payment_type
  ├─ bank_account_id (FK, nullable)
  ├─ recorded_by_id
  └─ timestamps
```

---

## Troubleshooting

### Valuations not showing
- Ensure valuations exist for the investment
- Check that valuation_date is set and valid

### Performance calculations incorrect
- Verify initial_amount is set correctly
- Check that latest valuation has been recorded
- Ensure all returns and withdrawals are logged

### M-Pesa code validation fails
- Code must be 6-20 characters
- Only alphanumeric characters allowed
- Code must be unique across investment returns

### Fund source bank not appearing
- Ensure bank account is marked as active
- Check that it's in the database

---

## Future Enhancements

Possible additions:
- Dividend reinvestment tracking
- Projected returns based on expected_return_rate
- Investment portfolio reports and analytics
- Comparison views between investments
- Dividend distribution to members
- Investment history/timeline views
- Performance benchmarking
- Risk assessment tracking

---

## File Structure

```
investments/
├── __init__.py
├── __pycache__/
├── migrations/
│   ├── 0001_initial.py
│   └── __init__.py
├── apps.py
├── admin.py               # Django admin configuration
├── forms.py               # All forms (Investment, Valuation, Return, Withdrawal)
├── models.py              # All models
├── urls.py                # URL routing
├── views.py               # All views
├── signals.py             # Audit logging signals
└── tests.py               # Unit tests

templates/investments/
├── list.html              # Investment list view
├── form.html              # Investment create/update
├── detail.html            # Investment detail with tabs
├── valuation_form.html    # Valuation recording
├── return_form.html       # Return recording
├── withdrawal_form.html   # Withdrawal recording
├── confirm_delete.html    # Investment deletion
├── valuation_confirm_delete.html
├── return_confirm_delete.html
└── withdrawal_confirm_delete.html
```

---

## Support & Documentation

For questions or issues:
1. Check Django admin for data integrity
2. Review audit logs for transaction history
3. Verify role-based permissions
4. Check database migrations have been applied

---

**Module Version:** 1.0
**Created:** August 2026
**Framework:** Django 4.x
**Python:** 3.9+
