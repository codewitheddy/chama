# Investment Categories Management Guide

## Overview

Admins can now create custom **Investment Categories** to organize and group investment types. Categories provide better structure and customization for your specific group's needs.

Instead of fixed categories like "Real Estate" or "Stocks", you can create your own categories with custom names, icons, and colors!

---

## How It Works

**Hierarchy:**
```
Investment Categories (Admin-created templates)
    ↓
Investment Types (Admin-created from categories)
    ↓
Investments (Treasurer records actual investments)
```

**Example:**
```
📦 Category: Real Estate (blue color, building icon)
    ├─ Type: Land - Residential Plot
    ├─ Type: House - Commercial Property
    └─ Type: Office Building

💰 Category: Banks (green color, bank icon)
    ├─ Type: Fixed Deposit - KCB
    ├─ Type: Fixed Deposit - Equity
    └─ Type: Savings Account - High Yield
```

---

## Accessing Categories

### Option 1: From Investment Types Page
1. Go to **Investments** → **Investment Types** button
2. Click the **"Investment Types"** button in the header
3. Click **"Add Category"** link on the types page

### Option 2: Direct URL
```
http://localhost:8000/investments/categories/
```

### Option 3: From Investments Dashboard
1. Navigate to **Investments**
2. New button **"Investment Categories"** will appear (once you create categories)

---

## Creating a Category

### Step 1: Go to Categories Page
- Click **Investments** → Find categories management
- Or visit `/investments/categories/`

### Step 2: Click "Add Category"

### Step 3: Fill the Form

**Left Panel - Basic Information:**

| Field | Example | Description |
|-------|---------|-------------|
| **Name** | Real Estate | Unique category name |
| **Description** | Land plots, houses, buildings | What this category includes |
| **Display Order** | 1 | Lower = appears first (optional) |
| **Active** | ✓ Checked | Make available for use |

**Right Panel - Display Settings:**

| Field | Example | Description |
|-------|---------|-------------|
| **Icon** | bi-building | Bootstrap icon class |
| **Color** | #FF6B6B | Hex color code |

### Step 4: Choose Icon

Common icons for categories:

```
🏢 bi-building              Real Estate
📊 bi-graph-up              Stocks/Shares
🏦 bi-bank                  Banks/Financial
💰 bi-coin                  Money/Currency
💼 bi-briefcase             Business
📚 bi-stack                 Assets/Portfolio
% bi-percent                Returns/Dividends
📈 bi-trending-up           Growth
💎 bi-gem                   Precious Assets
🤝 bi-people               Cooperatives
```

[View All Bootstrap Icons →](https://icons.getbootstrap.com/)

### Step 5: Choose Color

Click the color picker to select a custom color for your category. This color appears:
- In category cards
- Next to category names
- In investment type listings

### Step 6: Save

Click "Save Category" - your new category is ready to use!

---

## Using Categories for Investment Types

Once you create categories, they appear when creating investment types:

### Creating an Investment Type:
1. Go to **Investments** → **Investment Types** → **Add Type**
2. **Category** dropdown now shows your custom categories
3. Select the category your type belongs to
4. Fill other fields and save

### Example Workflow:

**Category Created:**
- Name: Real Estate
- Icon: bi-building
- Color: #FF6B6B

**Investment Type Created:**
- Name: Land - Residential Plot
- Category: Real Estate (automatically linked)
- Return Rate: 5.00%

**Treasure Records Investment:**
- Selects "Land - Residential Plot" type
- System knows it's in "Real Estate" category
- Uses the category icon and color in displays

---

## Managing Categories

### View All Categories
```
/investments/categories/
```
Shows a grid of all categories with:
- Category name and icon
- Number of investment types
- Active/Inactive status
- Edit and Delete buttons

### Edit a Category
1. Go to Categories list
2. Find the category
3. Click **Edit** button
4. Update any fields
5. Click "Save Category"

**You can update:**
- Name
- Description
- Icon
- Color
- Display order
- Active status

### Delete a Category
1. Go to Categories list
2. Find the category
3. Click **Delete** button
4. Enter password and reason
5. Confirm deletion

**Notes on Deletion:**
- Can only delete empty categories
- If types use this category, mark as "Inactive" instead
- Existing types won't be affected if you just deactivate

---

## Predefined Categories

Here are example categories most Chama groups use:

### 1. Real Estate
```
Name: Real Estate
Icon: bi-building
Color: #FF6B6B (Red)
Description: Land plots, houses, property
```

### 2. Stocks & Shares
```
Name: Stocks & Shares
Icon: bi-graph-up
Color: #4ECDC4 (Teal)
Description: Company shares and equities
```

### 3. Banks & Fixed Deposits
```
Name: Banks & Fixed Deposits
Icon: bi-bank
Color: #2563EB (Blue)
Description: Bank accounts and fixed deposits
```

### 4. Mutual Funds
```
Name: Mutual Funds
Icon: bi-layers
Color: #7C3AED (Purple)
Description: Investment fund products
```

### 5. Business Ventures
```
Name: Business Ventures
Icon: bi-briefcase
Color: #F59E0B (Amber)
Description: Business partnerships and ventures
```

### 6. Government Securities
```
Name: Government Securities
Icon: bi-percent
Color: #10B981 (Green)
Description: T-Bills, Treasury bonds, government papers
```

---

## Display Order

Control the order categories appear in dropdowns:

```
Display Order | Category
0             | Real Estate (appears first)
1             | Banks & Fixed Deposits
2             | Stocks & Shares
3             | Business Ventures
(higher numbers appear later)
```

Lower numbers = earlier in dropdown

---

## Active vs Inactive

### Active Categories
- ✓ Appear in dropdowns for investment types
- ✓ Can create new types with them
- ✓ Used for new investments

### Inactive Categories
- ✗ Don't appear in new dropdowns
- ✗ Existing types still work
- ✓ Keep history without cluttering UI

**Best Practice:** Mark old categories as "Inactive" instead of deleting them

---

## Complete Setup Example

### Step 1: Create Categories
```
1. Real Estate (red, building icon, order 0)
2. Banks (blue, bank icon, order 1)
3. Stocks (teal, graph icon, order 2)
4. Business (amber, briefcase icon, order 3)
```

### Step 2: Create Investment Types
```
Category: Real Estate
  - Land - Residential Plot (5% return)
  - House - Commercial Property (6% return)

Category: Banks
  - Fixed Deposit - KCB (8.5% return)
  - Fixed Deposit - Equity (8% return)

Category: Stocks
  - Shares - NSEG (10% return)
  - Shares - Safaricom (12% return)
```

### Step 3: Record Investments
```
Treasurer selects:
  Investment Type: Land - Residential Plot
  Amount: 500,000 KES
  (Category automatically: Real Estate)
```

---

## API/Technical Details

### Database Structure
```
InvestmentCategory
├─ id (PK)
├─ name (unique)
├─ description
├─ icon (e.g., "bi-building")
├─ color_code (e.g., "#FF6B6B")
├─ display_order
├─ is_active
└─ timestamps

InvestmentType
├─ id (PK)
├─ name
├─ category_id (FK → InvestmentCategory)
├─ expected_return_rate
└─ timestamps
```

### URL Endpoints
| Action | URL |
|--------|-----|
| List | `/investments/categories/` |
| Create | `/investments/categories/add/` |
| Edit | `/investments/categories/<id>/edit/` |
| Delete | `/investments/categories/<id>/delete/` |

---

## Best Practices

✅ **DO:**
- Create 4-6 main categories for typical groups
- Use clear, descriptive names
- Choose appropriate icons for visual consistency
- Use display order to organize logically
- Deactivate instead of deleting old categories
- Use colors to distinguish category types

❌ **DON'T:**
- Create too many categories (>10)
- Use vague names like "Investment 1"
- Duplicate category purposes
- Delete categories with active types
- Change color codes frequently (confuses users)

---

## Troubleshooting

### Can't see category dropdown when creating types
- Ensure categories are marked "Active"
- Refresh the page
- Create at least one category first

### Old categories still appearing
- Check if they're marked "Inactive"
- Only inactive categories are hidden
- Existing types using them still work

### Can't delete a category
- It likely has investment types
- Mark as "Inactive" instead
- Existing types won't be affected

### Color picker not showing
- Use modern browser (Chrome, Firefox, Safari, Edge)
- Try entering hex code directly (e.g., #FF6B6B)

---

## Integration with Investments

Once categories are set up:

**For Admins:**
1. Categories Management - `/investments/categories/`
2. Investment Types Management - `/investments/types/`

**For Treasurers:**
1. Record Investments - `/investments/add/`
   - Category appears in Investment Type dropdown
   - Icons and colors show automatically

**For All Users:**
1. View Investments - `/investments/`
   - Investments grouped by category
   - Visual consistency via colors and icons

---

## Examples by Group Type

### Merry-Go-Round
```
Categories:
- Group Contributions (savings)
- Emergency Funds
- Special Projects
```

### Sacco Group
```
Categories:
- Member Loans
- Business Ventures
- Fixed Deposits
- Government Securities
```

### Investment Club
```
Categories:
- Real Estate Holdings
- Stock Portfolio
- Bonds & Fixed Income
- Mutual Funds
- Business Investments
```

---

## Support

**Questions about Categories?**
1. Check this guide
2. See Django Admin for detailed records
3. Contact your administrator

---

**Ready to create your first category?** 🚀

Start by going to **Investments** → **Investment Categories** → **Add Category**

Happy organizing! 🎉
