from django.db import models
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from members.models import Member


class NonMemberApplicant(models.Model):
    """
    Stores details of an external (non-member) loan applicant.
    The admin reviews and qualifies the applicant before issuing a loan.
    """
    QUALIFICATION_CHOICES = [
        ('pending',    'Pending Review'),
        ('qualified',  'Qualified'),
        ('disqualified', 'Disqualified'),
    ]

    # Personal details
    full_name         = models.CharField(max_length=200)
    phone             = models.CharField(max_length=20, unique=True)
    id_number         = models.CharField(max_length=50, blank=True, help_text='National ID or Passport number.')
    email             = models.EmailField(blank=True)
    address           = models.CharField(max_length=300, blank=True)
    id_document = models.FileField(
        upload_to='non_members/id_docs/',
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        help_text='National ID, passport scan, or any official ID document.',
    )

    # Financial profile
    employer          = models.CharField(max_length=200, blank=True, help_text='Current employer or business name.')
    monthly_income    = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Estimated monthly income (KES).',
    )
    reason_for_loan   = models.TextField(blank=True, help_text='Purpose of the loan.')

    # Admin qualification
    qualification_status = models.CharField(
        max_length=20, choices=QUALIFICATION_CHOICES, default='pending',
    )
    qualification_notes  = models.TextField(
        blank=True,
        help_text='Admin notes on the qualification assessment.',
    )
    qualified_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='qualified_non_members',
        help_text='Admin/treasurer who assessed this applicant.',
    )
    qualified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.get_qualification_status_display()})"

    @property
    def is_qualified(self):
        return self.qualification_status == 'qualified'

    @property
    def has_active_loan(self):
        return self.loans.filter(status__in=['active', 'late']).exists()

# Read from settings so it can be changed without touching code.
INTEREST_RATE = Decimal(str(getattr(settings, 'LOAN_INTEREST_RATE', 0.10)))


def get_default_interest_rate():
    """Return the system-wide default interest rate from DB, falling back to settings."""
    try:
        obj = SystemSetting.objects.get(key='default_interest_rate')
        return Decimal(obj.value)
    except Exception:
        return INTEREST_RATE


THEME_PRESETS = {
    'navy_slate': {
        'id': 'navy_slate',
        'name': 'Navy Slate (Default)',
        'description': 'Professional dark navy with classic royal blue accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#2563eb',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'emerald_forest': {
        'id': 'emerald_forest',
        'name': 'Emerald Forest',
        'description': 'Clean dark navy with vibrant emerald green accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#059669',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'midnight_purple': {
        'id': 'midnight_purple',
        'name': 'Midnight Purple',
        'description': 'Clean dark navy with royal purple accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#7c3aed',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'ocean_teal': {
        'id': 'ocean_teal',
        'name': 'Ocean Teal',
        'description': 'Clean dark navy with crisp modern teal accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#0d9488',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'crimson_burgundy': {
        'id': 'crimson_burgundy',
        'name': 'Crimson Rose',
        'description': 'Clean dark navy with bold crimson rose accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#e11d48',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'charcoal_gold': {
        'id': 'charcoal_gold',
        'name': 'Amber Gold',
        'description': 'Clean dark navy with warm amber gold accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#d97706',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
    'classic_blue': {
        'id': 'classic_blue',
        'name': 'Sky Blue',
        'description': 'Clean dark navy with vivid corporate sky blue accent',
        'sidebar_bg': '#1e2a3a',
        'sidebar_hover': '#2c3e52',
        'primary_color': '#3b82f6',
        'sidebar_text': '#94a3b8',
        'sidebar_section': '#475569',
    },
}


class SystemSetting(models.Model):
    """Key/value store for system-wide configuration the admin can change via the UI."""
    key   = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=200, blank=True)
    help_text = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key, default=''):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value, label='', help_text=''):
        obj, _ = cls.objects.get_or_create(key=key)
        obj.value = str(value)
        if label:
            obj.label = label
        if help_text:
            obj.help_text = help_text
        obj.save()
        return obj

    @classmethod
    def get_group_info(cls):
        """Return a dict of all group-profile and system configuration settings with safe defaults."""
        keys = [
            # Group identity
            'group_name', 'group_tagline', 'group_logo', 'group_location',
            'group_phone', 'group_email', 'group_registration',
            'group_founded', 'group_postal_address', 'group_currency',
            # Visual theme
            'theme_preset', 'theme_sidebar_bg', 'theme_primary_color',
            'theme_sidebar_hover', 'theme_sidebar_text', 'theme_sidebar_section',
            # Financial rules
            'default_interest_rate', 'default_late_penalty_rate',
            'grace_period_days', 'max_active_loans_per_member', 'savings_loan_multiplier',
            # PDF / Document branding
            'pdf_header_title', 'pdf_footer_text', 'pdf_show_logo', 'pdf_show_contact',
        ]
        rows = {r.key: r.value for r in cls.objects.filter(key__in=keys)}

        # Determine theme tokens
        preset_key = rows.get('theme_preset', 'navy_slate')
        preset = THEME_PRESETS.get(preset_key, THEME_PRESETS['navy_slate'])

        sidebar_bg = '#1e2a3a'
        primary_color = rows.get('theme_primary_color') or preset['primary_color']
        sidebar_hover = '#2c3e52'
        sidebar_text = '#94a3b8'
        sidebar_section = '#475569'

        return {
            'group_name':           rows.get('group_name',           'Finance Wise TBM'),
            'group_tagline':        rows.get('group_tagline',        'Table Banking Manager'),
            'group_logo':           rows.get('group_logo',           ''),
            'group_location':       rows.get('group_location',       ''),
            'group_phone':          rows.get('group_phone',          ''),
            'group_email':          rows.get('group_email',          ''),
            'group_registration':   rows.get('group_registration',   ''),
            'group_founded':        rows.get('group_founded',        ''),
            'group_postal_address': rows.get('group_postal_address', ''),
            'group_currency':       rows.get('group_currency',       'KES'),
            # Theme
            'theme_preset':         preset_key,
            'theme_sidebar_bg':     sidebar_bg,
            'theme_primary_color':  primary_color,
            'theme_sidebar_hover':  sidebar_hover,
            'theme_sidebar_text':   sidebar_text,
            'theme_sidebar_section':sidebar_section,
            # Financial
            'default_interest_rate':        rows.get('default_interest_rate', '10.00'),
            'default_late_penalty_rate':    rows.get('default_late_penalty_rate', '10.00'),
            'grace_period_days':            rows.get('grace_period_days', '0'),
            'max_active_loans_per_member':  rows.get('max_active_loans_per_member', '0'),
            'savings_loan_multiplier':      rows.get('savings_loan_multiplier', '0'),
            # PDF / Documents
            'pdf_header_title':     rows.get('pdf_header_title', ''),
            'pdf_footer_text':      f"{rows.get('group_name', 'Finance Wise TBM')} - Powered by Ropenix Investments Limited ( 018 218 0965 )",
            'pdf_show_logo':        rows.get('pdf_show_logo', '1') == '1',
            'pdf_show_contact':     rows.get('pdf_show_contact', '1') == '1',
        }


class LoanProduct(models.Model):
    """
    A reusable loan template. When issuing a loan the treasurer can pick a
    product and all fields are pre-filled automatically.
    """

    INTEREST_TYPE_CHOICES = [
        ('flat',              'Flat Rate'),
        ('reducing_emi',      'Reducing Balance – Equal Installments (EMI)'),
        ('reducing_principal','Reducing Balance – Equal Principal'),
        ('emergency',         'Emergency Loan (0% Interest)'),
    ]

    FREQUENCY_CHOICES = [
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly',  'Yearly'),
    ]

    name             = models.CharField(max_length=150, unique=True)
    description      = models.TextField(blank=True)
    interest_type    = models.CharField(max_length=30, choices=INTEREST_TYPE_CHOICES, default='flat')
    interest_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='monthly')
    # Stored as percentage, e.g. 10.00 means 10%
    interest_rate    = models.DecimalField(
        max_digits=6, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Enter as a percentage, e.g. 10 for 10%.',
    )
    # Duration in months — 0 means "no fixed default"
    duration_months  = models.PositiveIntegerField(
        default=0,
        help_text='Default repayment period in months. 0 = no default.',
    )
    min_amount       = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    max_amount       = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='0 = no upper limit.',
    )
    is_active        = models.BooleanField(default=True)
    is_emergency     = models.BooleanField(
        default=False,
        help_text='Mark as an emergency loan product — 0% interest, short repayment window.',
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.interest_type == 'emergency' or self.is_emergency:
            self.interest_rate = Decimal('0.00')
            self.is_emergency = True
            self.interest_type = 'emergency'
        super().save(*args, **kwargs)

    @property
    def rate_as_decimal(self):
        """Return the rate as a decimal fraction, e.g. 10% → 0.10."""
        if self.interest_type == 'emergency':
            return Decimal('0.00')
        return (self.interest_rate / Decimal('100')).quantize(Decimal('0.0001'))

    @property
    def loan_type_for_calc(self):
        """Map interest_type → the 'flat' / 'reducing' / 'reducing_principal' / 'emergency' value used by Loan model."""
        if self.interest_type == 'emergency':
            return 'emergency'
        if self.interest_type == 'reducing_principal':
            return 'reducing_principal'
        if self.interest_type == 'reducing_emi':
            return 'reducing'
        return 'flat'


class Loan(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cleared', 'Cleared'),
        ('late', 'Late'),
        ('written_off', 'Written Off'),
        ('restructured', 'Restructured'),
    ]

    LOAN_TYPE_CHOICES = [
        ('flat',               'Flat Rate'),
        ('reducing',           'Reducing Balance (EMI)'),
        ('reducing_principal', 'Reducing Balance (Equal Principal)'),
        ('emergency',          'Emergency Loan (0% Interest)'),
    ]

    BORROWER_TYPE_CHOICES = [
        ('member',     'Member'),
        ('non_member', 'Non-Member'),
    ]

    borrower_type = models.CharField(
        max_length=15,
        choices=BORROWER_TYPE_CHOICES,
        default='member',
    )
    member = models.ForeignKey(Member, on_delete=models.CASCADE, null=True, blank=True)
    non_member = models.ForeignKey(
        NonMemberApplicant, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='loans',
        help_text='Set when issuing a loan to a non-member applicant.',
    )

    # ── Fund source ───────────────────────────────────────────────
    FUND_SOURCE_CHOICES = [
        ('group_funds',   'Group Funds'),
        ('bank_account',  'Bank Account'),
        ('other',         'Other Source'),
    ]
    fund_source = models.CharField(
        max_length=20,
        choices=FUND_SOURCE_CHOICES,
        default='group_funds',
        help_text='Where the loan money is coming from.',
    )
    fund_source_bank = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='loans_funded',
        help_text='Set when fund_source is "bank_account".',
    )
    fund_source_label = models.CharField(
        max_length=200, blank=True,
        help_text='Free-text description when fund_source is "other".',
    )

    # Optional link to the product this loan was issued from
    product = models.ForeignKey(
        LoanProduct, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='loans',
    )
    loan_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    duration_months = models.PositiveIntegerField(default=1)
    # Loan type determines how interest is calculated
    loan_type = models.CharField(
        max_length=20,
        choices=LOAN_TYPE_CHOICES,
        default='flat',
        help_text=(
            "Flat Rate: one-off interest on principal. "
            "Reducing Balance: monthly interest on outstanding balance."
        ),
    )
    # Per-loan interest rate (e.g. 0.10 = 10%). Defaults to the system-wide rate.
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=get_default_interest_rate,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="For flat: one-off rate on principal. For reducing: monthly rate on balance.",
    )
    interest_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    # Monthly instalment (reducing balance only; 0 for flat rate)
    monthly_installment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Fixed monthly repayment amount (reducing balance loans only).",
    )
    total_payable = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    date_taken = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    rollover_count = models.PositiveIntegerField(default=0)
    last_rollover_date = models.DateField(null=True, blank=True, help_text="Date of last rollover for payment scoping.")
    notes = models.TextField(blank=True)

    # Late-penalty tracking
    late_penalty_per_month = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Fixed monthly penalty amount (10% of original principal).",
    )
    late_penalty_months = models.PositiveIntegerField(
        default=0,
        editable=False,
        help_text="Number of overdue months for which the penalty has been applied.",
    )
    accumulated_penalties = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total penalty amount accumulated.",
    )

    class Meta:
        ordering = ['-date_taken']

    def _compute_interest(self):
        """
        Compute interest_amount, total_payable, and monthly_installment.

        Flat rate:
            interest = principal × rate  (once, regardless of duration)
            total_payable = principal + interest
            monthly_installment = 0

        Reducing Balance – EMI (equal installments):
            M = P × r / (1 - (1+r)^-n)
            total_payable = M × n
            interest = total_payable - principal
            monthly_installment = M

        Reducing Balance – Equal Principal:
            Each month: principal_payment = P / n
            interest for month i = outstanding_balance × r
            total_interest = sum of all monthly interests
            monthly_installment varies (decreasing)
            We store the FIRST month's installment as monthly_installment.
        """
        principal = Decimal(str(self.loan_amount))
        rate = Decimal(str(self.interest_rate)) if self.interest_rate is not None else get_default_interest_rate()
        n = int(self.duration_months) if self.duration_months else 1

        if self.loan_type == 'reducing_principal':
            # Equal principal repayment
            principal_per_month = (principal / Decimal(n)).quantize(Decimal('0.01'))
            total_interest = Decimal('0.00')
            balance = principal
            first_installment = Decimal('0.00')
            for i in range(n):
                month_interest = (balance * rate).quantize(Decimal('0.01'))
                installment = principal_per_month + month_interest
                if i == 0:
                    first_installment = installment
                total_interest += month_interest
                balance = max(balance - principal_per_month, Decimal('0'))
            total = (principal + total_interest).quantize(Decimal('0.01'))
            return total_interest, total, first_installment

        elif self.loan_type == 'reducing':
            if rate == 0:
                monthly = (principal / Decimal(n)).quantize(Decimal('0.01'))
                total = (monthly * n).quantize(Decimal('0.01'))
                interest = Decimal('0.00')
            else:
                r = float(rate)
                P = float(principal)
                M = P * r / (1 - (1 + r) ** (-n))
                monthly = Decimal(str(round(M, 2)))
                total = (monthly * n).quantize(Decimal('0.01'))
                interest = (total - principal).quantize(Decimal('0.01'))
            return interest, total, monthly

        elif self.loan_type == 'emergency':
            return Decimal('0.00'), principal.quantize(Decimal('0.01')), Decimal('0.00')

        else:
            # Flat rate
            interest = (principal * rate).quantize(Decimal('0.01'))
            total = (principal + interest).quantize(Decimal('0.01'))
            return interest, total, Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.loan_type == 'emergency' or (self.product and (self.product.is_emergency or self.product.interest_type == 'emergency')):
            self.loan_type = 'emergency'
            self.interest_rate = Decimal('0.0000')

        interest, total_base, monthly = self._compute_interest()
        self.interest_amount = interest
        self.monthly_installment = monthly

        # For flat loans store a fixed penalty-per-month at creation.
        # For reducing-balance loans the penalty is the outstanding balance x rate
        # each overdue month, so we store 0 (mark_late_loans computes it live).
        # For emergency loans (0% interest), late penalty per month is 0.
        if not self.pk:
            if self.loan_type == 'emergency':
                self.late_penalty_per_month = Decimal('0.00')
            elif self.loan_type == 'flat':
                principal = Decimal(str(self.loan_amount))
                rate = Decimal(str(self.interest_rate)) if self.interest_rate is not None else get_default_interest_rate()
                self.late_penalty_per_month = (principal * rate).quantize(Decimal('0.01'))
            else:
                self.late_penalty_per_month = Decimal('0.00')
            self.late_penalty_months = 0
            self.accumulated_penalties = Decimal('0.00')

        # For flat/emergency loans total_payable grows by late_penalty_per_month each overdue month.
        # For reducing loans mark_late_loans sets accumulated_penalties and total_payable.
        if self.loan_type in ('flat', 'emergency'):
            self.accumulated_penalties = (self.late_penalty_per_month * self.late_penalty_months).quantize(Decimal('0.01'))
        elif self.accumulated_penalties is None:
            self.accumulated_penalties = Decimal('0.00')

        self.total_payable = (total_base + self.accumulated_penalties).quantize(Decimal('0.01'))

        if self.date_taken and not self.due_date:
            import calendar
            from django.utils import timezone as tz
            month = self.date_taken.month - 1 + self.duration_months
            year = self.date_taken.year + month // 12
            month = month % 12 + 1
            day = min(self.date_taken.day, calendar.monthrange(year, month)[1])
            self.due_date = tz.localdate().replace(year=year, month=month, day=day)

        # Determine status — cleared takes priority, then late, then active
        from django.utils import timezone as tz
        today = tz.localdate()
        if self.amount_paid >= self.total_payable:
            self.status = 'cleared'
        elif self.due_date and today > self.due_date:
            self.status = 'late'
        elif self.status == 'cleared':
            self.status = 'active'
        elif self.status not in ('late', 'active'):
            self.status = 'active'

        super().save(*args, **kwargs)

    def apply_late_penalty(self):
        """
        Add one month's penalty to this loan (called by mark_late_loans).

        Flat loans:
            Each overdue month adds a fixed amount (original_principal x rate).
            total_payable = original_total + (late_penalty_per_month x overdue_months)

        Reducing-balance loans:
            Each overdue month charges interest on the CURRENT outstanding balance
            (outstanding_balance x rate).  This mirrors the original loan logic —
            the same monthly rate that built the EMI schedule continues to accrue
            on whatever the borrower still owes.
        """
        new_months = self.late_penalty_months + 1
        rate = Decimal(str(self.interest_rate)) if self.interest_rate is not None else get_default_interest_rate()

        if self.loan_type in ('flat', 'emergency'):
            # Fixed penalty per month
            _, base_total, _ = self._compute_interest()
            new_acc_penalties = (self.late_penalty_per_month * new_months).quantize(Decimal('0.01'))
            new_total = (base_total + new_acc_penalties).quantize(Decimal('0.01'))
        else:
            # Reducing balance: penalty = outstanding_balance x rate this month
            outstanding = max(self.total_payable - self.amount_paid, Decimal('0.00'))
            monthly_penalty = (outstanding * rate).quantize(Decimal('0.01'))
            new_acc_penalties = (self.accumulated_penalties + monthly_penalty).quantize(Decimal('0.01'))
            new_total = (self.total_payable + monthly_penalty).quantize(Decimal('0.01'))

        Loan.objects.filter(pk=self.pk).update(
            late_penalty_months=new_months,
            accumulated_penalties=new_acc_penalties,
            total_payable=new_total,
            status='late',
        )
        self.refresh_from_db()

    def do_rollover(self, duration_months=None):
        """
        Roll over the loan:
        - The outstanding balance becomes the new principal
        - Interest is recalculated using the same loan_type and rate
        - due_date is extended by duration_months
        - A LoanRollover record is created for audit trail
        """
        import calendar
        from django.db import transaction
        from django.utils import timezone as tz

        if self.balance <= Decimal('0.00'):
            raise ValueError("Cannot roll over a loan with zero or negative balance.")

        outstanding = self.balance
        months = duration_months or self.duration_months
        rate = Decimal(str(self.interest_rate)) if self.interest_rate is not None else get_default_interest_rate()

        if self.loan_type == 'reducing' and rate > 0:
            r = float(rate)
            M = float(outstanding) * r / (1 - (1 + r) ** (-months))
            monthly = Decimal(str(round(M, 2)))
            new_total = (monthly * months).quantize(Decimal('0.01'))
            new_interest = (new_total - outstanding).quantize(Decimal('0.01'))
        elif self.loan_type == 'reducing_principal':
            principal_per_month = (outstanding / Decimal(months)).quantize(Decimal('0.01'))
            total_interest = Decimal('0.00')
            bal = outstanding
            first_installment = Decimal('0.00')
            for i in range(months):
                month_interest = (bal * rate).quantize(Decimal('0.01'))
                installment = principal_per_month + month_interest
                if i == 0:
                    first_installment = installment
                total_interest += month_interest
                bal = max(bal - principal_per_month, Decimal('0'))
            new_interest = total_interest.quantize(Decimal('0.01'))
            new_total = (outstanding + new_interest).quantize(Decimal('0.01'))
            monthly = first_installment
        elif self.loan_type == 'emergency':
            new_interest = Decimal('0.00')
            new_total = outstanding
            monthly = Decimal('0.00')
        else:
            new_interest = (outstanding * rate).quantize(Decimal('0.01'))
            new_total = (outstanding + new_interest).quantize(Decimal('0.01'))
            monthly = Decimal('0.00')

        base = tz.localdate()
        month = base.month - 1 + months
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        new_due = base.replace(year=year, month=month, day=day)

        if self.loan_type in ('flat', 'emergency'):
            new_penalty_per_month = (outstanding * rate).quantize(Decimal('0.01'))
        else:
            new_penalty_per_month = Decimal('0.00')

        with transaction.atomic():
            LoanRollover.objects.create(
                loan=self,
                balance_before=outstanding,
                new_interest=new_interest,
                new_total=new_total,
                rolled_on=base,
            )
            Loan.objects.filter(pk=self.pk).update(
                loan_amount=outstanding,
                interest_amount=new_interest,
                monthly_installment=monthly,
                total_payable=new_total,
                amount_paid=Decimal('0.00'),
                due_date=new_due,
                status='active',
                rollover_count=self.rollover_count + 1,
                last_rollover_date=base,
                accumulated_penalties=Decimal('0.00'),
                late_penalty_months=0,
                late_penalty_per_month=new_penalty_per_month,
            )
        self.refresh_from_db()

    @property
    def balance(self):
        return max(self.total_payable - self.amount_paid, Decimal('0'))

    @property
    def repayment_percent(self):
        if self.total_payable == 0:
            return 0
        return min(int((self.amount_paid / self.total_payable) * 100), 100)

    @property
    def total_guaranteed(self):
        from django.db.models import Sum
        return self.guarantors.aggregate(t=Sum('amount_guaranteed'))['t'] or Decimal('0.00')

    @property
    def guarantee_coverage_percent(self):
        if self.loan_amount == 0:
            return 0
        return min(int((self.total_guaranteed / self.loan_amount) * 100), 100)

    @property
    def is_restructured(self):
        """Return True if this loan has been restructured or has approved restructure events."""
        return self.status == 'restructured' or self.restructures.filter(status='APPROVED').exists()

    @staticmethod
    def has_active_loan(member):
        return Loan.objects.filter(member=member, status__in=['active', 'late']).exists()

    @property
    def borrower_name(self):
        """Return the name of whoever holds this loan."""
        if self.borrower_type == 'non_member':
            try:
                return self.non_member.full_name if self.non_member else '—'
            except Exception:
                return '—'
        try:
            return self.member.name if self.member else '—'
        except Exception:
            return f"Member #{self.member_id}" if self.member_id else '—'

    @property
    def fund_source_description(self):
        """Human-readable fund source for display in templates."""
        if self.fund_source == 'bank_account' and self.fund_source_bank:
            return f"{self.fund_source_bank.bank_name} — {self.fund_source_bank.account_name}"
        if self.fund_source == 'other' and self.fund_source_label:
            return self.fund_source_label
        return 'Group Funds'

    def __str__(self):
        try:
            return f"#{self.pk} {self.borrower_name}  KES {self.loan_amount}"
        except Exception:
            return f"Loan #{self.pk} (KES {self.loan_amount})"


class LoanRollover(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='rollovers')
    balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    new_interest = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    new_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    rolled_on = models.DateField()

    class Meta:
        ordering = ['rolled_on']

    def __str__(self):
        return f"Rollover #{self.pk} for Loan #{self.loan_id} on {self.rolled_on}"


class LoanGuarantor(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='guarantors')
    guarantor = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='guarantees'
    )
    amount_guaranteed = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('loan', 'guarantor')

    def __str__(self):
        try:
            guarantor_name = self.guarantor.name
        except Exception:
            guarantor_name = f"Member #{self.guarantor_id}"
        return f"{guarantor_name} guarantees KES {self.amount_guaranteed} for Loan #{self.loan_id}"


class Collateral(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='collaterals')
    description = models.CharField(max_length=255)
    estimated_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    document = models.FileField(
        upload_to='collateral_docs/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} (KES {self.estimated_value})  Loan #{self.loan.pk}"


class LoanApplication(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    member          = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='loan_applications')
    loan_amount     = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    duration_months = models.PositiveIntegerField(default=1)
    reason          = models.TextField(help_text='Why the member needs this loan.')
    notes           = models.TextField(blank=True)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    review_notes    = models.TextField(blank=True, help_text='Treasurer notes on approval or rejection.')
    applied_at      = models.DateTimeField(default=timezone.now)
    reviewed_at     = models.DateTimeField(null=True, blank=True)

    # Who submitted and who reviewed
    applied_by  = models.ForeignKey(
        'auth.User', null=True, on_delete=models.SET_NULL,
        related_name='loan_applications_submitted',
    )
    reviewed_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='loan_applications_reviewed',
    )

    # Link to the actual Loan created on approval (null until approved)
    loan = models.OneToOneField(
        Loan, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='application',
    )

    class Meta:
        ordering = ['-applied_at']

    def __str__(self):
        try:
            member_name = self.member.name
        except Exception:
            member_name = f"Member #{self.member_id}"
        return f"Application #{self.pk} - {member_name} KES {self.loan_amount} ({self.get_status_display()})"

    @property
    def interest_preview(self):
        return (Decimal(str(self.loan_amount)) * get_default_interest_rate()).quantize(Decimal('0.01'))

    @property
    def total_payable_preview(self):
        return Decimal(str(self.loan_amount)) + self.interest_preview


class LoanRestructure(models.Model):
    RESTRUCTURE_TYPE_CHOICES = [
        ('TERM_EXTENSION',   'Term Extension'),
        ('RATE_ADJUSTMENT',  'Rate Adjustment'),
        ('MORATORIUM',       'Moratorium / Grace Period'),
        ('CONSOLIDATION',    'Loan Consolidation'),
        ('WRITE_OFF',        'Write-Off'),
    ]

    STATUS_CHOICES = [
        ('PENDING',  'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name='restructures',
        help_text='The primary loan being restructured.',
    )
    consolidated_loans = models.ManyToManyField(
        Loan, blank=True, related_name='consolidated_into_restructures',
        help_text='Additional loans being consolidated into this restructure (for CONSOLIDATION type).',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='loan_restructures_requested',
        help_text='User / officer who submitted the restructure request.',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='loan_restructures_approved',
        help_text='Admin / committee officer who reviewed and approved the restructure.',
    )
    reason = models.TextField(
        help_text='Detailed justification for modifying the original loan terms.',
    )
    restructure_type = models.CharField(
        max_length=30, choices=RESTRUCTURE_TYPE_CHOICES,
    )
    parameters = models.JSONField(
        default=dict, blank=True,
        help_text='Input parameters for the restructure calculation (e.g. new_term_months, new_rate, moratorium_months, accrue_interest).',
    )
    old_schedule_snapshot = models.JSONField(
        default=list, blank=True,
        help_text='JSON snapshot of repayment schedule entries prior to restructuring.',
    )
    new_schedule_snapshot = models.JSONField(
        default=list, blank=True,
        help_text='JSON snapshot of newly generated repayment schedule installments.',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='PENDING',
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text='Reason for rejection if the restructure was turned down.',
    )
    requested_at = models.DateTimeField(default=timezone.now)
    approved_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"Restructure #{self.pk} ({self.get_restructure_type_display()}) - Loan #{self.loan_id} [{self.get_status_display()}]"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.loan_id:
            if self.loan.status in ('cleared', 'written_off'):
                raise ValidationError(f"Cannot restructure a loan that is already {self.loan.get_status_display().lower()}.")
            if self.loan.balance <= Decimal('0.00'):
                raise ValidationError("Cannot restructure a loan with zero outstanding balance.")


class RepaymentSchedule(models.Model):
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name='schedules',
    )
    installment_number = models.PositiveIntegerField()
    due_date           = models.DateField()
    principal_amount   = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    interest_amount    = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    total_installment  = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total installment amount (principal + interest).',
    )
    paid_amount        = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    is_paid            = models.BooleanField(default=False)
    superseded_by      = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supersedes',
        help_text='Points to the new schedule row that replaced this entry after a restructure.',
    )
    restructure        = models.ForeignKey(
        LoanRestructure, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_schedules',
        help_text='The restructure event that created this schedule installment, if applicable.',
    )
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['installment_number', 'due_date']
        indexes = [
            models.Index(fields=['loan', 'is_paid']),
            models.Index(fields=['loan', 'due_date']),
        ]

    def __str__(self):
        status = "Paid" if self.is_paid else ("Superseded" if self.superseded_by_id else "Pending")
        return f"Loan #{self.loan_id} Installment #{self.installment_number} due {self.due_date}: KES {self.total_installment} ({status})"

    @property
    def is_superseded(self):
        return self.superseded_by_id is not None

