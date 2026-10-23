# Admin Quick Reference: Registration Fee Toggle

**Print or bookmark this quick reference for easy access**

---

## The Toggle - What It Does

### When Adding a New Member

You'll see this checkbox:

```
☐ Has the member paid the registration fee?
```

### Two Choices:

| Choice | Action | What Happens |
|--------|--------|--------------|
| ☑ Check | Member paid today | Fee automatically recorded as paid |
| ☐ Don't check | Member pays later | Fee set to 0, record payment when ready |

---

## Quick Decision Tree

```
New member is joining...

    Does member have cash RIGHT NOW?
    │
    ├─→ YES, paying today
    │   └─→ ☑ CHECK the box
    │       └─→ Fee auto-applied
    │
    └─→ NO, will pay later
        └─→ ☐ LEAVE UNCHECKED
            └─→ Record payment later
```

---

## Step-by-Step: Immediate Payment (☑ Checked)

**Member has cash and is paying today:**

1. Navigate: **Members > Add Member**
2. Fill in member details
3. **CHECK** ☑ "Has member paid registration fee?"
4. Click "Save Member"
5. ✅ Done - Fee is recorded as paid

**Time needed:** 2 minutes

---

## Step-by-Step: Deferred Payment (☐ Unchecked)

**Member will pay later:**

### Step A: Add Member (Today)
1. Navigate: **Members > Add Member**
2. Fill in member details
3. **LEAVE UNCHECKED** ☐ "Has member paid registration fee?"
4. Click "Save Member"
5. Member is added with fee = 0 owed

### Step B: Record Payment (When Member Pays)
1. Navigate: **Members > Registration Fee Payments**
2. Click **"Add Registration Fee Payment"**
3. Fill in:
   - Member: [Select member name]
   - Amount: [Type amount, e.g., 2000]
   - Payment Date: [Today's date]
   - Payment Method: [Cash / M-Pesa / Bank / Cheque]
   - Receipt Number: [Optional, e.g., RC-2026-001]
   - Notes: [Optional]
4. Click "Save Payment"
5. ✅ Done - Payment recorded and member updated

**Time needed:** 3-4 minutes (split across days)

---

## Payment Methods

When recording a deferred payment, choose the appropriate method:

- **Cash** - Handed to you in person
- **M-Pesa** - Digital payment, enter confirmation code
- **Bank Transfer** - From member's bank account
- **Cheque** - Received from member

---

## Common Scenarios

### Scenario 1: John Pays at Signup
```
1. Add John
2. CHECK the box
3. Save
Result: John's fee = 2,000 KES (recorded immediately)
```

### Scenario 2: Mary Pays Next Week
```
Day 1 (Today):
1. Add Mary
2. LEAVE UNCHECKED
3. Save
Result: Mary's fee = 0 KES (owed)

Day 8 (When Mary pays):
1. Go to Registration Fee Payments
2. Add payment: 2,000 KES
Result: Mary's fee updated to 2,000 KES (paid)
```

### Scenario 3: Peter Pays in Two Parts
```
Day 1 (Today):
1. Add Peter
2. LEAVE UNCHECKED
3. Save
Result: Peter's fee = 0 KES (owes 2,000)

Day 5 (Part payment):
1. Go to Registration Fee Payments
2. Add payment: 1,000 KES
Result: Peter's fee = 1,000 KES (owes 1,000 more)

Day 12 (Final payment):
1. Go to Registration Fee Payments
2. Add payment: 1,000 KES
Result: Peter's fee = 2,000 KES (fully paid) ✓
```

---

## Keyboard Shortcuts

None for this feature - just use your mouse/touchpad to:
- Click the checkbox ☑/☐
- Fill in the form fields
- Click Save

---

## Troubleshooting

### Q: Did I check the box correctly?
**A:** Look for the checkmark: ☑ = checked, ☐ = unchecked

### Q: The fee didn't apply - what now?
**A:** 
- If unchecked: Go to Registration Fee Payments, add payment manually
- If should be checked: Edit the member and manually adjust if needed

### Q: How do I know if a member paid?
**A:** Check the member's detail page:
- Scroll down to "Registration Fee" section
- Shows total amount paid
- Shows payment history (if any)

### Q: Member paid but I forgot to record it
**A:** No problem:
1. Go to Registration Fee Payments
2. Click "Add Registration Fee Payment"
3. Enter the date they paid
4. System updates member record

---

## Quick Stats

**What you need to know:**

- ☑ Default current fee rate: **2,000 KES** (or whatever is set)
- ☐ Unchecked = 0 KES (deferred)
- Payment methods: Cash, M-Pesa, Bank, Cheque
- Can split into multiple payments ✓
- All payments tracked and audited

---

## Key Points to Remember

1. **Check box** = Member paid today
2. **Leave blank** = Member will pay later
3. **Recording payments** = Go to Registration Fee Payments section
4. **Each payment is recorded** = Full audit trail maintained
5. **No database changes** = Everything integrates smoothly

---

## Getting Help

If you're unsure:

1. **Quick questions?** See this card
2. **Need examples?** Read `MEMBER_REG_FEE_QUICK_GUIDE.md`
3. **Want details?** Read `MEMBER_REGISTRATION_FEE_IMPROVEMENT.md`
4. **Confused about flow?** Read `FEATURE_CHANGELOG.md`

---

## Access Levels

This feature requires:
- ✅ Treasurer role (to add members)
- ✅ Treasurer role (to record fee payments)
- ❌ Regular members: Cannot access

---

## Pro Tips

1. **Batch check:** If 80% of new members pay at signup, check the box
2. **Document collection:** Keep receipts organized in a folder
3. **Follow-ups:** Use the unpaid list to follow up with members
4. **Recording time:** Batch record multiple payments at end of week
5. **Double-check:** Verify member name in dropdown before saving

---

## One-Minute Overview

```
Adding a member who will pay registration fee:

IMMEDIATELY:
☑ Check box → Save → Done ✅

LATER:
☐ Don't check → Save → (Later) Add payment record → Done ✅
```

---

## Checklist

When adding a member, before clicking "Save Member":

- [ ] Name entered
- [ ] Phone entered (and unique)
- [ ] Date joined set (or left as today)
- [ ] ☑ or ☐ Registration fee toggle chosen
- [ ] Photo/ID uploaded (optional but good)
- [ ] Next of kin info added (if available)

✅ Ready to save!

---

## Contact

For technical issues or feature requests:
- **System Administrator** - For access/permission issues
- **Treasurer Lead** - For fee rate questions
- **Database Manager** - For payment history/audit issues

---

**Last Updated:** August 15, 2026  
**Feature Version:** 1.0  
**Status:** Active & Tested

This is a quick reference. For detailed instructions, see the full documentation files.
