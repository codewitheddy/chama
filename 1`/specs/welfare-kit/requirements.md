# Requirements Document

## Introduction

The Welfare Kit module is a standalone Django app within the DC Welfare Group chama system. It manages a dedicated welfare fund that is financially and operationally separate from the main chama contributions. The module covers three core flows:

1. **Welfare Kit Fund** — members make periodic contributions into a shared welfare pool.
2. **Emergency Disbursements** — the fund pays out to a member facing an emergency (sickness, bereavement, etc.).
3. **Member Support Contributions** — other members voluntarily contribute directly to a specific member in need, on top of any disbursement from the fund.

For every welfare event, the system produces a summary showing the total support received by the beneficiary from both sources.

---

## Glossary

- **Welfare_Kit**: The dedicated welfare fund account, managed separately from the main chama account.
- **Welfare_Contribution**: A periodic payment made by a member into the Welfare_Kit fund.
- **Monthly_Contribution_Rate**: The system-configured KES amount that all members are expected to contribute to the Welfare_Kit for a given period, set and updated by the Treasurer.
- **Welfare_Event**: A recorded emergency or financial-need case opened for a specific beneficiary member.
- **Disbursement**: A payment made from the Welfare_Kit fund to a beneficiary member for a Welfare_Event.
- **Support_Contribution**: A voluntary payment made by an individual member directly to a beneficiary member for a specific Welfare_Event.
- **Beneficiary**: The member who receives support during a Welfare_Event.
- **Contributor**: A member who makes a Welfare_Contribution or Support_Contribution.
- **Welfare_Balance**: The current available balance of the Welfare_Kit fund (total Welfare_Contributions minus total Disbursements).
- **Event_Total**: The sum of the Disbursement amount and all Support_Contributions for a single Welfare_Event.
- **Treasurer**: An authorised user role permitted to record financial transactions.
- **Admin**: An authorised user role permitted to manage and delete records.

---

## Requirements

### Requirement 1: Welfare Kit Fund Account

**User Story:** As a Treasurer, I want a separate welfare fund account, so that welfare finances are tracked independently from the main chama contributions.

#### Acceptance Criteria

1. THE Welfare_Kit SHALL maintain a Welfare_Balance calculated as the sum of all Welfare_Contributions minus the sum of all Disbursements.
2. THE Welfare_Kit SHALL store its transaction history independently from the main chama contributions ledger.
3. WHEN a Welfare_Contribution or Disbursement is recorded, THE Welfare_Kit SHALL update the Welfare_Balance immediately.
4. THE Welfare_Kit SHALL display the current Welfare_Balance on the welfare dashboard.

---

### Requirement 2: Welfare Kit Contributions

**User Story:** As a Treasurer, I want to record periodic welfare contributions from members, so that the Welfare_Kit fund is funded over time.

#### Acceptance Criteria

1. WHEN a Treasurer records a Welfare_Contribution, THE Welfare_Kit SHALL store the contributing member, the amount in KES, and the date of contribution.
2. THE Welfare_Kit SHALL associate each Welfare_Contribution with a specific month and year to support period-based reporting.
3. THE Welfare_Kit SHALL allow a Treasurer to list all Welfare_Contributions, filterable by member name, month, and year.
4. THE Welfare_Kit SHALL allow a Treasurer to edit a Welfare_Contribution record.
5. THE Welfare_Kit SHALL allow an Admin to delete a Welfare_Contribution record.
6. IF a Welfare_Contribution amount is less than or equal to zero, THEN THE Welfare_Kit SHALL reject the record and return a descriptive validation error.

---

### Requirement 2b: Configurable Monthly Contribution Amount

**User Story:** As a Treasurer, I want to configure the expected monthly welfare contribution amount, so that all members are held to a consistent, system-defined standard for each period.

#### Acceptance Criteria

1. THE Welfare_Kit SHALL maintain a Monthly_Contribution_Rate, defined as a single KES amount that applies to all members for a given contribution period.
2. WHEN a Treasurer sets or updates the Monthly_Contribution_Rate, THE Welfare_Kit SHALL store the new amount and the date from which it takes effect.
3. THE Welfare_Kit SHALL display the current Monthly_Contribution_Rate on the welfare dashboard.
4. WHEN the defaulters list is generated for a given month and year, THE Welfare_Kit SHALL use the Monthly_Contribution_Rate in effect for that period to determine expected contributions.
5. IF a Treasurer attempts to set a Monthly_Contribution_Rate of less than or equal to zero, THEN THE Welfare_Kit SHALL reject the update and return a descriptive validation error.

---

### Requirement 3: Welfare Contribution Defaulters

**User Story:** As a Treasurer, I want to see which members have not made a welfare contribution for a given month, so that I can follow up with them.

#### Acceptance Criteria

1. WHEN a Treasurer requests the defaulters list for a given month and year, THE Welfare_Kit SHALL return all active members who have no Welfare_Contribution recorded for that period.
2. THE Welfare_Kit SHALL allow a Treasurer to export the defaulters list as a PDF report.
3. IF a non-Treasurer authenticated user attempts to export the defaulters list, THEN THE Welfare_Kit SHALL deny the request and return an authorisation error.

---

### Requirement 4: Welfare Events

**User Story:** As a Treasurer, I want to open a welfare event for a member in need, so that all support activity for that emergency is grouped and tracked together.

#### Acceptance Criteria

1. WHEN a Treasurer creates a Welfare_Event, THE Welfare_Kit SHALL store the beneficiary member, a description of the emergency, and the date the event was opened.
2. THE Welfare_Kit SHALL assign each Welfare_Event a status of either "Open" or "Closed".
3. THE Welfare_Kit SHALL allow a Treasurer to close a Welfare_Event when support activity is complete.
4. THE Welfare_Kit SHALL list all Welfare_Events, filterable by status and beneficiary member name.
5. THE Welfare_Kit SHALL display the Event_Total for each Welfare_Event in the list and detail views.

---

### Requirement 5: Emergency Disbursements from the Welfare Kit Fund

**User Story:** As a Treasurer, I want to record a disbursement from the welfare fund to a beneficiary, so that there is a clear record of how much the fund paid out for each emergency.

#### Acceptance Criteria

1. WHEN a Treasurer records a Disbursement, THE Welfare_Kit SHALL store the associated Welfare_Event, the amount disbursed in KES, the date, and an optional note.
2. THE Welfare_Kit SHALL allow at most one Disbursement per Welfare_Event from the fund.
3. IF a Disbursement amount exceeds the current Welfare_Balance, THEN THE Welfare_Kit SHALL reject the record and return a descriptive validation error stating the available balance.
4. IF a Disbursement amount is less than or equal to zero, THEN THE Welfare_Kit SHALL reject the record and return a descriptive validation error.
5. WHEN a Disbursement is saved, THE Welfare_Kit SHALL deduct the disbursed amount from the Welfare_Balance.
6. THE Welfare_Kit SHALL allow a Treasurer to edit a Disbursement record, and SHALL recalculate the Welfare_Balance accordingly.
7. THE Welfare_Kit SHALL allow an Admin to delete a Disbursement record, and SHALL restore the disbursed amount to the Welfare_Balance.

---

### Requirement 6: Member Support Contributions

**User Story:** As a Treasurer, I want to record individual member contributions made directly to support a specific beneficiary, so that I know who contributed and how much during a welfare event.

#### Acceptance Criteria

1. WHEN a Treasurer records a Support_Contribution, THE Welfare_Kit SHALL store the associated Welfare_Event, the contributing member, the amount in KES, and the date.
2. THE Welfare_Kit SHALL allow multiple Support_Contributions per Welfare_Event, from different members.
3. THE Welfare_Kit SHALL allow a Treasurer to list all Support_Contributions for a given Welfare_Event.
4. IF a Support_Contribution amount is less than or equal to zero, THEN THE Welfare_Kit SHALL reject the record and return a descriptive validation error.
5. IF the contributing member of a Support_Contribution is the same as the Beneficiary of the associated Welfare_Event, THEN THE Welfare_Kit SHALL reject the record and return a descriptive validation error stating that a beneficiary cannot contribute to their own welfare event.
6. THE Welfare_Kit SHALL allow a Treasurer to edit a Support_Contribution record.
7. THE Welfare_Kit SHALL allow an Admin to delete a Support_Contribution record.

---

### Requirement 7: Welfare Event Summary

**User Story:** As a Treasurer or member, I want to see a full summary of support received for a welfare event, so that I know the total amount the beneficiary received and from which sources.

#### Acceptance Criteria

1. WHEN a Welfare_Event detail page is viewed, THE Welfare_Kit SHALL display the Disbursement amount from the fund (or zero if none recorded).
2. WHEN a Welfare_Event detail page is viewed, THE Welfare_Kit SHALL display each Support_Contribution with the contributing member's name and amount.
3. WHEN a Welfare_Event detail page is viewed, THE Welfare_Kit SHALL display the Event_Total, calculated as the Disbursement amount plus the sum of all Support_Contributions for that event.
4. THE Welfare_Kit SHALL allow a Treasurer to export the Welfare_Event summary as a PDF report.
5. IF a non-Treasurer authenticated user attempts to export the Welfare_Event summary, THEN THE Welfare_Kit SHALL deny the request and return an authorisation error.

---

### Requirement 8: Welfare Reports and Fund Overview

**User Story:** As a Treasurer, I want a welfare-specific overview page, so that I can monitor the fund balance and activity at a glance.

#### Acceptance Criteria

1. THE Welfare_Kit SHALL provide a welfare dashboard page showing the current Welfare_Balance, total Welfare_Contributions to date, total Disbursements to date, and the count of open Welfare_Events.
2. THE Welfare_Kit SHALL allow a Treasurer to export a welfare contributions report as CSV and PDF, filterable by member, month, and year.
3. IF a non-Treasurer authenticated user attempts to export any welfare report, THEN THE Welfare_Kit SHALL deny the request and return an authorisation error.
4. THE Welfare_Kit SHALL present all welfare data on pages that are accessible only to authenticated users, consistent with the role-based access control used across the chama system.
5. WHILE a user is authenticated with the Member role, THE Welfare_Kit SHALL allow read-only access to welfare data pages and SHALL not display export controls.
