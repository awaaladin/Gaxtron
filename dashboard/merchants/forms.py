from django import forms
from django.contrib.auth.forms import UserCreationForm

from merchants.models import GaxtronUser


class MerchantRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = GaxtronUser
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower().strip()
        if commit:
            user.save()
        return user
