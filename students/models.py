from datetime import date

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
class Student(models.Model):
    parent = models.ForeignKey(
        Parent, 
        on_delete=models.CASCADE, 
        related_name="students",
    )
    student_name     = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True) 
    year_group    = models.CharField(max_length=50)
    school_name   = models.CharField(max_length=200, blank=True, default="")
    subjects      = models.JSONField(default=list, blank=True)
    support_needed = models.TextField(blank=True, default="")
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.student_name


# Invoice / Fee model
class Invoice(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    due_date = models.DateField()
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} ({self.student.student_name})"


# Session model
class Session(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    subject = models.CharField(max_length=100)
    session_date = models.DateField()
    duration = models.DurationField()
    notes = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.subject} - {self.session_date}"


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
