from django.shortcuts import render

from students.forms import ParentForm, StudentForm


def home(request):
    return render(
        request,
        "core/home.html",
        {
            "parent_form": ParentForm(),
            "student_form": StudentForm(),
        },
    )

