from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import mail_admins
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import EmergencyContact, MedicalInfo, Parent, Student
from .security import get_owned_queryset, raise_403_if_not_owned

from .forms import (
    ChildDetailUpdateForm,
    DuplicateSafePasswordResetForm,
    EmergencyContactForm,
    EnrolmentAgreementForm,
    LoginForm,
    MedicalInfoForm,
    ParentContactUpdateForm,
    ParentForm,
    StudentForm,
    UserRegistrationForm,
)


# Student and Parent views
def _display_name(user):
    """Address people by their full name rather than their email, falling
    back to the email (or username) only when no profile name exists."""
    if user.is_authenticated:
        parent = Parent.objects.filter(user=user).first()
        if parent and parent.parent_name.strip():
            return parent.parent_name.strip()
    return getattr(user, "email", None) or str(user)


def register_student(request):
    parent_form = ParentForm()
    student_form = StudentForm()

    if request.method == "POST":
        parent_form = ParentForm(request.POST)
        student_form = StudentForm(request.POST)

        if parent_form.is_valid() and student_form.is_valid():
            # Never create a second profile for a user that already owns one
            # / never bind this row to another user's account.
            if request.user.is_authenticated:
                if Parent.objects.filter(user=request.user).exists():
                    messages.error(
                        request,
                        "You already have a profile. Please use 'New student "
                        "enrolment' from your account page instead.",
                    )
                    return redirect("my_account")
                parent = parent_form.save(commit=False)
                parent.user = request.user
                parent.save()
            else:
                # Duplicate-safe: reuse an existing parent row with the same
                # email instead of silently creating a second record for the
                # same person (the usual cause of duplicated accounts).
                email = (parent_form.cleaned_data.get("email") or "").strip().lower()
                existing = Parent.objects.filter(
                    email__iexact=email
                ).first() if email else None
                if existing:
                    parent = existing
                    # Refresh display fields from the new submission but keep
                    # the row (and any linked user/children) intact.
                    for field in ("parent_name", "phone_number", "address"):
                        value = parent_form.cleaned_data.get(field)
                        if value:
                            setattr(parent, field, value)
                    parent.save()
                else:
                    parent = parent_form.save()
            student = student_form.save(commit=False)
            student.parent = parent
            student.save()
            messages.success(
                request,
                f"Thank you, {parent.parent_name}! We have received your registration for {student.student_name}. We will be in touch soon to discuss the support your child needs.",
            )
            return redirect("home")

    return render(
        request,
        "core/home.html",
        {
            "parent_form": parent_form,
            "student_form": student_form,
        },
    )


def register(request):
    initial_email = request.POST.get("email") or request.GET.get("email") or ""
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                f"Welcome, {_display_name(user)}! Your account has been created.",
            )
            return redirect(_safe_next(request, reverse("home")))
    else:
        form = UserRegistrationForm(initial={"email": initial_email})

    return render(
        request,
        "students/register.html",
        {
            "form": form,
            "next_url": _safe_next(request, ""),
        },
    )


def login_view(request):
    form = LoginForm(request=request)
    if request.method == "POST":
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(
                request,
                f"Welcome back, {_display_name(user)}!",
            )
            # Option B: land parents straight on their account page, but keep
            # the `next` target (staff/admin consoles) and fall back to home
            # for users without a parent profile.
            landing = _safe_next(request, "")
            if not landing:
                if Parent.objects.filter(user=user).exists():
                    landing = reverse("my_account")
                else:
                    landing = reverse("home")
            return redirect(landing)
    return render(
        request,
        "students/login.html",
        {
            "form": form,
            "next_url": _safe_next(request, ""),
        },
    )


def reset_password(request):
    """Duplicate-safe parent password reset entry point.

    Uses DuplicateSafePasswordResetForm which refuses to send when an email
    maps to more than one account/parent — the centre must reconcile first
    rather than risk resetting the wrong person. We always show the neutral
    'done' page (no account enumeration), but log duplicates for staff.
    """
    form = DuplicateSafePasswordResetForm(request.POST or None)
    if form.is_valid():
        if form.ambiguity:
            import logging

            logger = logging.getLogger("students.passwordreset")
            logger.warning(
                "Duplicate account/parent for reset email %s (%s user(s)); "
                "sent no reset link. Centre must reconcile.",
                form.cleaned_data.get("email"),
                form.user_count or "?",
            )
            # Mirrors done-page to avoid revealing whether the email exists.
            return redirect("password_reset_done")
        # Send a real reset email to the single matching user.
        form.save(
            request=request,
            use_https=request.is_secure(),
            subject_template_name="registration/password_reset_subject.txt",
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
        )
        return redirect("password_reset_done")
    return render(
        request,
        "registration/password_reset_form.html",
        {"form": form},
    )


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


@login_required
def my_account(request):
    parent = get_owned_queryset(Parent, "user", request).first()
    students = []
    if parent:
        students = parent.students.prefetch_related(
            "invoices", "sessions", "progress_reports"
        )
    return render(
        request,
        "students/my_account.html",
        {
            "parent": parent,
            "students": students,
        },
    )


def _get_owned_student_or_403(request, pk):
    """Return a student whose parent account belongs to the logged-in user,
    otherwise 403. This is the ownership gate for every parent-side edit."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    return get_object_or_404(
        Student.objects.filter(parent__user=request.user),
        pk=pk,
    )


@login_required
def edit_parent(request):
    """Parent self-service: update their own contact details (name is
    centre-controlled and therefore not editable here)."""
    parent = get_owned_queryset(Parent, "user", request).first()
    if parent is None:
        messages.error(request, "No parent profile found for your account.")
        return redirect("my_account")
    form = ParentContactUpdateForm(instance=parent)
    if request.method == "POST":
        form = ParentContactUpdateForm(request.POST, instance=parent)
        if form.is_valid():
            parent = form.save()
            # Keep login and contact email in sync: the account uses email as
            # its username, so update the linked User's email to match.
            if parent.user_id:
                new_email = (parent.email or "").strip().lower()
                if (parent.user.email or "").strip().lower() != new_email:
                    parent.user.email = new_email
                    parent.user.save(update_fields=["email"])
            messages.success(request, "Your contact details have been updated.")
            return redirect("my_account")
    return render(
        request,
        "students/edit_parent.html",
        {"form": form, "parent": parent},
    )


@login_required
def edit_student(request, pk):
    """Parent self-service: update safe child details (school, DOB, support).
    Name, year group, subjects and all billing stay centre-controlled."""
    student = _get_owned_student_or_403(request, pk)
    form = ChildDetailUpdateForm(instance=student)
    if request.method == "POST":
        form = ChildDetailUpdateForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Details for {student.student_name} have been updated."
            )
            return redirect("my_account")
    return render(
        request,
        "students/edit_student.html",
        {"form": form, "student": student},
    )


@login_required
def edit_emergency(request, pk):
    """Parent self-service: keep emergency contact current for their child."""
    student = _get_owned_student_or_403(request, pk)
    contact = EmergencyContact.objects.filter(student=student).first()
    form = EmergencyContactForm(instance=contact)
    if request.method == "POST":
        form = EmergencyContactForm(request.POST, instance=contact)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.student = student
            obj.save()
            messages.success(
                request, "Emergency contact updated for " + student.student_name + "."
            )
            return redirect("my_account")
    return render(
        request,
        "students/edit_emergency.html",
        {"form": form, "student": student},
    )


@login_required
def edit_medical(request, pk):
    """Parent self-service: keep medical / special-requirements info current."""
    student = _get_owned_student_or_403(request, pk)
    medical = MedicalInfo.objects.filter(student=student).first()
    form = MedicalInfoForm(instance=medical)
    if request.method == "POST":
        form = MedicalInfoForm(request.POST, instance=medical)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.student = student
            obj.save()
            messages.success(
                request, "Medical info updated for " + student.student_name + "."
            )
            return redirect("my_account")
    return render(
        request,
        "students/edit_medical.html",
        {"form": form, "student": student},
    )


def enrol(request):
    """6-step enrolment wizard: student, parent, emergency, medical, questions, agreement.

    Invite-gated: the view only loads when a valid one-time enrolment_token
    belonging to the logged-in parent is supplied (the token the centre emails
    out). Unregistered parents who received an invite are routed through a
    quick register-and-enrol flow with their email pre-filled.
    """
    token = request.GET.get("token") or request.POST.get("token") or ""
    parent = _parent_by_token(token)
    if parent is None:
        messages.error(
            request,
            "That enrolment link is invalid or has already been used. "
            "Please ask the centre to send you a fresh link.",
        )
        return redirect("my_account" if request.user.is_authenticated else "home")

    if not request.user.is_authenticated:
        # Register-and-enrol: revisit the same token link right after sign-up.
        next_path = f"{reverse('enrol')}?token={token}"
        return redirect(
            f"{reverse('register')}?email={quote(parent.email or '')}"
            f"&next={quote(next_path)}"
        )

    if not _may_use_invite(request, parent):
        messages.error(
            request,
            "This enrolment link was sent to a different email address. "
            "Please log in with the email address the link was sent to.",
        )
        return redirect("my_account")

    # A valid invite claimed with the matching email links the account now, so
    # the parent's dashboard works even if they finish the form later.
    if parent.user_id is None:
        parent.user = request.user
        parent.save(update_fields=["user"])

    parent_form = ParentForm()
    student_form = StudentForm()
    emergency_form = EmergencyContactForm()
    medical_form = MedicalInfoForm()
    agreement_form = EnrolmentAgreementForm()

    if request.method == "POST":
        parent_form = ParentForm(request.POST)
        student_form = StudentForm(request.POST)
        emergency_form = EmergencyContactForm(request.POST)
        medical_form = MedicalInfoForm(request.POST)
        agreement_form = EnrolmentAgreementForm(request.POST)

        all_valid = (
            parent_form.is_valid()
            and student_form.is_valid()
            and emergency_form.is_valid()
            and medical_form.is_valid()
            and agreement_form.is_valid()
        )

        if all_valid:
            with transaction.atomic():
                student = student_form.save(commit=False)
                student.parent = parent
                student.save()

                emergency = emergency_form.save(commit=False)
                emergency.student = student
                emergency.save()

                medical = medical_form.save(commit=False)
                medical.student = student
                medical.save()

                agreement = agreement_form.save(commit=False)
                agreement.student = student
                agreement.save()

                # One-time link: consume the token so it cannot be reused.
                parent.enrolment_token = None
                parent.save(update_fields=["enrolment_token"])

            _notify_admins_of_enrolment(parent, student)
            messages.success(
                request,
                f"Thank you, {parent.parent_name}! We have received {student.student_name}'s "
                "enrolment and will be in touch soon.",
            )
            return redirect("my_account")

    return render(
        request,
        "students/enrol.html",
        {
            "parent_form": parent_form,
            "student_form": student_form,
            "emergency_form": emergency_form,
            "medical_form": medical_form,
            "agreement_form": agreement_form,
            "token": token,
            "invited_parent": parent,
            "step_labels": ["Student", "Parent", "Emergency", "Medical", "Questions", "Agreement"],
            "form_errors": any(
                f.errors
                for f in (parent_form, student_form, emergency_form, medical_form, agreement_form)
            ),
            # On a failed POST, restart the wizard on the step with the FIRST
            # error so the parent does not get bounced back to page 1 to re-fill.
            "initial_step": _first_error_step(
                student_form, parent_form, emergency_form, medical_form, agreement_form
            ),
        },
    )


def _parent_by_token(token):
    """Return the Parent row behind an invite token, or None if unknown."""
    if not token:
        return None
    try:
        return Parent.objects.get(enrolment_token=token)
    except Parent.DoesNotExist:
        return None


def _may_use_invite(request, parent):
    """Identity check: the invite may only be used by the account it belongs to."""
    if parent.user_id == request.user.id:
        return True
    return (
        parent.user_id is None
        and parent.email
        and parent.email.lower() == request.user.email.lower()
    )


def _safe_next(request, default):
    """Return the caller's redirect target only if it is a same-site path."""
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=False
    ):
        return nxt
    return default


def _notify_admins_of_enrolment(parent, student):
    subject = f"New enrolment received: {student.student_name}"
    message = (
        f"A new enrolment has been completed.\n\n"
        f"Parent/guardian: {parent.parent_name}\n"
        f"Contact: {parent.email or parent.phone_number}\n"
        f"Child: {student.student_name}\n"
        f"Year group: {student.year_group}\n"
        f"School: {student.school_name or 'Not provided'}\n"
        f"Subjects: {', '.join(student.subjects) if student.subjects else 'Not provided'}\n\n"
        "View it in the admin panel under Students."
    )
    mail_admins(subject=subject, message=message)


def _first_error_step(
    student_form, parent_form, emergency_form, medical_form, agreement_form
):
    """Return the number of the earliest step that has a form error, else 1."""
    # additional_questions lives on step 5, the agreement checkboxes on step 6.
    if "additional_questions" in agreement_form.errors:
        return 5
    for step, form in (
        (1, student_form),
        (2, parent_form),
        (3, emergency_form),
        (4, medical_form),
        (6, agreement_form),
    ):
        if form.errors:
            return step
    return 1
