# 📜 Finance Wise TBM — Version History & Changelog

This document tracks the evolution of **Finance Wise TBM**, detailing every version release, new architectural features, financial invariants, and database schema updates.

---

## 🚀 Version 1.1.0 — Dedicated Welfare Bank Accounts & Smart Upgrades
**Release Date:** October 2026  
**Type:** Minor Feature Release & Packaging Upgrade  
**Installer:** `FinanceWiseTBM_Setup_v1.1.0.exe`

### 1. Dedicated Welfare Bank Account Segregation 🏦
- **Problem Solved:** Previously, all bank accounts were treated as general funds. Welfare benevolent reserves (collected from monthly member welfare fees) were mixed with general lending capital.
- **Solution:**
  - Added `fund_type` field to `BankAccount` model with choices:
    - `general` (General Chama Operations & Lending)
    - `welfare` (Dedicated Welfare Emergency & Benevolent Fund)
    - `registration` (Registration Fees Fund)
  - Applied migration `bank_accounts.0003_bankaccount_fund_type`.
  - Configured **I & M Bank Current Account** (`0360 4658 1361 51`) with balance KES 14,800.00 as the dedicated Welfare Account.
  - Enforced financial invariant: Loan disbursements (`loans/forms.py`) and general expense payouts are strictly filtered to `fund_type='general'`, guaranteeing Welfare funds cannot be drawn for loan issuances.
  - Segregated `money_movement/services.py` and `utils/financials.py` so General Chama and Welfare funds calculate independently with zero variance.

### 2. Welfare Contributions Page Enhancements 📊
- Redesigned the main Welfare Contributions page (`/welfare/contributions/`):
  - **5-Card Top KPI Metric Row**: Live counts and balances for Total Collected, Total Disbursed, Welfare Balance, Welfare in Bank, and Open Events.
  - **Dedicated Welfare Bank Banner**: Displays the segregated bank account details, account number, live bank balance, and real-time reconciliation badges (`Segregated from Group Lending` & `100% Banked & Reconciled`).
  - **1-Click Bank Deposit Action**: Embedded modal enabling instant cash banking deposits directly into the Welfare bank account with preset increment chips (`+500`, `+1,000`, `+2,000`, `+5,000`, `+10,000`).

### 3. Desktop Installer Data Isolation & Zero-Data Guarantee 🛡️
- **Installer Sanitization:**
  - Hardened `desktop.spec`, `build.bat`, and `compile_installer.ps1` to strictly exclude all `*.sqlite3`, `*.db`, `license.key`, and uploaded media files (`media/*`).
  - Added Inno Setup compile filter:
    `Excludes: "*.sqlite3,*.db,*.sqlite,*.log,*.bak,*.tmp,license.key,media\*,backups\*"`
- **Runtime User Data Isolation (`desktop.py`):**
  - Application data lives in `%APPDATA%\FinanceWiseTBM\` (`db.sqlite3`, `media/`, `license.key`).
  - Installer updates replace application code in `C:\Program Files` without touching `%APPDATA%`.
  - Automatic migration engine: On update, `call_command('migrate')` executes on the user's existing database, safely applying schema changes while preserving all records.

### 4. Interactive Installer: Safe Update vs. Clean Reinstall 🔄
- The Inno Setup wizard automatically detects any previous installation or database:
  - **Update existing installation (Recommended):** Keeps all member records, loan balances, welfare funds, and transactions intact.
  - **Clean fresh install:** Allows users to purposefully wipe existing data and start with a blank database. A secondary confirmation prompt protects against accidental deletion.

---

## 📦 Version 1.0.0 — Initial Production Release
**Release Date:** September 2026  
**Type:** Major Release  
**Installer:** `FinanceWiseTBM_Setup_v1.0.0.exe`

- **Member Management**: Comprehensive member directory, profiles, next of kin, registration fee tracking, and member exits.
- **Dynamic Loan Engine**: Support for flat rate and reducing balance loan products, automated repayment schedules, loan restructuring, emergency 0% interest products, and guarantor exposure tracking.
- **Welfare Fund System**: Monthly rate configurations, welfare contributions, benevolent event lifecycles, and aid disbursements.
- **Double-Entry Financial Accounting**: Automated cash book, bank ledger, meeting summaries, and funds position tracking.
- **Investments & Asset Register**: Real-time asset valuation, dividend recording, and capital growth metrics.
- **System Administration & Security**: Granular role-based access control (Admin, Treasurer, Read-Only), audit logging, and automated database backups with Recycle Bin recovery.
- **Desktop Packaging**: Offline launcher using embedded Chromium (`pywebview`) and fallback system browser modes.

---

## 📌 Summary of Release Evolution

| Version | Release Date | Key Focus | Database Schema Status |
|---|---|---|---|
| **v1.0.0** | Sep 2026 | Initial full-featured release | Initial baseline schemas |
| **v1.1.0** | Oct 2026 | Welfare bank segregation, zero-data updates, interactive installer | `bank_accounts.0003` migration |
