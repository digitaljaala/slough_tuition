from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AssessmentForm, SessionForm
from .models import Assessment, DeliveryType, Invoice, Parent, Session, Student, User


def _is_console_user(user):
    """Only staff (incl. superusers) may enter the console."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(
        name="Staff (sessions & assessments)"
    ).exists()


_console_required = user_passes_test(_is_console_user, login_url="login")


def _is_superuser(user):
    return user.is_authenticated and user.is_superuser


_superuser_required = user_passes_test(_is_superuser, login_url="login")


@_console_required
def dashboard(request):
    today = date.today()
    week = date.today() + timedelta(days=7)

    sessions_today = Session.objects.filter(session_date=today).select_related("student")
    upcoming = (
        Session.objects.filter(session_date__gte=today, status="scheduled")
        .order_by("session_date", "start_time")
        .select_related("student")[:10]
    )
    scheduled_count = Session.objects.filter(status="scheduled").count()
    attended_count = Session.objects.filter(status="attended").count()
    students_count = Student.objects.count()
    assessments_count = Assessment.objects.count()

    return render(
        request,
        "staff/dashboard.html",
        {
            "today": today,
            "sessions_today": sessions_today,
            "upcoming": upcoming,
            "week": week,
            "scheduled_count": scheduled_count,
            "attended_count": attended_count,
            "students_count": students_count,
            "assessments_count": assessments_count,
            "console_active": "dashboard",
        },
    )


@_console_required
def booking_hub(request):
    """Sub-module 1: bookable list — every student with their plan and the
    number of sessions left in their current block, so staff can book at a
    glance. Centre students show a finite remaining count; home tuition is
    billed per session and shows unlimited."""
    students = Student.objects.select_related("parent", "payment_plan").order_by(
        "student_name"
    )
    low_count = sum(
        1 for s in students if s.remaining_sessions is not None and s.remaining_sessions <= 2
    )
    return render(
        request,
        "staff/booking_hub.html",
        {
            "students": students,
            "low_count": low_count,
            "console_active": "booking",
        },
    )


@_console_required
def session_list(request):
    q = request.GET.get("q", "")
    status_filter = request.GET.get("status", "")
    sessions = Session.objects.select_related("student").order_by(
        "-session_date", "-start_time"
    )
    if status_filter:
        sessions = sessions.filter(status=status_filter)
    if q:
        sessions = sessions.filter(student__student_name__icontains=q)

    return render(
        request,
        "staff/sessions.html",
        {
            "sessions": sessions,
            "q": q,
            "status_filter": status_filter,
            "status_choices": Session.SessionStatus.choices,
            "console_active": "sessions",
        },
    )


@_console_required
def session_create(request):
    initial = {}
    student_id = request.GET.get("student")
    if student_id:
        initial["student"] = student_id
    form = SessionForm(initial=initial)
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            session = form.save()
            _apply_billing_for_session(session)
            messages.success(
                request,
                f"Session booked for {session.student.student_name} on "
                f"{session.session_date}.",
            )
            return redirect("staff_session_list")
    return render(
        request,
        "staff/session_form.html",
        {
            "form": form,
            "title": "Book a session",
            "console_active": "sessions",
        },
    )


def _apply_billing_for_session(session):
    """Apply billing when a session is booked.

    Sub-module 2: centre students pay in fixed blocks, so each booked session
    consumes one session from the current block.
    Sub-module 3: home tuition is billed per session, so booking creates a
    per-session invoice line (with the one-off assessment fee if it's the
    student's first invoice)."""
    student = session.student
    if student.delivery_type == DeliveryType.CENTRE:
        student.sessions_used_in_block += 1
        student.save(update_fields=["sessions_used_in_block"])
    elif student.delivery_type == DeliveryType.HOME:
        Invoice.for_home_session(session)


@_console_required
def session_edit(request, pk):
    session = get_object_or_404(Session, pk=pk)
    form = SessionForm(instance=session)
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Updated session for {session.student.student_name}."
            )
            return redirect("staff_session_list")
    return render(
        request,
        "staff/session_form.html",
        {
            "form": form,
            "title": "Edit session",
            "session": session,
            "console_active": "sessions",
        },
    )


@_console_required
def assessment_list(request):
    assessments = Assessment.objects.select_related("student").order_by(
        "-assessment_date"
    )
    return render(
        request,
        "staff/assessments.html",
        {
            "assessments": assessments,
            "console_active": "assessments",
        },
    )


@_console_required
def assessment_create(request):
    form = AssessmentForm()
    if request.method == "POST":
        form = AssessmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Assessment recorded.")
            return redirect("staff_assessment_list")
    return render(
        request,
        "staff/assessment_form.html",
        {
            "form": form,
            "title": "Record an assessment",
            "console_active": "assessments",
        },
    )


@_console_required
def student_list(request):
    students = Student.objects.select_related("parent", "payment_plan").order_by(
        "student_name"
    )
    return render(
        request,
        "staff/students.html",
        {
            "students": students,
            "console_active": "students",
        },
    )


@_superuser_required
def staff_reset_parent(request):
    """Superuser tool: find a parent (even if they lost their email) and set a
    fresh password for their login account. Creates a login account only when
    the parent had none and their email is not already someone's login."""
    q = request.GET.get("q", "").strip()
    results = Parent.objects.none()
    if q:
        results = (
            Parent.objects.filter(
                Q(parent_name__icontains=q) | Q(email__icontains=q)
            )
            .select_related("user")
            .order_by("parent_name")
        )

    if request.method == "POST":
        parent_id = request.POST.get("parent_id")
        password = request.POST.get("password1", "")
        parent = get_object_or_404(Parent, pk=parent_id)
        try:
            validate_password(password, parent.user or User(email=parent.email or ""))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(f"{request.path}?q={parent.email}")

        if parent.user_id:
            user = parent.user
        elif parent.email:
            taken = User.objects.filter(email__iexact=parent.email.strip()).exists()
            if taken:
                messages.error(
                    request,
                    f"A login account already exists for {parent.email}. "
                    f"Duplicate prevented — do not create a second account.",
                )
                return redirect(f"{request.path}?q={parent.email}")
            user = User.objects.create_user(
                email=parent.email.strip(), password=password
            )
            parent.user = user
            parent.save()
        else:
            messages.error(
                request,
                "This parent has no email on file, so no login account can be created.",
            )
            return redirect(f"{request.path}?q={parent.email}")

        user.set_password(password)
        user.save()
        messages.success(
            request,
            f"Password reset for {parent.parent_name}. Login email: {user.email}",
        )
        return redirect(f"{request.path}?q={parent.email}")

    return render(
        request,
        "staff/reset_parent.html",
        {
            "q": q,
            "results": results,
            "console_active": "parents",
        },
    )
