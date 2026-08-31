"""Reportlab-backed PDF generation for assessment reports.

Kept to a single page so it prints cleanly and reads well on a phone/email
attachment. No system dependencies (reportlab is pure Python), so it works on
the same Windows/pip-only setup as the rest of the project.
"""

from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_TEAL = colors.HexColor("#36827F")
_INK = colors.HexColor("#262322")
_MUTED = colors.HexColor("#64748B")
_RULE = colors.HexColor("#E2E8F0")


def _wrap(c, text, x, y, max_width, font, size, leading):
    """Draw wrapped text, returning the y position just below the block."""
    c.setFont(font, size)
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if c.stringWidth(trial, font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_assessment_pdf(assessment, title="Assessment Report"):
    """Render a single assessment as a tidy one-page PDF and return bytes."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    x = margin
    y = height - margin

    # --- Header band ---
    c.setFillColor(_TEAL)
    c.roundRect(margin - 4 * mm, height - 28 * mm, width - 2 * margin + 8 * mm, 24 * mm, 3 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(x, height - 18 * mm, title)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#D7F0EE"))
    centre = "Slough Tuition Centre"
    if hasattr(settings, "STC_CENTRE_NAME"):
        centre = getattr(settings, "STC_CENTRE_NAME", centre)
    c.drawRightString(width - margin, height - 18 * mm, centre)

    y -= 34 * mm

    # --- Student & parent block ---
    stu = assessment.student
    parent = stu.parent
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(x, y, "STUDENT")
    y -= 4 * mm
    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, stu.student_name)
    c.setFont("Helvetica", 9)
    y -= 4.5 * mm
    school = stu.school_name or "—"
    year = stu.year_group or "—"
    c.drawString(x, y, f"Year {year}   ·   {school}")

    if parent:
        px = width - margin - 70 * mm
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(px, height - 28 * mm - 4 * mm, "PARENT")
        c.setFillColor(_INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(px, height - 28 * mm - 8.5 * mm, parent.parent_name)
        if parent.email:
            c.setFont("Helvetica", 8)
            c.drawString(px, height - 28 * mm - 12 * mm, parent.email)
        if parent.phone_number:
            c.setFont("Helvetica", 8)
            c.drawString(px, height - 28 * mm - 15.5 * mm, parent.phone_number)

    y -= 12 * mm
    c.setStrokeColor(_RULE)
    c.setLineWidth(0.5)
    c.line(x, y, width - margin, y)
    y -= 10 * mm

    # --- Assessment details ---
    rows = [
        ("Subject", assessment.subject),
        ("Assessment date", assessment.assessment_date.strftime("%d %B %Y") if assessment.assessment_date else "—"),
        ("Result", _result_text(assessment)),
    ]
    if assessment.topics:
        rows.append(("Topics covered", assessment.topics))
    for label, value in rows:
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, y, label.upper())
        c.setFillColor(_INK)
        c.setFont("Helvetica", 10.5)
        y -= 4.5 * mm
        y = _wrap(c, value, x, y, width - 2 * margin, "Helvetica", 10.5, 4.5 * mm)
        y -= 5 * mm

    # --- Tutor notes ---
    if assessment.tutor_notes.strip():
        y -= 2 * mm
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, y, "TUTOR NOTES")
        y -= 4.5 * mm
        c.setFillColor(_INK)
        y = _wrap(c, assessment.tutor_notes, x, y, width - 2 * margin, "Helvetica", 10.5, 4.5 * mm)

    # --- Footer ---
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(x, 12 * mm, f"Generated {__import__('datetime').date.today():%d %B %Y} · Slough Tuition Centre")

    c.showPage()
    c.save()
    return buf.getvalue()


def _result_text(assessment):
    if assessment.marks is None:
        return "Not yet marked"
    if assessment.max_marks:
        mark_str = f"{assessment.marks} / {assessment.max_marks}"
        if assessment.percentage is not None:
            mark_str += f"  ·  {assessment.percentage:g}%"
        return mark_str
    if assessment.percentage is not None:
        return f"{assessment.percentage:g}%"
    return str(assessment.marks)
