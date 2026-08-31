from django import template

from students.models import EnrolmentAgreement

register = template.Library()


@register.inclusion_tag("admin/recent_enrolments.html", takes_context=True)
def recent_enrolments(context, limit=5):
    enrolments = (
        EnrolmentAgreement.objects.select_related("student", "student__parent")
        .order_by("-agreed_at")[:limit]
    )
    return {
        "enrolments": enrolments,
    }