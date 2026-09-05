from datetime import date
from decimal import Decimal

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

# User manager

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)    

# User class
class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    objects = UserManager()
    USERNAME_FIELD ='email'
    REQUIRED_FIELDS = []

    # The centre a staff/tutor account belongs to. Head-office staff may see
    # all centres; a franchisee staff member is locked to their own centre.
    centre = models.ForeignKey(
        "Centre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
        help_text="The centre this staff account is tied to (null for head-office/global staff).",
    )

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        related_name="student_users",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name='user permissions',
        blank=True,
        related_name="student_users",


    )

    def __str__(self):
        return self.email

    @property
    def is_console_staff(self):
        """Staff (or superuser) who may use the bespoke staff console."""
        if self.is_superuser:
            return True
        return self.groups.filter(
            name="Staff (sessions & assessments)"
        ).exists()


# Parent Model 
class Parent(models.Model):
    parent_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    relationship_to_student = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.OneToOneField(
        "User", 
        on_delete=models.CASCADE,
        related_name="parent",
        null=True,
        blank=True,
    )
    # Fee tracking fields
    outstanding_balance = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )
    payment_due_date = models.DateField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    # One-time invitation token emailed by the centre so /enrol/ is invoke-only.
    enrolment_token = models.UUIDField(null=True, blank=True, unique=True)

    @property
    def is_overdue(self):
        if self.outstanding_balance > 0 and self.payment_due_date:
            return date.today() > self.payment_due_date
        return False

    def __str__(self):
        return self.parent_name

# Student Model with Parent one to many relatioship
class DeliveryType(models.TextChoices):
    CENTRE = "centre", "Centre"
    HOME = "home", "Home tuition"


class Centre(models.Model):
    """A tuition location in the franchise.

    The main centre at Chalvey is the head office (franchisor); other centres
    (e.g. Manor Park) are franchisees. The head office can see every centre's
    data; a franchisee staff account only ever sees its own centre.

    `session_slots` stores the centre's recurring timetable as a JSON list of
    blocks, e.g. [{"days": ["Sat","Sun"], "start": "10:00", "end": "12:00"}].
    Each new franchise location just gets its own Centre record.
    """

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    address = models.TextField(blank=True, default="")
    is_head_office = models.BooleanField(
        default=False,
        help_text="Head office (franchisor) may view every centre; franchisees see only their own.",
    )
    session_slots = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def is_franchisee(self):
        return not self.is_head_office



class PaymentPlan(models.Model):
    """One flexible model for ALL billing arrangements.

    Centre block, home tuition, and any negotiated custom deal are all just
    instances of this single model. There are no hard-coded pricing formulas;
    every payment plan is configurable and every price can be overridden.
    """

    name = models.CharField(max_length=150)
    centre = models.ForeignKey(
        Centre,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_plans",
        help_text="Centre this plan belongs to; null = plan is shared by all centres.",
    )
    applies_to = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.CENTRE,
        help_text="Which delivery type this plan applies to.",
    )
    sessions_per_payment = models.PositiveIntegerField(
        default=8,
        help_text="Sessions covered by one payment. Centre block = 8, home = 1.",
    )
    base_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("175.00"),
        help_text="Auto price for one payment (e.g. £175 for an 8-session block).",
    )
    assessment_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("25.00"),
        help_text="One-off assessment fee charged on first payment (0 if none).",
    )
    custom_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional override used instead of base_price (e.g. a discount or custom deal).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def effective_price(self):
        """The amount actually charged for one payment of this plan."""
        return self.custom_price if self.custom_price is not None else self.base_price

    def __str__(self):
        pricing = f"{self.effective_price():.2f}"
        if self.custom_price is not None:
            pricing = f"{pricing} (was {self.base_price:.2f})"
        return f"{self.name} ({self.sessions_per_payment}/£{pricing})"


class Student(models.Model):
    parent = models.ForeignKey(
        Parent, 
        on_delete=models.CASCADE, 
        related_name="students",
    )
    centre = models.ForeignKey(
        Centre,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        help_text="The centre this student attends. Determines venue, pricing and which staff can see them.",
    )
    student_name     = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True) 
    year_group    = models.CharField(max_length=50)
    school_name   = models.CharField(max_length=200, blank=True, default="")
    subjects      = models.JSONField(default=list, blank=True)
    support_needed = models.TextField(blank=True, default="")
    # Billing foundation
    delivery_type  = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.CENTRE,
        help_text="Centre tuition or home tuition — determines pricing.",
    )
    payment_plan = models.ForeignKey(
        PaymentPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        help_text="The payment plan this student is billed under.",
    )
    # Number of sessions already consumed within the student's current block.
    # Reset to 0 when a new block is paid for (billing module).
    sessions_used_in_block = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.student_name

    @property
    def block_size(self):
        """Sessions covered by one payment for this student."""
        if self.payment_plan:
            return self.payment_plan.sessions_per_payment
        return 8

    @property
    def remaining_sessions(self):
        """How many sessions remain in the current block.

        Centre tuition is sold in fixed blocks, so consumption is limited. Home
        tuition is billed per session and has no fixed block, so it is unlimited.
        Returns None (meaning unlimited) for home tuition.
        """
        if self.delivery_type != DeliveryType.CENTRE:
            return None
        return max(self.block_size - self.sessions_used_in_block, 0)


# ---------------------------------------------------------------------------
# Billing foundation (Module 1)
# ---------------------------------------------------------------------------

# Invoice / Fee model
class Invoice(models.Model):
    class InvoiceType(models.TextChoices):
        BLOCK = "block", "Session block"
        SESSION = "session", "Home session"
        ASSESSMENT = "assessment", "Assessment fee"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.BLOCK,
    )
    plan = models.ForeignKey(
        PaymentPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        help_text="The payment plan this invoice was generated from (if any).",
    )
    description = models.CharField(max_length=200)
    # Auto-computed amount before any manual override.
    base_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    # The amount the parent is actually charged - edit this to apply a
    # discount / custom price. Defaults to base_amount.
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    custom_note = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Optional note explaining a custom price / discount (e.g. 'sibling discount').",
    )
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} ({self.student.student_name})"

    @classmethod
    def for_home_session(cls, session):
        """Sub-module 3: generate a per-session invoice line when a home
        tuition session is booked. Home is billed per session at the plan's
        effective (possibly custom-overridden) price, plus any assessment fee
        if the student has no prior invoice yet."""
        student = session.student
        plan = student.payment_plan
        if plan is None:
            raise ValueError("Home student has no payment plan to bill against.")
        amount = plan.effective_price()
        assessment_fee = plan.assessment_fee
        # One-off assessment fee is charged on the first-ever invoice only.
        existing = cls.objects.filter(student=student).exists()
        description = f"Home tuition session ({session.session_date})"
        if not existing and assessment_fee and assessment_fee > 0:
            amount += assessment_fee
            description += f" + assessment fee £{assessment_fee:.2f}"
        return cls.objects.create(
            student=student,
            invoice_type=cls.InvoiceType.SESSION,
            plan=plan,
            description=description,
            base_amount=amount,
            amount=amount,
            due_date=session.session_date,
        )


# Session model
class Session(models.Model):
    class SessionStatus(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        ATTENDED = "attended", "Attended"
        MISSED = "missed", "Missed"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    subject = models.CharField(max_length=100)
    session_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True, help_text="Optional start time.")
    duration = models.DurationField()
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.SCHEDULED,
    )
    tutor = models.CharField(max_length=150, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["session_date", "start_time"]

    def __str__(self):
        return f"{self.subject} - {self.session_date}"


# Assessment model: raw marking data that feeds into ProgressReport.
#
# One assessment can hold up to eight distinct subjects, each recorded as its
# own AssessmentSubject line (year/class + subject + marks). The year/class and
# the subject are recorded per line so a single assessment can mix, e.g.,
# "Year 8 Maths" with "Year 9 English" without conflating the two.
class Assessment(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    assessment_date = models.DateField()
    tutor_notes = models.TextField(blank=True, default="")
    # Average of every recorded subject's percentage, recomputed on save.
    overall_percentage = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )

    class Meta:
        ordering = ["assessment_date"]

    def __str__(self):
        summary = self.subject_summary
        return f"{self.student.student_name} - {summary} ({self.assessment_date})"

    @property
    def subject_summary(self):
        names = [s.subject for s in self.subjects.all()]
        return ", ".join(names) if names else "Unmarked"

    def recompute_overall(self):
        """Average the per-subject percentages into `overall_percentage`.

        Subjects that have not been marked yet (no percentage) are ignored.
        Returns the computed value (or None when nothing is marked)."""
        pcts = [s.percentage for s in self.subjects.all() if s.percentage is not None]
        if not pcts:
            self.overall_percentage = None
        else:
            avg = sum(pcts) / Decimal(len(pcts))
            self.overall_percentage = avg.quantize(Decimal("0.1"))
        return self.overall_percentage


# A single subject line within an assessment (1-8 per assessment).
class AssessmentSubject(models.Model):
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    # "Year / Class" (e.g. "Year 8", "GCSE") recorded alongside the subject.
    year_group = models.CharField(max_length=50, blank=True, default="")
    subject = models.CharField(max_length=100)
    max_marks = models.PositiveIntegerField(null=True, blank=True)
    marks = models.PositiveIntegerField(null=True, blank=True)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.assessment.student.student_name} - {self.subject}"


# Progress model
class ProgressReport(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="progress_reports",
    )
    subject = models.CharField(max_length=100)
    grade = models.CharField(max_length=20)
    comments = models.TextField(blank=True, default="")
    report_date = models.DateField()

    def __str__(self):
        return f"{self.student.student_name} - {self.subject} ({self.grade})"


# Progress Log model (linked to Parent, weekly tracking)
class ProgressLog(models.Model):
    SKILL_RATINGS = [
        (1, "1 - Needs improvement"),
        (2, "2 - Developing"),
        (3, "3 - Satisfactory"),
        (4, "4 - Good"),
        (5, "5 - Excellent"),
    ]

    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="progress_logs",
    )
    date = models.DateField()
    topic_covered = models.CharField(max_length=200)
    skill_rating = models.IntegerField(choices=SKILL_RATINGS)
    tutor_comments = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.parent.parent_name} - {self.topic_covered} ({self.date})"


# Carefully collected at enrolment (Step 3) - emergency contact for a child
class EmergencyContact(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="emergency_contacts",
    )
    full_name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=30)

    def __str__(self):
        return f"{self.full_name} ({self.relationship}) - {self.student.student_name}"


# Medical / special requirements (Step 4)
class MedicalInfo(models.Model):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="medical_info",
    )
    details = models.TextField(
        help_text="Health, allergies, conditions, learning/behavioural needs, medications. Enter N/A if none."
    )

    def __str__(self):
        return f"Medical info - {self.student.student_name}"


# Payment & attendance agreement + final confirmations (Step 6)
class EnrolmentAgreement(models.Model):
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="agreement",
    )
    pays_in_advance = models.BooleanField(default=False, verbose_name="I understand all payments are made in advance")
    pays_on_time = models.BooleanField(default=False, verbose_name="I understand missed payments may pause sessions")
    understands_no_refund = models.BooleanField(default=False, verbose_name="I understand the no-refund policy")
    gives_24h_notice = models.BooleanField(default=False, verbose_name="I will give 24 hours' notice for absences")
    child_on_time = models.BooleanField(default=False, verbose_name="I will ensure my child arrives and is collected on time")
    confirm_terms = models.BooleanField(default=False, verbose_name="I confirm I have read and agree to all terms")
    confirms_official_contact = models.BooleanField(
        default=False,
        verbose_name="I confirm I will only use the official STC contact number",
    )
    additional_questions = models.TextField(
        blank=True,
        default="",
        verbose_name="Questions, concerns, or special requests for STC (optional)",
    )
    agreed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Agreement - {self.student.student_name}"
