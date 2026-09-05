from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from .forms import MAX_ASSESSMENT_SUBJECTS, AssessmentForm, SessionForm
from .models import (
    Assessment,
    Centre,
    DeliveryType,
    Invoice,
    Parent,
    Session,
    Student,
    User,
)
from .pdf import build_assessment_pdf


def _subject_groups(form):
    """Package the form's subject blocks for the template loop.

    Each block is flagged `active` when it should start visible: the first
    block is always shown, and any later block that already holds a value or
    has an error is shown too (so edits / validation re-renders don't lose
    entered data). The rest are revealed on demand by the "+ Add subject"
    button."""
    groups = []
    for i in range(1, MAX_ASSESSMENT_SUBJECTS + 1):
        fields = {
            "year_group": form[f"year_group_{i}"],
            "subject": form[f"subject_{i}"],
            "marks": form[f"marks_{i}"],
            "max_marks": form[f"max_marks_{i}"],
        }
        populated = any(f.value() for f in fields.values())
        errored = any(f.errors for f in fields.values())
        groups.append(
            {
                "number": i,
                "active": i == 1 or populated or errored,
                **fields,
            }
        )
    return groups


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


def _scoped_queryset(user, model):
    """Scope any console query to the centres the staff user may see.

    Franchise rules:
      * Superuser, head-office staff, or a staff account with no centre -> can
        see ALL centres (returns an unfiltered queryset).
      * A franchisee staff account -> restricted to its own centre only.

    `model` may be one where `centre` is a direct FK (Student, PaymentPlan,
    Centre, User) or reached via `student__centre` (Session, Assessment,
    Invoice) / `students__centre` (Parent, the reverse of Student.centre).
    """
    qs = model.objects.all()
    centre = getattr(user, "centre", None)
    if user.is_superuser or centre is None or centre.is_head_office:
        return qs
    if model is Centre:
        return qs.filter(pk=centre.pk)
    if model in (Session, Assessment, Invoice):
        return qs.filter(student__centre=centre)
    if model is Parent:
        return qs.filter(students__centre=centre).distinct()
    return qs.filter(centre=centre)


def _visible_centres(user):
    """The Centre list a console user may operate on (all for head office)."""
    centre = getattr(user, "centre", None)
    if user.is_superuser or centre is None or centre.is_head_office:
        return Centre.objects.all()
    return Centre.objects.filter(pk=centre.pk)


def _visible_centre_ids(user):
    """Set of centre PKs visible to the user, or None to mean 'all'."""
    centre = getattr(user, "centre", None)
    if user.is_superuser or centre is None or centre.is_head_office:
        return None
    return {centre.pk}


@_console_required
def dashboard(request):
    today = date.today()
    week = date.today() + timedelta(days=7)

    sessions_today = _scoped_queryset(request.user, Session).filter(
        session_date=today
    ).select_related("student")
    upcoming = (
        _scoped_queryset(request.user, Session)
        .filter(session_date__gte=today, status="scheduled")
        .order_by("session_date", "start_time")
        .select_related("student")[:10]
    )
    scheduled_count = _scoped_queryset(request.user, Session).filter(status="scheduled").count()
    attended_count = _scoped_queryset(request.user, Session).filter(status="attended").count()
    students_count = _scoped_queryset(request.user, Student).count()
    assessments_count = _scoped_queryset(request.user, Assessment).count()
    visible_centres = _visible_centres(request.user)

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
            "visible_centres": visible_centres,
            "console_active": "dashboard",
        },
    )


@_console_required
def booking_hub(request):
    """Sub-module 1: bookable list — every student with their plan and the
    number of sessions left in their current block, so staff can book at a
    glance. Centre students show a finite remaining count; home tuition is
    billed per session and shows unlimited."""
    students = (
        _scoped_queryset(request.user, Student)
        .select_related("parent", "payment_plan", "centre")
        .order_by("student_name")
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
            "visible_centres": _visible_centres(request.user),
            "console_active": "booking",
        },
    )


@_console_required
def session_list(request):
    q = request.GET.get("q", "")
    status_filter = request.GET.get("status", "")
    sessions = _scoped_queryset(request.user, Session).select_related(
        "student", "student__centre"
    ).order_by("-session_date", "-start_time")
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
            "visible_centres": _visible_centres(request.user),
            "console_active": "sessions",
        },
    )


@_console_required
def session_create(request):
    initial = {}
    student_id = request.GET.get("student")
    if student_id:
        initial["student"] = student_id
    students_qs = _scoped_queryset(request.user, Student)
    form = SessionForm(initial=initial, student_queryset=students_qs)
    if request.method == "POST":
        form = SessionForm(request.POST, student_queryset=students_qs)
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
            "visible_centres": _visible_centres(request.user),
            "centre_ids": _visible_centre_ids(request.user),
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
    session = get_object_or_404(
        _scoped_queryset(request.user, Session), pk=pk
    )
    students_qs = _scoped_queryset(request.user, Student)
    form = SessionForm(instance=session, student_queryset=students_qs)
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session, student_queryset=students_qs)
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
            "visible_centres": _visible_centres(request.user),
            "centre_ids": _visible_centre_ids(request.user),
            "console_active": "sessions",
        },
    )


def _assessment_score(assessment):
    """Return (percentage, colour_flag) for an assessment.

    `percentage` is the score to display (or None when the assessment has no
    marks). `colour_flag` is one of 'emerald' / 'amber' / 'rose' / 'slate' so
    the template can pick the matching badge/progress-bar style.
    """
    if assessment.overall_percentage is not None:
        score = float(assessment.overall_percentage)
    else:
        pcts = [
            float(s.percentage)
            for s in assessment.subjects.all()
            if s.percentage is not None
        ]
        if not pcts:
            return None, "slate"
        score = sum(pcts) / len(pcts)
    if score >= 80:
        return score, "emerald"
    if score >= 60:
        return score, "amber"
    return score, "rose"


def _attach_subject_rows(assessments):
    """Attach `subject_rows` to each assessment (uses the prefetch cache)."""
    for a in assessments:
        a.subject_rows = list(a.subjects.all())
        a.subject_label = ", ".join(s.subject for s in a.subject_rows) or "Unmarked"


@_console_required
def assessment_list(request):
    assessments = list(
        _scoped_queryset(request.user, Assessment)
        .select_related("student", "student__centre")
        .prefetch_related("subjects")
        .order_by("-assessment_date")
    )
    _attach_subject_rows(assessments)
    for a in assessments:
        a.score_percentage, a.score_colour = _assessment_score(a)
    return render(
        request,
        "staff/assessments.html",
        {
            "assessments": assessments,
            "visible_centres": _visible_centres(request.user),
            "console_active": "assessments",
        },
    )


@_console_required
def assessment_create(request):
    students_qs = _scoped_queryset(request.user, Student)
    form = AssessmentForm(student_queryset=students_qs)
    if request.method == "POST":
        form = AssessmentForm(request.POST, student_queryset=students_qs)
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
            "subject_groups": _subject_groups(form),
            "visible_centres": _visible_centres(request.user),
            "centre_ids": _visible_centre_ids(request.user),
            "console_active": "assessments",
        },
    )


@_console_required
def student_list(request):
    students = _scoped_queryset(request.user, Student).select_related(
        "parent", "payment_plan", "centre"
    ).order_by("student_name")
    return render(
        request,
        "staff/students.html",
        {
            "students": students,
            "visible_centres": _visible_centres(request.user),
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


@_console_required
def assessment_edit(request, pk):
    assessment = get_object_or_404(
        _scoped_queryset(request.user, Assessment), pk=pk
    )
    students_qs = _scoped_queryset(request.user, Student)
    form = AssessmentForm(instance=assessment, student_queryset=students_qs)
    if request.method == "POST":
        form = AssessmentForm(
            request.POST, instance=assessment, student_queryset=students_qs
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Assessment updated.")
            return redirect("staff_student_assessments", pk=assessment.student_id)
    return render(
        request,
        "staff/assessment_form.html",
        {
            "form": form,
            "title": "Edit assessment",
            "subject_groups": _subject_groups(form),
            "visible_centres": _visible_centres(request.user),
            "centre_ids": _visible_centre_ids(request.user),
            "console_active": "assessments",
            "assessment": assessment,
        },
    )


@_console_required
def assessment_delete(request, pk):
    assessment = get_object_or_404(
        _scoped_queryset(request.user, Assessment), pk=pk
    )
    if request.method == "POST":
        student_pk = assessment.student_id
        assessment.delete()
        messages.success(request, "Assessment deleted.")
        return redirect("staff_student_assessments", pk=student_pk)
    return render(
        request,
        "staff/assessment_confirm_delete.html",
        {"assessment": assessment, "console_active": "assessments"},
    )


@_console_required
def student_assessments(request, pk):
    """Per-student assessment history: stats, score trend and per-subject
    breakdown, alongside the full edit/PDF/email list."""
    student = get_object_or_404(
        _scoped_queryset(request.user, Student), pk=pk
    )
    assessments = list(
        student.assessments.select_related("student", "student__centre")
        .prefetch_related("subjects")
        .order_by("-assessment_date")
    )
    _attach_subject_rows(assessments)
    for a in assessments:
        a.score_percentage, a.score_colour = _assessment_score(a)

    scored = [a for a in assessments if a.score_percentage is not None]
    avg_percentage = best_score = latest_score = None
    if scored:
        avg_percentage = sum(a.score_percentage for a in scored) / len(scored)
        best_score = max(a.score_percentage for a in scored)
        latest_score = scored[0].score_percentage

    # Chronological (oldest first) score trend for a mini bar chart.
    trend = [
        {
            "date": a.assessment_date,
            "score": a.score_percentage,
            "colour": a.score_colour,
            "subject_label": a.subject_label,
        }
        for a in reversed(scored)
    ]

    # Per-subject average + count across every recorded subject line,
    # sorted best-first.
    by_subject = {}
    for a in assessments:
        for s in a.subject_rows:
            if s.percentage is None:
                continue
            entry = by_subject.setdefault(s.subject, {"total": 0.0, "count": 0})
            entry["total"] += float(s.percentage)
            entry["count"] += 1
    subject_breakdown = [
        {
            "subject": label,
            "average": info["total"] / info["count"],
            "count": info["count"],
        }
        for label, info in by_subject.items()
    ]
    subject_breakdown.sort(key=lambda s: -s["average"])

    return render(
        request,
        "staff/assessment_history.html",
        {
            "student": student,
            "assessments": assessments,
            "avg_percentage": avg_percentage,
            "best_score": best_score,
            "latest_score": latest_score,
            "scored_count": len(scored),
            "trend": trend,
            "subject_breakdown": subject_breakdown,
            "visible_centres": _visible_centres(request.user),
            "console_active": "assessments",
        },
    )


@_console_required
def assessment_report(request, pk):
    """Item 7: download a clean, mobile-friendly one-page PDF report."""
    assessment = get_object_or_404(
        _scoped_queryset(request.user, Assessment), pk=pk
    )
    filename = f"assessment_{assessment.student_id}_{assessment.pk}.pdf"
    response = HttpResponse(
        build_assessment_pdf(assessment), content_type="application/pdf"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@_console_required
def assessment_email(request, pk):
    """Item 8: email the PDF report to the student's parent as an attachment."""
    assessment = get_object_or_404(
        _scoped_queryset(request.user, Assessment).select_related(
            "student__parent", "student", "student__centre"
        ),
        pk=pk,
    )
    parent = assessment.student.parent
    if not parent or not parent.email:
        messages.error(
            request, "No parent email on file to send the report to."
        )
        return redirect("staff_student_assessments", pk=assessment.student_id)
    subject = (
        f"Assessment report for {assessment.student.student_name} "
        f"- {assessment.subject_summary}"
    )
    body = render_to_string(
        "staff/assessment_email.txt",
        {"assessment": assessment, "parent": parent},
    )
    email = EmailMessage(subject=subject, body=body, to=[parent.email])
    email.attach(
        f"assessment_{assessment.student_id}.pdf",
        build_assessment_pdf(assessment),
        "application/pdf",
    )
    email.send()
    messages.success(request, f"Report emailed to {parent.email}.")
    return redirect("staff_student_assessments", pk=assessment.student_id)
