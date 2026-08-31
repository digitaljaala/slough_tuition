import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    EmergencyContact,
    EnrolmentAgreement,
    MedicalInfo,
    Parent,
    Student,
)

User = get_user_model()

INPUT_CLASS = (
    "mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 "
    "text-[#262322] outline-none transition "
    "focus:border-[#36827F] focus:ring-2 focus:ring-[#36827F]/20"
)
ERROR_CLASS = "border-[#E63946] focus:border-[#E63946] focus:ring-[#E63946]/20"

UK_PHONE_RE = re.compile(r"^(?:\+44|0)\d{9,10}$")

YEAR_GROUP_CHOICES = [
    ("", "Select year group"),
    *[(f"Year {n}", f"Year {n}") for n in range(1, 14)],
    ("Key Stage 2", "Key Stage 2"),
    ("Key Stage 3", "Key Stage 3"),
    ("GCSE", "GCSE"),
    ("A Levels", "A Levels"),
    ("11+", "11+"),
    ("12+", "12+"),
    ("13+", "13+"),
    ("Life in the UK", "Life in the UK"),
    ("English Language Test", "English Language Test"),
    ("Other", "Other"),
]

SUBJECT_CHOICES = [
    ("primary_ks1", "Primary KS1"),
    ("primary_ks2", "Primary KS2"),
    ("11_plus", "11 Plus"),
    ("12_plus", "12 Plus"),
    ("13_plus", "13 Plus"),
    ("gcse_science", "GCSE Science"),
    ("gcse_maths", "GCSE Maths"),
    ("gcse_english_language", "GCSE English Language"),
    ("gcse_english_literature", "GCSE English Literature"),
    ("as_a_level", "AS/A Level"),
]

RELATIONSHIP_CHOICES = [
    ("", "Select relationship"),
    ("Mother", "Mother"),
    ("Father", "Father"),
    ("Step-parent", "Step-parent"),
    ("Grandparent", "Grandparent"),
    ("Legal guardian", "Legal guardian"),
    ("Other", "Other"),
]


def _widget_attrs(*, placeholder, autocomplete, input_type=None, extra=None):
    attrs = {
        "class": INPUT_CLASS,
        "placeholder": placeholder,
        "autocomplete": autocomplete,
    }
    if input_type:
        attrs["type"] = input_type
    if extra:
        attrs.update(extra)
    return attrs


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if self.errors.get(name):
                css = field.widget.attrs.get("class", INPUT_CLASS)
                field.widget.attrs["class"] = f"{css} {ERROR_CLASS}"


class ParentForm(StyledModelForm):
    relationship_to_student = forms.ChoiceField(
        label="Relationship to student",
        choices=RELATIONSHIP_CHOICES,
    )

    class Meta:
        model = Parent
        fields = ("parent_name", "relationship_to_student", "phone_number", "email", "address")
        labels = {
            "parent_name": "Parent or guardian name",
            "phone_number": "Contact number",
            "email": "Email address",
            "address": "Home address",
        }
        help_texts = {
            "email": "Optional if you have an account",
        }
        widgets = {
            "parent_name": forms.TextInput(
                attrs=_widget_attrs(
                    placeholder="Full name",
                    autocomplete="name",
                )
            ),
            "phone_number": forms.TelInput(
                attrs=_widget_attrs(
                    placeholder="e.g. 01753 318318",
                    autocomplete="tel",
                    extra={"inputmode": "tel"},
                )
            ),
            "email": forms.EmailInput(
                attrs=_widget_attrs(
                    placeholder="you@example.com",
                    autocomplete="email",
                )
            ),
            "address": forms.Textarea(
                attrs=_widget_attrs(
                    placeholder="Street, town, postcode",
                    autocomplete="street-address",
                    extra={"rows": 2},
                )
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["relationship_to_student"].widget.attrs["class"] = INPUT_CLASS

    def clean_parent_name(self):
        return self.cleaned_data["parent_name"].strip()

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        compact = re.sub(r"[\s\-().]", "", phone)
        if not UK_PHONE_RE.fullmatch(compact):
            raise ValidationError(
                "Enter a valid UK phone number, e.g. 01753 318318 or 07553 123565."
            )
        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email") or ""
        return email.strip().lower()


class StudentForm(StyledModelForm):
    year_group = forms.ChoiceField(
        label="Age or year group",
        choices=YEAR_GROUP_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    subjects = forms.ChoiceField(
        label="Subject enrolling for",
        choices=SUBJECT_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "h-5 w-5 text-[#36827F]"}),
    )

    class Meta:
        model = Student
        fields = ("student_name", "date_of_birth", "school_name", "year_group", "subjects", "support_needed")
        labels = {
            "student_name": "Child's name",
            "date_of_birth": "Date of birth",
            "school_name": "School name",
            "support_needed": "What support does your child need?",
        }
        help_texts = {
            "date_of_birth": "Optional",
            "school_name": "Optional",
            "support_needed": "Optional",
        }
        widgets = {
            "student_name": forms.TextInput(
                attrs=_widget_attrs(
                    placeholder="Child's full name",
                    autocomplete="off",
                )
            ),
            "date_of_birth": forms.DateInput(
                format="%Y-%m-%d",
                attrs=_widget_attrs(
                    placeholder="",
                    autocomplete="bday",
                    input_type="date",
                ),
            ),
            "school_name": forms.TextInput(
                attrs=_widget_attrs(
                    placeholder="Child's school (if applicable)",
                    autocomplete="organization",
                )
            ),
            "support_needed": forms.Textarea(
                attrs=_widget_attrs(
                    placeholder="Subjects, goals, or questions",
                    autocomplete="off",
                    extra={"rows": 3},
                )
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_of_birth"].input_formats = ["%Y-%m-%d"]
        self.fields["date_of_birth"].required = False
        self.fields["date_of_birth"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.fields["support_needed"].required = False
        self.fields["school_name"].required = False

    def clean_student_name(self):
        return self.cleaned_data["student_name"].strip()

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob and dob > timezone.localdate():
            raise ValidationError("Date of birth cannot be in the future.")
        return dob

    def save(self, commit=True):
        student = super().save(commit=False)
        subject = self.cleaned_data.get("subjects")
        student.subjects = [subject] if subject else []
        if commit:
            student.save()
        return student


class EmergencyContactForm(StyledModelForm):
    class Meta:
        model = EmergencyContact
        fields = ("full_name", "relationship", "phone_number")
        labels = {
            "full_name": "Emergency contact name",
            "relationship": "Relationship to student",
            "phone_number": "Contact number",
        }
        widgets = {
            "full_name": forms.TextInput(
                attrs=_widget_attrs(
                    placeholder="Full name",
                    autocomplete="off",
                )
            ),
            "relationship": forms.TextInput(
                attrs=_widget_attrs(
                    placeholder="e.g. Mother, Uncle, Neighbour",
                    autocomplete="off",
                )
            ),
            "phone_number": forms.TelInput(
                attrs=_widget_attrs(
                    placeholder="e.g. 01753 318318",
                    autocomplete="tel",
                    extra={"inputmode": "tel"},
                )
            ),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        compact = re.sub(r"[\s\-().]", "", phone)
        if not UK_PHONE_RE.fullmatch(compact):
            raise ValidationError(
                "Enter a valid UK phone number, e.g. 01753 318318 or 07553 123565."
            )
        return phone


class MedicalInfoForm(StyledModelForm):
    class Meta:
        model = MedicalInfo
        fields = ("details",)
        labels = {
            "details": "Medical or special requirements",
        }
        help_texts = {
            "details": "Health, allergies, conditions, learning/behavioural needs, medications. Enter N/A if none.",
        }
        widgets = {
            "details": forms.Textarea(
                attrs=_widget_attrs(
                    placeholder="If none, please enter N/A.",
                    autocomplete="off",
                    extra={"rows": 4},
                )
            ),
        }


class EnrolmentAgreementForm(StyledModelForm):
    class Meta:
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
        )
        widgets = {
            field_name: forms.CheckboxInput(
                attrs={"class": "h-5 w-5 rounded border-slate-300 text-[#36827F] focus:ring-[#36827F]/20"}
            )
            for field_name in (
                "pays_in_advance",
                "pays_on_time",
                "understands_no_refund",
                "gives_24h_notice",
                "child_on_time",
                "confirm_terms",
                "confirms_official_contact",
            )
        } | {
            "additional_questions": forms.Textarea(
                attrs=_widget_attrs(
                    placeholder="If none, please enter N/A.",
                    autocomplete="off",
                    extra={"rows": 3},
                )
            ),
        }

    def clean(self):
        cleaned = super().clean()
        required = (
            "pays_in_advance",
            "pays_on_time",
            "understands_no_refund",
            "gives_24h_notice",
            "child_on_time",
            "confirm_terms",
            "confirms_official_contact",
        )
        for field in required:
            if not cleaned.get(field):
                self.add_error(field, "This box must be ticked to continue.")
        return cleaned


class UserRegistrationForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs=_widget_attrs(
                placeholder="you@example.com",
                autocomplete="email",
            )
        ),
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs=_widget_attrs(
                placeholder="Create a password",
                autocomplete="new-password",
            )
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs=_widget_attrs(
                placeholder="Repeat your password",
                autocomplete="new-password",
            )
        ),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two passwords did not match.")
        password_validation.validate_password(password2)
        return password2

    def save(self):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        return User.objects.create_user(email=email, password=password)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email address"
        self.fields["username"].widget = forms.EmailInput(
            attrs=_widget_attrs(
                placeholder="you@example.com",
                autocomplete="email",
            )
        )
        self.fields["password"].widget = forms.PasswordInput(
            attrs=_widget_attrs(
                placeholder="Your password",
                autocomplete="current-password",
            )
        )
