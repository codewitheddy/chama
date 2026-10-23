# Investment Types Management Guide

## Overview

You can now create, edit, and delete Investment Types directly from the Investments module without needing to go to the admin panel!

## How to Access Investment Types Management

### Option 1: From Investments Dashboard
1. Go to **Investments** (from sidebar)
2. Click the **"Investment Types"** button (info button)
3. You're now in the Investment Types management page

### Option 2: Direct URL
```
http://localhost:8000/investments/types/
```

---

## Creating an Investment Type

### Step 1: Go to Investment Types Page
- Click **Investments** → **Investment Types** button
- Or visit `/investments/types/`

### Step 2: Click "Add Investment Type" Button

### Step 3: Fill in the Form

**Fields to Complete:**

| Field | Example | Description |
|-------|---------|-------------|
| **Type Name** | Land - Residential Plot | Name of the investment type |
| **Category** | Real Estate | Choose from dropdown (9 options) |
| **Expected Return Rate** | 8.50 | Annual return % (optional, default: 0%) |
| **Description** | Residential land plots in prime locations | Details about this type |
| **Active** | ✓ Checked | Check to make available for new investments |

### Step 4: Click "Save Investment Type"

---

## Category Options

Choose the category that best matches your investment type:

1. **Real Estate** - Land, buildings, properties
   - Example: "Land - Residential Plot"
   - Example: "House - Commercial Property"

2. **Stocks/Shares** - Company shares and equities
   - Example: "Shares - NSEG"
   - Example: "Shares - Safaricom"

3. **Bonds/T-Bills** - Government securities
   - Example: "T-Bills - 91 Day"
   - Example: "Treasury Bonds"

4. **Mutual Fund** - Investment funds
   - Example: "Mutual Fund - Equity"
   - Example: "Money Market Fund"

5. **Fixed Deposit** - Bank CDs and deposits
   - Example: "Fixed Deposit - Bank Account"
   - Example: "Certificate of Deposit"

6. **Savings Account** - Savings products
   - Example: "Savings Account - High Yield"

7. **Cooperative Society** - Cooperative shares
   - Example: "Cooperative Society - Merry Go Round"

8. **Business Venture** - Business partnerships
   - Example: "Business Venture - Poultry Farm"
   - Example: "Business - Retail Shop"

9. **Other** - Anything not listed
   - Example: "Art Collection"
   - Example: "Vintage Assets"

---

## Quick Setup Examples

### Example 1: Create Real Estate Investment Type

```
Name: Land - Residential Plot
Category: Real Estate
Expected Return: 5.00%
Description: Residential land plots for future development
Active: ✓ Yes
```

### Example 2: Create Stock Investment Type

```
Name: Shares - NSEG
Category: Stocks/Shares
Expected Return: 10.00%
Description: NSEG shares for portfolio diversification
Active: ✓ Yes
```

### Example 3: Create Fixed Deposit Investment Type

```
Name: Fixed Deposit - KCB Bank
Category: Fixed Deposit
Expected Return: 8.50%
Description: Fixed deposit account at KCB with quarterly interest
Active: ✓ Yes
```

---

## Managing Investment Types

### View All Investment Types
1. Go to **Investments** → **Investment Types**
2. See a list with:
   - Name
   - Category
   - Expected Return Rate
   - Description
   - Active/Inactive status
   - Edit and Delete buttons

### Search Investment Types
1. In the Investment Types list
2. Use the search box to find by name or description
3. Click "Search"

### Edit an Investment Type
1. Find the type in the list
2. Click the **Edit** button (pencil icon)
3. Update any fields
4. Click "Save Investment Type"

### Delete an Investment Type
1. Find the type in the list
2. Click the **Delete** button (trash icon)
3. Enter your password and reason for deletion
4. Click "Yes, Delete Type"

> **Note:** Deleting is permanent. Existing investments with this type won't be affected, but the type will no longer be available for new investments.

---

## Using Investment Types When Recording Investments

After creating investment types, they appear in the dropdown when recording a new investment:

1. Go to **Investments** → **Add Investment**
2. Click the **Investment Type** dropdown
3. Select one of your created types
4. The form auto-fills with the type details
5. Continue filling out the rest of the investment form

---

## Common Tasks

### Make an Investment Type Inactive
1. Go to **Investment Types**
2. Click **Edit** on the type
3. Uncheck the "Active" checkbox
4. Click "Save"
   
**Effect:** Type won't appear in dropdown for new investments, but existing investments remain unaffected.

### Change Expected Return Rate
1. Go to **Investment Types**
2. Click **Edit**
3. Update the "Expected Return Rate" field
4. Click "Save"

### Archive Investment Types
1. You can't delete if investments use them
2. Instead, mark as "Inactive"
3. This keeps the investment history intact

---

## Best Practices

✅ **DO:**
- Create types matching your group's actual investments
- Use clear, descriptive names
- Set realistic expected return rates
- Activate only types you actually use
- Mark obsolete types as inactive instead of deleting

❌ **DON'T:**
- Create duplicate types (e.g., "Land" and "Land - Plot")
- Use vague names (e.g., "Investment" or "Asset")
- Delete types that have active investments

---

## Troubleshooting

### Can't see "Investment Types" button
- Ensure you're logged in as Admin
- Refresh your browser (Ctrl+F5)
- Check that you're on the Investments list page

### Can't see new type in dropdown
- Make sure it's marked as "Active"
- Refresh the investment form page
- Check the spelling matches exactly

### Can't delete an investment type
- Check if it's used by existing investments
- If used, mark it "Inactive" instead
- Contact admin if you need to force delete

---

## Integration with Investment Recording

Once you create investment types, the workflow becomes:

1. **Admin**: Creates Investment Types (`/investments/types/`)
2. **Treasurer**: Uses types when recording investments (`/investments/add/`)
3. **System**: Auto-populates category and other metadata
4. **Dashboard**: Shows performance by type

---

## URL Reference

| Page | URL |
|------|-----|
| Investment Types List | `/investments/types/` |
| Add Investment Type | `/investments/types/add/` |
| Edit Investment Type | `/investments/types/<id>/edit/` |
| Delete Investment Type | `/investments/types/<id>/delete/` |
| Investments List | `/investments/` |
| Add Investment | `/investments/add/` |

---

## Support

**Questions about Investment Types?**

1. Check this guide first
2. See the Investment Module Guide for more details
3. Contact your admin for technical support

---

**Ready to create your first investment type?** 🚀

Start by going to **Investments** → **Investment Types** → **Add Investment Type**

Happy investing! 📈
