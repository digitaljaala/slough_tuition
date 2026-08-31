from django.urls import path  # noqa: I001

from . import views
from students import views as student_views

urlpatterns = [
    path('', views.home, name='home'),
    path(
        "register/",
        student_views.register_student,
        name = "register_student",
         ),
    path("accounts/register/", student_views.register, name="register"),
    path("accounts/login/", student_views.login_view, name="login"),
    path("accounts/logout/", student_views.logout_view, name="logout"),
    path("accounts/", student_views.my_account, name="my_account"),
    path("enrol/", student_views.enrol, name="enrol"),
]
