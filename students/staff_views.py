from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AssessmentForm, SessionForm
from .models import Assessment, Session, Student


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
    form = SessionForm()
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            session = form.save()
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
