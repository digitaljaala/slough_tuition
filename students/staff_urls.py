from django.urls import path

from . import staff_views

urlpatterns = [
    path("", staff_views.dashboard, name="staff_dashboard"),
    path("bookings/", staff_views.booking_hub, name="staff_booking_hub"),
    path("sessions/", staff_views.session_list, name="staff_session_list"),
    path("sessions/new/", staff_views.session_create, name="staff_session_create"),
    path("sessions/<int:pk>/edit/", staff_views.session_edit, name="staff_session_edit"),
    path("assessments/", staff_views.assessment_list, name="staff_assessment_list"),
    path("assessments/new/", staff_views.assessment_create, name="staff_assessment_create"),
    path("students/", staff_views.student_list, name="staff_student_list"),
    path("parents/reset/", staff_views.staff_reset_parent, name="staff_reset_parent"),
]
