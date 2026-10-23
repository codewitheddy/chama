# Implementation Plan: Welfare Kit

## Overview

Build the `welfare` Django app from scratch, following the patterns of the existing `contributions` app. Tasks are ordered so each step builds on the previous: app scaffold → models → migrations → forms → views → URLs → templates → sidebar → tests. Property-based tests use Hypothesis and are placed close to the code they validate.

## Tasks

- [x] 1. Scaffold the welfare app and register it with Django
  - Create `chama_system/welfare/` with `__init__.py`, `apps.py`, `admin.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, and an empty `migrations/__init__.py`
  - Add `WelfareConfig` in `apps.py` following the `ContributionsConfig` pattern (`default_auto_field`, `name = 'welfare'`)
  - Add `'welfare'` to `INSTALLED_APPS` in `chama_system/chama_system/settings.py` after `'meetings'`
  - Mount the app at `/welfare/` in `chama_system/chama_system/urls.py` with `include('welfare.urls')`
  - _Requirements: 1.1, 8.4_

- [x] 2. Implement models and the balance helper
  - [x] 2.1 Write all four models and the `get_welfare_balance()` helper in `welfare/models.py`
    - Define `MONTH_CHOICES` list (same as `contributions/models.py`)
    - Implement `WelfareContributionRate` with `amount`, `effective_date`, `created_at`, `current_rate()` classmethod, and `rate_for_period()` classmethod
    - Implement `WelfareContribution` with `member` FK, `amount`, `date`, `month`, `year` fields and `Meta.ordering = ['-date']`
    - Implement `WelfareEvent` with `beneficiary` FK, `description`, `date_opened`, `status` fields; add `disbursement_amount`, `support_total`, and `event_total` properties
    - Implement `WelfareDisbursement` with `event` OneToOneField, `amount`, `date`, `notes` fields
    - Implement `WelfareSupportContribution` with `event` FK, `contributor` FK, `amount`, `date` fields
    - Implement `get_welfare_balance()` as a module-level function using `Sum` aggregates on `WelfareContribution` and `WelfareDisbursement`
    - _Requirements: 1.1, 1.3, 2.1, 2.2, 2b.1, 2b.2, 4.1, 4.2, 5.1, 5.2, 6.1, 6.2, 7.3_

  - [ ]* 2.2 Write property test for welfare balance invariant
    - **Property 1: Welfare balance invariant**
    - **Validates: Requirements 1.1, 1.3, 5.5, 5.6, 5.7**
    - Create `welfare/tests_pbt.py`; use `@given` with `st.lists(st.decimals(...))` for contributions and disbursements; assert `get_welfare_balance()` equals sum-of-contributions minus sum-of-disbursements for any combination

  - [ ]* 2.3 Write property test for contribution field persistence
    - **Property 2: Contribution field persistence**
    - **Validates: Requirements 2.1, 2.2**
    - Use `@given(amount, date)` to create a `WelfareContribution`, re-fetch from DB, assert `month == date.month` and `year == date.year` and all other fields match

  - [ ]* 2.4 Write property test for welfare event field persistence
    - **Property 9: Welfare event field persistence**
    - **Validates: Requirements 4.1, 4.2**
    - Use `@given(description, date_opened)` to create a `WelfareEvent`, re-fetch from DB, assert all fields match and `status == 'open'`

  - [ ]* 2.5 Write property test for event total computation
    - **Property 11: Event total computation**
    - **Validates: Requirements 4.5, 7.1, 7.3**
    - Use `@given` with optional disbursement amount and list of support amounts; create the corresponding DB records; assert `event.event_total == disbursement_amount + sum(support_amounts)`

  - [ ]* 2.6 Write property test for rate persistence
    - **Property 5: Rate persistence**
    - **Validates: Requirements 2b.2**
    - Use `@given(amount, effective_date)` to create a `WelfareContributionRate`, re-fetch from DB, assert both fields match

- [x] 3. Create and apply database migrations
  - Run `python manage.py makemigrations welfare` inside `chama_system/` to generate `welfare/migrations/0001_initial.py`
  - Run `python manage.py migrate` to apply the migration
  - Verify the six tables are created without errors
  - _Requirements: 1.1, 2.1, 2b.1, 4.1, 5.1, 6.1_

- [x] 4. Implement forms in `welfare/forms.py`
  - [x] 4.1 Implement `WelfareContributionRateForm`
    - Fields: `amount`, `effective_date`; Bootstrap widget attrs; `clean_amount` raises `ValidationError` for `amount <= 0`
    - _Requirements: 2b.2, 2b.5_

  - [ ]* 4.2 Write property test for non-positive rate rejection
    - **Property 6: Non-positive rate is rejected**
    - **Validates: Requirements 2b.5**
    - Use `@given(st.decimals(max_value='0'))` to assert `WelfareContributionRateForm` is invalid and has an error on `amount`

  - [x] 4.3 Implement `WelfareContributionForm`
    - Fields: `member`, `amount`, `date`; Bootstrap widget attrs; `clean_amount` raises `ValidationError` for `amount <= 0`; `save()` derives `month` and `year` from `date` (same pattern as `ContributionForm`)
    - _Requirements: 2.1, 2.2, 2.6_

  - [ ]* 4.4 Write property test for non-positive contribution amount rejection
    - **Property 4: Non-positive contribution amount is rejected**
    - **Validates: Requirements 2.6, 6.4**
    - Use `@given(st.decimals(max_value='0'))` to assert `WelfareContributionForm` is invalid and has an error on `amount`

  - [x] 4.5 Implement `WelfareEventForm`
    - Fields: `beneficiary`, `description`, `date_opened`; Bootstrap widget attrs
    - _Requirements: 4.1_

  - [x] 4.6 Implement `WelfareDisbursementForm`
    - Fields: `amount`, `date`, `notes`; Bootstrap widget attrs; `__init__` accepts `welfare_balance` kwarg; `clean_amount` raises `ValidationError` for `amount <= 0` and for `amount > welfare_balance`; `clean` raises `ValidationError` if the event already has a disbursement (checked in the view before instantiation)
    - _Requirements: 5.1, 5.3, 5.4_

  - [ ]* 4.7 Write property test for disbursement exceeding balance rejection
    - **Property 12: Disbursement exceeding balance is rejected**
    - **Validates: Requirements 5.3**
    - Use `@given` with `amount > balance`; assert form is invalid and error message includes the balance figure

  - [ ]* 4.8 Write property test for non-positive disbursement amount rejection
    - **Property 13: Non-positive disbursement amount is rejected**
    - **Validates: Requirements 5.4**
    - Use `@given(st.decimals(max_value='0'))` to assert `WelfareDisbursementForm` is invalid and has an error on `amount`

  - [x] 4.9 Implement `WelfareSupportContributionForm`
    - Fields: `contributor`, `amount`, `date`; Bootstrap widget attrs; `clean_amount` raises `ValidationError` for `amount <= 0`; `clean` raises `ValidationError` when `contributor == event.beneficiary` (event injected via `__init__`)
    - _Requirements: 6.1, 6.4, 6.5_

  - [ ]* 4.10 Write property test for beneficiary self-contribution rejection
    - **Property 14: Beneficiary cannot self-contribute**
    - **Validates: Requirements 6.5**
    - Use `@given` with `contributor == event.beneficiary`; assert `WelfareSupportContributionForm` is invalid with a descriptive error

- [ ] 5. Checkpoint — run all tests so far
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement views in `welfare/views.py`
  - [x] 6.1 Implement `WelfareDashboardView`
    - `MemberAccessMixin`, `TemplateView`; template `welfare/dashboard.html`
    - Context: `welfare_balance`, `total_contributions`, `total_disbursements`, `open_events_count`, `recent_contributions` (last 5), `open_events` (all open)
    - _Requirements: 1.4, 8.1, 8.3_

  - [x] 6.2 Implement `WelfareContributionListView`
    - `MemberAccessMixin`, `ListView`; `paginate_by = 20`; filter by `q` (member name icontains), `month`, `year`; context includes `months`, `years`, `q`, `selected_month`, `selected_year`
    - _Requirements: 2.3, 8.2_

  - [ ]* 6.3 Write property test for contribution filter correctness
    - **Property 3: Contribution filter correctness**
    - **Validates: Requirements 2.3**
    - Use `@given` with member name fragment, month, year; create matching and non-matching records; assert queryset returns only records satisfying all supplied predicates

  - [x] 6.4 Implement `WelfareContributionCreateView` and `WelfareContributionUpdateView`
    - Both use `TreasurerRequiredMixin`, `SuccessMessageMixin`; `form_class = WelfareContributionForm`; template `welfare/contribution_form.html`
    - Create redirects to `welfare:contribution_add`; update redirects to `welfare:contribution_list`
    - _Requirements: 2.1, 2.4_

  - [x] 6.5 Implement `WelfareContributionDeleteView`
    - `AdminRequiredMixin`, `DeleteView`; template `welfare/contribution_confirm_delete.html`; redirects to `welfare:contribution_list`
    - _Requirements: 2.5_

  - [x] 6.6 Implement `WelfareContributionExportView`
    - `TreasurerRequiredMixin`, `View`; supports `?format=csv` and `?format=pdf`; applies same filters as list view; calls `export_csv` or `export_pdf` from `utils/exports.py`
    - _Requirements: 8.2, 8.3_

  - [x] 6.7 Implement `WelfareDefaultersView` and `WelfareDefaultersExportView`
    - `WelfareDefaultersView`: `MemberAccessMixin`, `TemplateView`; computes defaulters as `Member.objects.exclude(id__in=paid_ids)` for the selected month/year; uses `WelfareContributionRate.rate_for_period()` to show expected amount in context
    - `WelfareDefaultersExportView`: `TreasurerRequiredMixin`, `View`; exports defaulters as PDF via `export_pdf`
    - _Requirements: 3.1, 3.2, 3.3, 2b.4_

  - [ ]* 6.8 Write property test for defaulters list correctness
    - **Property 7: Defaulters list correctness**
    - **Validates: Requirements 3.1, 2b.4**
    - Use `@given` with a set of member IDs and a subset that paid; assert defaulters queryset returns exactly the complement set for that month/year

  - [x] 6.9 Implement `WelfareContributionRateView`
    - `TreasurerRequiredMixin`, `CreateView` (always creates a new rate record); template `welfare/rate_form.html`; redirects to `welfare:dashboard` on success
    - _Requirements: 2b.1, 2b.2, 2b.3_

  - [x] 6.10 Implement `WelfareEventListView`
    - `MemberAccessMixin`, `ListView`; `paginate_by = 20`; filter by `status` and `q` (beneficiary name icontains); context includes filter values
    - _Requirements: 4.4, 4.5_

  - [ ]* 6.11 Write property test for event filter correctness
    - **Property 10: Event filter correctness**
    - **Validates: Requirements 4.4**
    - Use `@given` with status and beneficiary name fragment; create matching and non-matching records; assert queryset returns only records satisfying all supplied predicates

  - [x] 6.12 Implement `WelfareEventCreateView`, `WelfareEventUpdateView`, `WelfareEventDeleteView`
    - Create/Update: `TreasurerRequiredMixin`, `SuccessMessageMixin`; `form_class = WelfareEventForm`; template `welfare/event_form.html`
    - Delete: `AdminRequiredMixin`; template `welfare/event_confirm_delete.html`; redirects to `welfare:event_list`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 6.13 Implement `WelfareEventDetailView`
    - `MemberAccessMixin`, `DetailView`; template `welfare/event_detail.html`; context includes `welfare_balance`, `disbursement` (or None), `support_contributions`, `event_total`
    - _Requirements: 4.5, 7.1, 7.2, 7.3_

  - [x] 6.14 Implement `WelfareEventCloseView`
    - `TreasurerRequiredMixin`, `View`; POST only; sets `event.status = 'closed'` and saves; redirects to `welfare:event_detail`
    - _Requirements: 4.3_

  - [x] 6.15 Implement `WelfareDisbursementCreateView` and `WelfareDisbursementUpdateView`
    - Both use `TreasurerRequiredMixin`, `SuccessMessageMixin`; inject `welfare_balance` into form via `get_form_kwargs`
    - Create view: check for existing disbursement before allowing creation; catch `IntegrityError` and surface as user-facing error
    - Template: `welfare/disbursement_form.html`; redirect to `welfare:event_detail` on success
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 6.16 Implement `WelfareDisbursementDeleteView`
    - `AdminRequiredMixin`, `DeleteView`; template `welfare/disbursement_confirm_delete.html`; redirects to `welfare:event_detail`
    - _Requirements: 5.7_

  - [x] 6.17 Implement `WelfareSupportCreateView` and `WelfareSupportUpdateView`
    - Both use `TreasurerRequiredMixin`, `SuccessMessageMixin`; inject `event` into form via `get_form_kwargs` so `clean` can check contributor != beneficiary
    - Template: `welfare/support_contribution_form.html`; redirect to `welfare:event_detail` on success
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.18 Implement `WelfareSupportDeleteView`
    - `AdminRequiredMixin`, `DeleteView`; template `welfare/support_contribution_confirm_delete.html`; redirects to `welfare:event_detail`
    - _Requirements: 6.7_

  - [x] 6.19 Implement `WelfareEventExportView`
    - `TreasurerRequiredMixin`, `View`; exports event summary (disbursement + support contributions) as PDF via `export_pdf`; uses `welfare/export_event_summary.html` context for the PDF title
    - _Requirements: 7.4, 7.5_

- [x] 7. Define URL patterns in `welfare/urls.py`
  - Set `app_name = 'welfare'`
  - Wire all 22 URL patterns from the design document's URL structure table, mapping each path to its view class with the correct `name=` argument
  - _Requirements: 1.4, 2.3, 2.4, 2.5, 3.1, 3.2, 4.1, 4.3, 4.4, 5.1, 5.6, 5.7, 6.1, 6.6, 6.7, 7.4, 8.1, 8.2_

- [x] 8. Register models in `welfare/admin.py`
  - Register `WelfareContributionRate`, `WelfareContribution`, `WelfareEvent`, `WelfareDisbursement`, `WelfareSupportContribution` using `@admin.register`
  - Add `list_display`, `list_filter`, and `search_fields` for each, following the `ContributionAdmin` pattern
  - _Requirements: 2.1, 2b.1, 4.1, 5.1, 6.1_

- [ ] 9. Checkpoint — run migrations and smoke-test admin
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create templates in `chama_system/templates/welfare/`
  - [x] 10.1 Create `welfare/dashboard.html`
    - Extend `base.html`; four `.stat-card` divs (Welfare Balance accent-green, Total Contributions accent-blue, Total Disbursements accent-rose, Open Events accent-amber)
    - Two tables below stat cards: 5 most recent welfare contributions and all open events
    - Show current `Monthly_Contribution_Rate` and a "Set Rate" link for treasurer/admin
    - _Requirements: 1.4, 2b.3, 8.1_

  - [x] 10.2 Create `welfare/contribution_list.html`
    - Extend `base.html`; filter form with `data-ajax-filter` (member name text input, month select, year select) and `.ajax-clear` button
    - `id="results-container"` wrapping the table and `{% include 'includes/pagination.html' %}`
    - Export buttons (CSV, PDF) visible only when `user.profile.role != 'readonly'`
    - _Requirements: 2.3, 8.2, 8.3, 8.5_

  - [x] 10.3 Create `welfare/contribution_form.html` and `welfare/contribution_confirm_delete.html`
    - Form template: same card/form layout as `contributions/contribution_form.html`; Cancel links back to `welfare:contribution_list`
    - Delete template: confirmation card with object name and Cancel/Delete buttons
    - _Requirements: 2.1, 2.4, 2.5_

  - [x] 10.4 Create `welfare/defaulters.html`
    - Same layout as `contributions/defaulters.html`; month/year filter; table of defaulters (name, phone); PDF export button visible only to treasurer/admin
    - Show expected contribution amount from `WelfareContributionRate.rate_for_period()`
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 10.5 Create `welfare/rate_form.html`
    - Simple card form for setting the monthly contribution rate; Cancel links back to `welfare:dashboard`
    - _Requirements: 2b.2, 2b.3_

  - [x] 10.6 Create `welfare/event_list.html`
    - Extend `base.html`; filter form with `data-ajax-filter` (status select, beneficiary name text input)
    - `id="results-container"` wrapping the table; columns: Beneficiary, Description, Date Opened, Status badge, Event Total, Actions
    - "New Event" button visible to treasurer/admin
    - _Requirements: 4.4, 4.5_

  - [x] 10.7 Create `welfare/event_form.html` and `welfare/event_confirm_delete.html`
    - Form template: card/form layout; Cancel links back to `welfare:event_list`
    - Delete template: confirmation card with Cancel/Delete buttons
    - _Requirements: 4.1, 4.3_

  - [x] 10.8 Create `welfare/event_detail.html`
    - Section 1: event header card (beneficiary, description, date, status badge, Close Event button for treasurer/admin on open events)
    - Section 2: Fund Disbursement card — shows amount and date, or "No disbursement recorded" with Add Disbursement button; Edit/Delete buttons for existing disbursement
    - Section 3: Member Support Contributions card — table of contributors + amounts + dates; Add Support Contribution button; Edit/Delete per row
    - Section 4: Event Total summary row (`disbursement_amount + support_total`)
    - Export PDF button visible only to treasurer/admin
    - _Requirements: 4.5, 5.1, 5.2, 6.3, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 10.9 Create `welfare/disbursement_form.html` and `welfare/disbursement_confirm_delete.html`
    - Form template: card/form layout; show current welfare balance in a callout above the form; Cancel links back to `welfare:event_detail`
    - Delete template: confirmation card
    - _Requirements: 5.1, 5.3_

  - [x] 10.10 Create `welfare/support_contribution_form.html` and `welfare/support_contribution_confirm_delete.html`
    - Form template: card/form layout; Cancel links back to `welfare:event_detail`
    - Delete template: confirmation card
    - _Requirements: 6.1, 6.5_

  - [x] 10.11 Create `welfare/export_event_summary.html` (PDF context template — not rendered in browser)
    - Used only as a title/context source for `WelfareEventExportView`; not a standalone browsable page
    - _Requirements: 7.4_

- [ ] 11. Add Welfare section to sidebar in `base.html`
  - Insert the three `<li>` items (nav-section label + Welfare Dashboard + Welfare Contributions + Welfare Events) between the closing `</li>` of the Meetings nav item and the `<li class="nav-section">Reports</li>` line
  - Use `{% if request.resolver_match.app_name == 'welfare' %}active{% endif %}` on the dashboard link
  - Icons: `bi-heart-pulse` for dashboard, `bi-cash` for contributions, `bi-clipboard2-heart` for events
  - _Requirements: 8.1, 8.4_

- [ ] 12. Write unit tests in `welfare/tests.py`
  - [ ] 12.1 Write model unit tests
    - Test `__str__` for all five models
    - Test `get_welfare_balance()` with zero records, contributions only, disbursements only, and mixed
    - Test `WelfareEvent.event_total` with no disbursement, disbursement only, support only, and both
    - Test `WelfareContributionRate.current_rate()` and `rate_for_period()` with multiple rate records
    - _Requirements: 1.1, 1.3, 2b.1, 4.5, 7.3_

  - [ ] 12.2 Write form validation unit tests
    - Test each error scenario from the design's error table (7 scenarios)
    - Test that valid inputs produce no errors for each form
    - _Requirements: 2.6, 2b.5, 5.3, 5.4, 6.4, 6.5_

  - [ ] 12.3 Write view access control unit tests
    - Test 403 for `readonly` role on all export views (`contribution_export`, `defaulters_export`, `event_export`)
    - Test 302 redirect to `/accounts/login/` for unauthenticated requests on all welfare URLs
    - _Requirements: 3.3, 7.5, 8.3, 8.4_

  - [ ]* 12.4 Write property test for access control — export views deny non-treasurer roles
    - **Property 8: Access control — export views deny non-treasurer roles**
    - **Validates: Requirements 3.3, 7.5, 8.3**
    - Use `@given` with a welfare export URL sampled from the three export endpoints; assert authenticated `readonly` user receives HTTP 403

  - [ ]* 12.5 Write property test for unauthenticated access denial
    - **Property 15: Unauthenticated access is denied**
    - **Validates: Requirements 8.4**
    - Use `@given` with a welfare URL sampled from the full URL list; assert unauthenticated request receives HTTP 302 to `/accounts/login/`

  - [ ] 12.6 Write dashboard context unit tests
    - Test that `welfare:dashboard` returns all required context keys (`welfare_balance`, `total_contributions`, `total_disbursements`, `open_events_count`, `recent_contributions`, `open_events`)
    - Test that balance and counts are correct after inserting test records
    - _Requirements: 1.4, 8.1_

  - [ ] 12.7 Write defaulters list unit tests
    - Test members with contributions for a period are excluded from defaulters
    - Test members without contributions for a period are included in defaulters
    - _Requirements: 3.1_

  - [ ] 12.8 Write integration tests
    - End-to-end: create event → record disbursement → record support contributions → assert `event_total` on detail page equals disbursement + support sum
    - Export: assert CSV response has `content-type: text/csv` and non-empty body; assert PDF response has `content-type: application/pdf` and non-empty body
    - Balance recalculation: assert balance updates correctly after editing and after deleting a disbursement
    - _Requirements: 1.3, 5.5, 5.6, 5.7, 7.3, 8.2_

- [ ] 13. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at natural breaks
- Property tests (Hypothesis) validate universal correctness properties; install with `pip install hypothesis`
- Unit tests validate specific examples and edge cases
- The `welfare_balance` is never stored — always computed via `get_welfare_balance()` in `welfare/models.py`
- All templates go in `chama_system/templates/welfare/` (the project-level templates directory, not inside the app)
- The `WelfareDisbursementForm` receives `welfare_balance` at instantiation time via `get_form_kwargs` in the view
