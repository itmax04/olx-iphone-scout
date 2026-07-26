"""Core forms: login with identifier/remember."""

from django import forms


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label="Логин или email",
        max_length=254,
        widget=forms.TextInput(
            attrs={"autofocus": True, "autocomplete": "username", "class": "form-control"}
        ),
    )
    password = forms.CharField(
        label="Пароль",
        max_length=256,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "class": "form-control"}
        ),
    )
    remember = forms.BooleanField(
        label="Запомнить на этом устройстве",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
