# Registration Fee Toggle - Quick User Guide

## The Problem

Previously, when adding a new member:
- Admin was forced to immediately set the registration fee (or it defaulted to current rate)
- No flexibility for members who would pay later
- Required separate workflow to adjust fee after member creation

## The Solution

A simple **registration fee toggle** on the member creation form.

---

## Using the Feature

### Step 1: Open Add Member Form
Navigate to **Members > Add Member**

### Step 2: Fill in Member Details
- Name
- Phone
- Date Joined
- Photo (optional)
- ID Document (optional)
- Next of Kin info (optional)

### Step 3: Choose Registration Fee Option

**Option A: Member Has Paid Fee Now**
```
☑ Has the member paid the registration fee?
```
- ✓ Checked
- Fee automatically set to current rate (e.g., 2,000 KES)
- Member is fully onboarded

**Option B: Member Will Pay Fee Later**
```
☐ Has the member paid the registration fee?
```
- ✗ Unchecked
- Fee set to 0
- Member is added but marked as owing fee
- You'll add payment when they pay

### Step 4: Save Member
Click "Save Member"

---

## Recording Deferred Payment

If you chose "Will pay later", here's how to record payment when member pays:

### Step 1: Go to Registration Fee Payments
Navigate to **Members > Registration Fee Payments**

### Step 2: Click "Add Registration Fee Payment"

### Step 3: Fill in Payment Details
```
Member:           [John Doe]
Amount:           2000.00 KES
Payment Date:     [15/08/2026]
Payment Method:   [M-Pesa / Cash / Bank Transfer]
Receipt Number:   [RC-2026-0145] (optional)
Notes:            (optional)
```

### Step 4: Save Payment
Click "Save Payment"

System automatically updates member's registration fee status.

---

## Example Scenarios

### Scenario 1: New Member, Cash Payment Today
1. Admin adds member "Alice Johnson"
2. **Checks** "Has the member paid registration fee?"
3. Saves
4. System sets fee to 2,000 KES
5. Alice is fully onboarded ✅

### Scenario 2: New Member, Payment Next Week
1. Admin adds member "Bob Kipchoge"
2. **Leaves unchecked** "Has the member paid registration fee?"
3. Saves
4. System sets fee to 0
5. Bob is added but owes 2,000 KES
6. Next week when Bob pays via M-Pesa:
   - Admin goes to Registration Fee Payments
   - Adds Bob's 2,000 KES payment
   - System updates Bob's record ✅

### Scenario 3: Member Paying in Installments
1. Admin adds member "Carol Mwangi"
2. **Leaves unchecked** "Has the member paid registration fee?"
3. Saves
4. Carol owes 2,000 KES
5. Carol pays 1,000 KES on Day 1:
   - Add payment: 1,000 KES
6. Carol pays remaining 1,000 KES on Day 7:
   - Add payment: 1,000 KES
7. Total paid: 2,000 KES ✅

---

## Why This Matters

### Before
- Every new member had fee applied immediately
- No flexibility for real-world payment scenarios
- Difficult to track who owes fees vs who paid

### After
- **Flexible onboarding:** Choose payment timing
- **Better tracking:** Clear audit trail of who paid when
- **Real-world friendly:** Accommodates delayed payments
- **Cleaner workflow:** No need to manually adjust fees

---

## Common Questions

**Q: What if I accidentally checked the box?**
A: The member's fee is already recorded. You can:
   - Edit the member and change `registration_fee_paid` if needed
   - Or record a "refund" payment with negative amount
   - Contact admin if unsure

**Q: Can I see which members haven't paid fees?**
A: Yes! Check:
   - Dashboard: Members with fee = 0
   - Reports > Registration Fee Payment Report
   - Member detail page: Shows registration fee status

**Q: What if the registration fee rate changes?**
A: When you add a member:
   - If toggle is checked: Uses the CURRENT rate at signup
   - If toggle is unchecked: Set to 0 (no rate applied)
   - Later when fee is paid: Admin manually enters amount (flexible)

**Q: Can multiple payments count toward one fee?**
A: Yes! Each payment is recorded separately:
   - Payment 1: 1,000 KES on Day 1
   - Payment 2: 1,000 KES on Day 7
   - Both count toward the 2,000 KES total

---

## Visual Flow

```
┌─────────────────────────────────────┐
│  Add New Member                     │
└─────────────────────────────────────┘
            ↓
┌─────────────────────────────────────┐
│  Fill Member Details                │
│  - Name, Phone, Photo, etc.         │
└─────────────────────────────────────┘
            ↓
      Choose One:
      
  ☑ Fee Paid Now              ☐ Fee Paid Later
       ↓                            ↓
   Fee = 2,000 KES            Fee = 0 KES
   Fully Onboarded            Owes Payment
       ↓                            ↓
   DONE ✓                    (Later: Add Payment)
                                    ↓
                             Fee Updated ✓
```

---

## Tips

1. **For Groups With Upfront Payment:**
   - Most members will check the box (faster process)

2. **For Groups Allowing Deferred Payment:**
   - Uncheck for all members initially
   - Track pending payments in Registration Fee Payment list
   - Add payment records as members pay

3. **For Mixed Payment Scenarios:**
   - Some members pay upfront: ☑
   - Some pay later: ☐ then add payment record later

---

## Need Help?

If something doesn't look right:
1. Check the member's detail page to see registration fee status
2. Go to Registration Fee Payments to see all payment history
3. Contact admin for access to fee rate settings

**Key Point:** The toggle is just a convenience. You can always manually adjust fees and add payment records as needed.
