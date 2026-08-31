from django.contrib import admin
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.html import format_html
import uuid

from .models import (
    EmergencyContact,
    EnrolmentAgreement,
    Invoice,
    MedicalInfo,
    Parent,
    ProgressLog,
    ProgressReport,
    Session,
    Student,
)


# My Models for admin panel
class StudentInline(admin.TabularInline):
    model = Student
    extra = 0

class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0

class MedicalInfoInline(admin.StackedInline):
    model = MedicalInfo
    extra = 0

class EnrolmentAgreementInline(admin.StackedInline):
    model = EnrolmentAgreement
    fields = (
        "pays_in_advance",
        "pays_on_time",
        "understands_no_refund",
        "gives_24h_notice",
        "child_on_time",
        "confirm_terms",
        "confirms_official_contact",
        "additional_questions",
        "agreed_at",
    )
    readonly_fields = ("agreed_at",)
    extra = 0

class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0

class SessionInline(admin.TabularInline):
    model = Session
    extra = 0

class ProgressReportInline(admin.TabularInline):
    model = ProgressReport
    extra = 0

@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = (
        'parent_name', 'email', 'phone_number', 'created_at',
        'outstanding_balance', 'payment_due_date', 'status_badge',
    )
    search_fields = ('parent_name', 'email', 'phone_number')
    list_filter = ('reminder_sent',)
    inlines = [StudentInline]  # noqa: RUF012
    actions = ['send_fee_reminder', 'send_enrolment_link']

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.outstanding_balance <= 0:
            return format_html(
                '<span style="color:#15803d;font-weight:bold;">{label}</span>',
                label="✔ Paid",
            )
        if obj.is_overdue:
            return format_html(
                '<span style="color:#b91c1c;font-weight:bold;">{label}</span>',
                label="⚠️ OVERDUE",
            )
        return format_html(
            '<span style="color:#d97706;font-weight:bold;">{label}</span>',
            label="Pending",
        )

    @admin.action(description="Send fee reminder to selected parents")
    def send_fee_reminder(self, request, queryset):
        sent = 0
        for parent in queryset:
            if parent.is_overdue and parent.email:
                send_mail(
                    subject="Fees Reminder - Slough Tuition Centre",
                    message=(
                        f"Dear {parent.parent_name},\n\n"
                        f"This is a reminder that your outstanding balance of "
                        f"£{parent.outstanding_balance} was due on "
                        f"{parent.payment_due_date.strftime('%d %b %Y')}.\n\n"
                        "Please arrange payment at your earliest convenience. "
                        "Thank you.\n\nSlough Tuition Centre"
                    ),
                    from_email=None,
                    recipient_list=[parent.email],
                )
                parent.reminder_sent = True
                parent.save()
                sent += 1
        if sent:
            self.message_user(
                request, f"Fee reminder sent to {sent} parent(s)."
            )
        else:
            self.message_user(
                request, "No overdue parents with an email address selected."
            )

    @admin.action(description="Send enrolment form link to selected parents")
    def send_enrolment_link(self, request, queryset):
        sent = 0
        for parent in queryset:
            email = parent.email or (
                parent.user.email if parent.user else ""
            )
            if email:
                # Issue a fresh one-time token so the emailed link can only be
                # used by an invited parent (and only once).
                parent.enrolment_token = uuid.uuid4()
                parent.save(update_fields=["enrolment_token"])
                link = request.build_absolute_uri(
                    f"{reverse('enrol')}?token={parent.enrolment_token}"
                )
                send_mail(
                    subject="Complete your child's enrolment - Slough Tuition Centre",
                    message=(
                        f"Dear {parent.parent_name},\n\n"
                        "Thank you for choosing Slough Tuition Centre. To "
                        "complete your child's enrolment, please log in and "
                        "open your enrolment form here:\n\n"
                        f"{link}\n\n"
                        "This link is personal to you and can only be used once. "
                        "If you do not have an account yet, please register with "
                        "the email address this message was sent to first.\n\n"
                        "Slough Tuition Centre"
                    ),
                    from_email=None,
                    recipient_list=[email],
                )
                sent += 1
        if sent:
            self.message_user(
                request, f"Enrolment link sent to {sent} parent(s)."
            )
        else:
            self.message_user(
                request, "No selected parents have an email address."
            )

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'parent', 'year_group', 'school_name', 'created_at')
    search_fields = ('student_name', 'parent__parent_name', 'school_name')
    list_filter = ('year_group',)
    inlines = [
        InvoiceInline,
        SessionInline,
        ProgressReportInline,
        EmergencyContactInline,
        MedicalInfoInline,
        EnrolmentAgreementInline,
    ]  # noqa: RUF012

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('student', 'description', 'amount', 'due_date', 'paid')
    list_filter = ('paid',)

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'session_date', 'duration')
    list_filter = ('subject',)

@admin.register(ProgressReport)
class ProgressReportAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'grade', 'report_date')
    list_filter = ('subject',)

@admin.register(ProgressLog)
class ProgressLogAdmin(admin.ModelAdmin):
    list_display = ('parent', 'date', 'topic_covered', 'skill_rating')
    list_filter = ('skill_rating',)
    search_fields = ('parent__parent_name', 'topic_covered')

@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'relationship', 'phone_number', 'student')
    search_fields = ('full_name', 'student__student_name')

@admin.register(MedicalInfo)
class MedicalInfoAdmin(admin.ModelAdmin):
    list_display = ('student',)
    search_fields = ('student__student_name',)

@admin.register(EnrolmentAgreement)
class EnrolmentAgreementAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'pays_in_advance',
        'confirm_terms',
        'confirms_official_contact',
        'agreed_at',
    )
    search_fields = ('student__student_name',)
    