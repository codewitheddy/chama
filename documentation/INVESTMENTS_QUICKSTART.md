# Investments Module - Quick Start Guide

## Installation & Setup

The Investments module has been fully integrated into the Chama system. No additional installation is required beyond what has been completed.

### What Was Done
✅ Created complete `investments` Django app
✅ Registered in settings.py (INSTALLED_APPS)
✅ Added URL routing to main urls.py
✅ Created database migrations and applied them
✅ Created models, forms, views, templates, and admin interface
✅ System check passed with no issues

### Files Created
- **Models**: `investments/models.py` (5 models: InvestmentType, Investment, InvestmentValuation, InvestmentReturn, InvestmentWithdrawal)
- **Forms**: `investments/forms.py` (4 forms with validation)
- **Views**: `investments/views.py` (13 views for CRUD operations)
- **URLs**: `investments/urls.py` (11 URL patterns)
- **Admin**: `investments/admin.py` (Complete admin configuration)
- **Templates**: 9 HTML templates for all operations
- **Signals**: `investments/signals.py` (Audit trail logging)
- **Tests**: `investments/tests.py` (Basic model tests)

---

## Accessing the Module

### Main Entry Points
1. **Investments List**: Navigate to `/investments/`
2. **Add Investment**: Click "Add Investment" button or go to `/investments/add/`
3. **Admin Interface**: Go to `/admin/investments/` to manage investment types and view all records

### Navigation
The investments module should appear in your main navigation menu. If not, add this link to your base template:
```html
<a href="{% url 'investments:list' %}" class="nav-link">
  <i class="fas fa-chart-line"></i> Investments
</a>
```

---

## First Steps

### Step 1: Create Investment Types (Admin Only)
1. Go to Django Admin (`/admin/investments/investmenttype/`)
2. Click "Add Investment Type"
3. Create investment types for your group:
   - Land - Residential Plot
   - Shares - NSEG
   - Fixed Deposit - Bank Account
   - Mutual Fund - Equity Fund
   - Business Venture - Poultry Farm
   - House - Commercial Property
   - Cooperative Society - Merry Go Round

### Step 2: Record Your First Investment (Treasurer+)
1. Go to Investments → Add Investment
2. Select investment type (e.g., "Land - Residential Plot")
3. Fill in details:
   - Initial Amount: e.g., 500,000 KES
   - Date Invested: e.g., 2024-01-15
   - Quantity: e.g., 1 (for one plot)
   - Fund Source: Select "Bank Account" or "Group Funds"
   - Payment Method: Select "Cash" or "M-Pesa"
4. If uploading document, select the certificate/deed file
5. Click "Save Investment"

### Step 3: Record a Valuation (Treasurer+)
1. From investment detail page, click "Add Valuation"
2. Enter valuation date
3. Enter current market value
4. Add notes (e.g., "Appraised by John Smith")
5. Click "Record Valuation"
6. System now shows: Current Value, Gain/Loss, ROI%

### Step 4: Record Returns/Dividends (Treasurer+)
1. From investment detail, click "Record Return"
2. Select return type: Dividend, Interest, Rental, Bonus, etc.
3. Enter amount received
4. Select payment method
5. Add description
6. Click "Record Return"

### Step 5: Record Withdrawal/Sale (Treasurer+)
1. From investment detail, click "Withdraw"
2. Choose: Partial or Full withdrawal
3. Enter quantity and amount received
4. Record buyer name
5. On FULL withdrawal, investment status auto-updates to "Completed"

---

## Key Features at a Glance

### Performance Tracking
Dashboard shows 4 key metrics:
- **Total Invested**: Sum of all initial investments
- **Current Value**: Latest valuation or initial amount
- **Total Returns**: All dividends, interest, rental income
- **Net Position**: Current value + returns - invested amount

### Search & Filter
- Search by investment name, description, certificate number
- Filter by status (Active, Completed, Suspended)
- Results show ROI%, Gain/Loss, and status at a glance

### Detailed Views
Each investment shows:
- Investment details (type, category, fund source)
- Valuation history with performance metrics
- All returns received with dates and amounts
- Withdrawal/liquidation records
- Gain/loss calculations

### Role-Based Permissions
- **Admin**: Full access + can delete with password
- **Treasurer**: Can record all transactions
- **Read-Only**: Can view all investment details
- All destructive actions require admin password

---

## Common Scenarios

### Scenario 1: Land Investment Purchase
```
1. Create InvestmentType: "Land - Residential Plot"
2. Add Investment:
   - Type: Land - Residential Plot
   - Amount: 500,000 KES
   - Quantity: 1 plot
   - Fund Source: Bank Account (KCB)
   - Payment: M-Pesa QHX4Y2Z1AB
   - Certificate: Upload title deed scan
3. First Valuation (after 6 months):
   - Date: 2024-07-15
   - Current Value: 575,000 KES
   - Notes: "Revalued based on similar property sales"
   - System shows: ROI = 15%, Gain = 75,000 KES
```

### Scenario 2: Fixed Deposit Interest Income
```
1. Add Investment:
   - Type: Fixed Deposit - Bank Account
   - Amount: 200,000 KES
   - Date: 2024-01-01
2. After 3 months, Record Return:
   - Type: Interest
   - Amount: 5,000 KES
   - Payment: Bank Transfer
   - Description: "Quarterly interest at 10% per annum"
3. Current Value still 200,000 (principal unchanged)
   But Total Returns now shows 5,000 KES
```

### Scenario 3: Partial Share Sale
```
1. Investment: 1,000 shares at 10 KES each = 10,000 KES invested
2. Record Valuation: Now worth 15 KES per share = 15,000 KES
3. Sell 300 shares at 15 KES = 4,500 KES
   - Withdrawal Type: Partial
   - Quantity: 300
   - Amount: 4,500 KES
   - Gain on sale: 1,500 KES
4. Investment remains active with 700 shares
```

### Scenario 4: Full Property Liquidation
```
1. Investment: House purchased for 2,500,000 KES
2. Latest Valuation: 3,000,000 KES (20% appreciation)
3. Sell property for 3,000,000 KES
   - Withdrawal Type: FULL
   - Amount: 3,000,000 KES
4. System automatically changes status to "COMPLETED"
5. Investment now appears in completed list
```

---

## Reports & Analytics

### Investment Summary Report
Navigate to `/investments/` to see:
- Total capital deployed across all investments
- Breakdown by investment type and status
- Overall portfolio gain/loss
- Weighted ROI across portfolio

### Individual Investment Performance
From investment detail page:
- Historical valuation trend (dates and values)
- Returns timeline (dividends, interest received)
- Cost basis vs. current value analysis
- Withdrawal history with gain/loss per sale

---

## Best Practices

### Recording Transactions
1. **Always** include a detailed description
2. **Upload documents** when available (deeds, certificates, receipts)
3. **Record M-Pesa codes** for audit trail
4. **Use meaningful names** for investment types
5. **Valuate regularly** (quarterly recommended)

### Fund Source
- Use "Bank Account" to link to specific bank account
- Use "Group Funds" for internal group capital
- Use "Other" for external loans or partner funding

### Document Management
- Keep all original documents secure
- Store scanned copies via the system
- Include certificate numbers for reference

### Audit Trail
- All actions logged to audit log
- Deletion requires password confirmation
- Reason for deletion is captured
- Helpful for regulatory compliance

---

## Troubleshooting

### Issue: Can't see Investments in menu
**Solution**: Clear browser cache, refresh page, or check that 'investments' is in INSTALLED_APPS

### Issue: Can't add investment, form is empty
**Solution**: Create InvestmentType in admin first, then try adding investment

### Issue: M-Pesa code validation fails
**Solution**: Code must be 6-20 alphanumeric characters. Remove spaces.

### Issue: Can't record valuation
**Solution**: Ensure you have Treasurer or Admin role. Check that investment exists.

### Issue: Deletion blocked
**Solution**: Ensure you're Admin. Enter correct admin password. Provide deletion reason.

---

## Database Queries (For Developers)

### Get all active investments
```python
from investments.models import Investment
active = Investment.objects.filter(status='active')
```

### Calculate portfolio value
```python
total_invested = Investment.objects.aggregate(Sum('initial_amount'))['initial_amount__sum']
total_current = sum(inv.current_value for inv in Investment.objects.all())
total_gains = sum(inv.net_gain_loss for inv in Investment.objects.all())
```

### Get recent returns
```python
from investments.models import InvestmentReturn
recent = InvestmentReturn.objects.filter(return_date__gte='2024-01-01').order_by('-return_date')
```

### Top performing investments
```python
investments = Investment.objects.all()
top = sorted(investments, key=lambda x: x.roi_percentage, reverse=True)[:5]
```

---

## Admin Commands

```bash
# Create migrations
python manage.py makemigrations investments

# Apply migrations
python manage.py migrate investments

# Run system check
python manage.py check

# Run tests
python manage.py test investments

# Django shell for queries
python manage.py shell
```

---

## URLs Reference

| URL | Purpose | Role |
|-----|---------|------|
| `/investments/` | List all investments | All |
| `/investments/add/` | Create new investment | Treasurer+ |
| `/investments/<id>/` | View investment details | All |
| `/investments/<id>/edit/` | Edit investment | Treasurer+ |
| `/investments/<id>/delete/` | Delete investment | Admin |
| `/investments/<id>/valuations/add/` | Record valuation | Treasurer+ |
| `/investments/<id>/returns/add/` | Record return | Treasurer+ |
| `/investments/<id>/withdrawals/add/` | Record withdrawal | Treasurer+ |
| `/admin/investments/` | Admin interface | Admin |

---

## Support

For detailed documentation, see: **INVESTMENTS_MODULE_GUIDE.md**

For technical questions:
1. Review Django ORM documentation
2. Check model docstrings in `models.py`
3. Review form validation in `forms.py`
4. Check view implementations in `views.py`

---

## Summary

You now have a fully functional investment management system that:
✅ Tracks multiple investments across various asset classes
✅ Records periodic valuations and calculates performance metrics
✅ Tracks income/returns from investments
✅ Manages withdrawals and liquidations
✅ Provides audit trails for compliance
✅ Integrates with bank accounts
✅ Supports role-based access control
✅ Stores supporting documents

**Start recording your group's investments today!**

---

**Last Updated:** August 2026
**Version:** 1.0
**Status:** Production Ready
