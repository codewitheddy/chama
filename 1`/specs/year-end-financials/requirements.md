# Requirements Document

## Introduction

The DC Welfare Group chama (table banking) system needs two related financial features:

1. **Year-End Withdrawal** — At the close of each financial year the group withdraws its accumulated savings pool, distributes the interest earned among members, and resets for the new year. This event must be recorded as an auditable transaction that reduces the available fund balance. The interest distribution must be broken down per member so each individual's share is recorded.

2. **Year-End Closure Process** — Closing a financial year involves more than recording a withdrawal. The group starts fresh for the new year: new contributions and registrations begin, and members either continue (roll over) or exit. Exiting members receive their share and are no longer active contributors in the new year, though their historical records are preserved.

3. **Loan Fund Availability Enforcement** — The treasurer balance (available lending fund) is currently displayed on the dashboard but is not enforced when a new loan is created or rolled over. The system must prevent a loan from being approved or rolled over when the requested amount exceeds the available fund balance.

---

## Glossary

- **System**: The DC Welfare Group chama management Django application.
- **Treasurer**: An authenticated user with the Treasurer role who manages group finances.
- **Member**: A registered participant of the chama group.
- **Contribution**: A monthly cash contribution recorded against a Member for a specific month and year (`contributions.Contribution`).
- **Registration_Fee**: A one-time fee stored on the `Member` model (`Member.registration_fee`).
- **Loan**: A loan issued to a Member from the group fund (`loans.Loan`). Status is `active`, `late`, or `cleared`.
- **Rollover**: The act of converting an existing Loan's outstanding balance into a new principal via `Loan.do_rollover()`, recorded as a `LoanRollover` entry.
- **Payment**: A repayment made against a Loan (`payments.Payment`).
- **Penalty**: A fine levied on a Member; `paid=True` means the cash has been collected (`penalties.Penalty`).
- **Interest_Collected**: Per loan, the lesser of `amount_paid` and `(total_payable − loan_amount)` — i.e., the interest portion of repayments already received.
- **Total_Income**: `SUM(Contributions) + SUM(Registration_Fees) + SUM(Interest_Collected) + SUM(Penalties where paid=True)`.
- **Principal_Outstanding**: `SUM(total_payable − amount_paid)` for all Loans with status `active` or `late`.
- **Year_End_Withdrawal**: A recorded event capturing the group's annual savings distribution — the total amount withdrawn from the fund and the total interest shared out to members.
- **MemberInterestShare**: A record linked to a Year_End_Withdrawal that stores the individual interest amount allocated to a specific Member for that year-end event.
- **Total_Year_End_Withdrawals**: `SUM(amount_withdrawn)` across all `YearEndWithdrawal` records.
- **Available_Fund_Balance**: `Total_Income − Principal_Outstanding − Total_Year_End_Withdrawals`. This is the amount the group can currently lend out.
- **Financial_Year**: A calendar year (e.g., 2024) used to scope a Year_End_Withdrawal event.
- **Year_End_Member_Status**: A record that marks whether a Member is continuing or exiting at the close of a Financial_Year, linked to a Year_End_Withdrawal.
- **Continuing_Member**: A Member marked as continuing at year-end who rolls over into the new financial year as an active contributor.
- **Exiting_Member**: A Member marked as exiting at year-end who receives their share and is no longer an active contributor in the new financial year.

---

## Requirements

### Requirement 1: Record Year-End Withdrawal Events

**User Story:** As a Treasurer, I want to record a year-end withdrawal event, so that the group's annual savings distribution is captured as an auditable transaction in the system.

#### Acceptance Criteria

1. THE System SHALL provide a form that allows the Treasurer to create a Year_End_Withdrawal record containing: `financial_year` (integer), `amount_withdrawn` (decimal ≥ 0.01 KES), `interest_shared` (decimal ≥ 0.00 KES), `date` (calendar date), `notes` (optional free text), and `recorded_by` (the authenticated Treasurer user).
2. WHEN the Treasurer submits a valid Year_End_Withdrawal form, THE System SHALL persist the record and display a success confirmation.
3. IF the Treasurer submits a Year_End_Withdrawal form with `amount_withdrawn` less than or equal to zero, THEN THE System SHALL reject the submission and display a validation error.
4. IF the Treasurer submits a Year_End_Withdrawal form with `interest_shared` greater than `amount_withdrawn`, THEN THE System SHALL reject the submission and display a validation error stating that interest shared cannot exceed the total amount withdrawn.
5. IF the Treasurer submits a Year_End_Withdrawal for a `financial_year` that already has a Year_End_Withdrawal record, THEN THE System SHALL reject the submission and display an error indicating a withdrawal for that year already exists.
6. THE System SHALL record the `recorded_by` field automatically from the authenticated session; the Treasurer SHALL NOT be able to set it manually.

---

### Requirement 2: Per-Member Interest Share Breakdown

**User Story:** As a Treasurer, I want to record how much interest each individual member received at year-end, so that every member's share is traceable and auditable.

#### Acceptance Criteria

1. THE System SHALL provide a MemberInterestShare model that stores: a foreign key to the associated Year_End_Withdrawal, a foreign key to the Member, and the `amount` (decimal ≥ 0.00 KES) allocated to that Member for that year-end event.
2. WHEN the Treasurer creates a Year_End_Withdrawal, THE System SHALL allow the Treasurer to enter a MemberInterestShare amount for each Member as part of the same submission flow.
3. IF the sum of all MemberInterestShare `amount` values for a Year_End_Withdrawal exceeds the `interest_shared` value of that Year_End_Withdrawal, THEN THE System SHALL reject the submission and display a validation error stating the per-member total cannot exceed the total interest shared.
4. THE System SHALL display the per-member interest breakdown on the Year_End_Withdrawal detail view, listing each Member's name alongside their allocated interest amount.
5. WHEN a Year_End_Withdrawal record is deleted, THE System SHALL cascade-delete all associated MemberInterestShare records.

---

### Requirement 3: Year-End Closure — Member Continuation and Exit

**User Story:** As a Treasurer, I want to record which members are continuing into the new year and which are exiting at year-end, so that the group can start the new financial year with an accurate active membership list.

#### Acceptance Criteria

1. THE System SHALL provide a Year_End_Member_Status model that stores: a foreign key to the associated Year_End_Withdrawal, a foreign key to the Member, and a `status` field with values `continuing` or `exiting`.
2. WHEN the Treasurer creates a Year_End_Withdrawal, THE System SHALL allow the Treasurer to assign a Year_End_Member_Status of `continuing` or `exiting` for each Member as part of the year-end closure flow.
3. WHEN a Member is marked as `exiting` for a Financial_Year, THE System SHALL set that Member's `is_active` flag to `False`, preventing the Member from appearing as an active contributor in subsequent contribution and loan workflows.
4. WHEN a Member is marked as `continuing` for a Financial_Year, THE System SHALL retain that Member's `is_active` flag as `True` so the Member rolls over into the new year without interruption.
5. THE System SHALL preserve all historical Contribution, Loan, Payment, and Penalty records for Exiting_Members; only the `is_active` flag SHALL be changed.
6. THE System SHALL display the member status breakdown (continuing vs. exiting) on the Year_End_Withdrawal detail view.
7. IF a Member has an outstanding Loan (status `active` or `late`) at the time they are marked as `exiting`, THEN THE System SHALL reject the exit and display an error stating the Member must clear all pending loans before exiting the group.

---

### Requirement 4: Year-End Withdrawal Reduces Available Fund Balance

**User Story:** As a Treasurer, I want year-end withdrawals to reduce the available fund balance, so that the treasurer balance accurately reflects how much money remains in the lending pool after distributions.

#### Acceptance Criteria

1. THE System SHALL compute Available_Fund_Balance as `Total_Income − Principal_Outstanding − Total_Year_End_Withdrawals`.
2. WHEN a Year_End_Withdrawal record is saved, THE System SHALL include its `amount_withdrawn` in `Total_Year_End_Withdrawals` immediately, so that the Available_Fund_Balance displayed on the dashboard reflects the withdrawal without requiring a page reload after the next request.
3. THE System SHALL display the Available_Fund_Balance on the main dashboard, replacing the existing `treasurer_balance` value with the updated formula.
4. WHILE `Total_Year_End_Withdrawals` is zero, THE System SHALL compute Available_Fund_Balance identically to the previous `treasurer_balance` formula, preserving backward compatibility.

---

### Requirement 5: List and View Year-End Withdrawal History

**User Story:** As a Treasurer, I want to view a history of all year-end withdrawals, so that I can audit past distributions and verify the fund balance at any point.

#### Acceptance Criteria

1. THE System SHALL provide a page listing all Year_End_Withdrawal records ordered by `financial_year` descending, showing: `financial_year`, `date`, `amount_withdrawn`, `interest_shared`, `notes`, and `recorded_by`.
2. WHEN no Year_End_Withdrawal records exist, THE System SHALL display an empty-state message indicating no withdrawals have been recorded.
3. THE System SHALL restrict access to the Year_End_Withdrawal list and creation pages to authenticated users with the Treasurer role.
4. THE System SHALL provide a detail view for each Year_End_Withdrawal that shows the per-member interest breakdown (MemberInterestShare records) and the member continuation/exit status (Year_End_Member_Status records) for that event.

---

### Requirement 6: Enforce Loan Fund Availability at Loan Creation

**User Story:** As a Treasurer, I want the system to prevent a loan from being approved when the requested amount exceeds the available fund balance, so that the group never lends out more money than it has.

#### Acceptance Criteria

1. WHEN the Treasurer submits a new Loan creation form, THE System SHALL compute the Available_Fund_Balance at that moment and compare it to the submitted `loan_amount`.
2. IF the submitted `loan_amount` exceeds the Available_Fund_Balance at the time of submission, THEN THE System SHALL reject the loan and display an error message that includes the current Available_Fund_Balance in KES.
3. WHEN the submitted `loan_amount` is less than or equal to the Available_Fund_Balance, THE System SHALL proceed with normal loan validation and creation.
4. THE System SHALL display the current Available_Fund_Balance on the loan creation form so that the Treasurer can see how much is available before submitting.
5. IF the Available_Fund_Balance is zero or negative at the time of loan creation, THEN THE System SHALL reject any loan submission and display a message indicating no funds are currently available to lend.

---

### Requirement 7: Enforce Loan Fund Availability at Loan Rollover

**User Story:** As a Treasurer, I want the system to prevent a loan rollover when the new principal (the outstanding balance) exceeds the available fund balance, so that rollovers cannot silently over-commit the group's funds.

#### Acceptance Criteria

1. WHEN the Treasurer initiates a Rollover for an existing Loan, THE System SHALL compute the Available_Fund_Balance at that moment and compare it to the outstanding balance that will become the new principal.
2. IF the outstanding balance of the Loan being rolled over exceeds the Available_Fund_Balance at the time of the rollover request, THEN THE System SHALL reject the rollover and display an error message that includes the current Available_Fund_Balance in KES.
3. WHEN the outstanding balance is less than or equal to the Available_Fund_Balance, THE System SHALL proceed with the rollover using the existing `Loan.do_rollover()` logic.
4. THE System SHALL display the current Available_Fund_Balance on the rollover confirmation page or form so that the Treasurer can see how much is available before confirming.
5. IF the Available_Fund_Balance is zero or negative at the time of a rollover request, THEN THE System SHALL reject the rollover and display a message indicating no funds are currently available.

---

### Requirement 8: Available Fund Balance Consistency

**User Story:** As a Treasurer, I want the available fund balance to be consistent across the dashboard, loan creation form, and rollover flow, so that I always see the same figure regardless of where I look.

#### Acceptance Criteria

1. THE System SHALL compute Available_Fund_Balance using a single shared function or utility so that the dashboard, loan creation form, rollover flow, and any future views all use the identical formula.
2. WHEN a new Loan is created, THE System SHALL reflect the reduced Available_Fund_Balance on the dashboard on the next page load.
3. WHEN a Payment is recorded against a Loan, THE System SHALL reflect the increased Available_Fund_Balance (due to reduced Principal_Outstanding) on the dashboard on the next page load.
4. WHEN a Year_End_Withdrawal is recorded, THE System SHALL reflect the reduced Available_Fund_Balance on the dashboard on the next page load.
5. WHEN a Loan Rollover is completed, THE System SHALL reflect the updated Available_Fund_Balance on the dashboard on the next page load.
