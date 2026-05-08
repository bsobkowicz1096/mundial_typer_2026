from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Bet, InviteCode, Player, SpecialBet, Team

INPUT_CLASS = "w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"


class SpecialBetForm(forms.ModelForm):
    class Meta:
        model = SpecialBet
        fields = ["answer_player", "answer_team", "answer_number"]

    def __init__(self, question, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question

        if question.answer_type == "PLAYER":
            self.fields["answer_player"].required = True
            self.fields["answer_player"].queryset = Player.objects.select_related("team").order_by("team__name", "name")
            self.fields["answer_player"].widget.attrs["class"] = INPUT_CLASS
            self.fields["answer_player"].label = "Zawodnik"
            del self.fields["answer_team"]
            del self.fields["answer_number"]

        elif question.answer_type == "TEAM":
            self.fields["answer_team"].required = True
            self.fields["answer_team"].queryset = Team.objects.order_by("name")
            self.fields["answer_team"].widget.attrs["class"] = INPUT_CLASS
            self.fields["answer_team"].label = "Drużyna"
            del self.fields["answer_player"]
            del self.fields["answer_number"]

        else:  # NUMBER
            self.fields["answer_number"].required = True
            self.fields["answer_number"].widget = forms.NumberInput(attrs={"min": 0, "max": 500, "class": INPUT_CLASS})
            self.fields["answer_number"].label = "Liczba"
            del self.fields["answer_player"]
            del self.fields["answer_team"]

    def clean(self):
        cleaned = super().clean()
        if self.question.answer_type == "PLAYER" and not cleaned.get("answer_player"):
            self.add_error("answer_player", "Wybierz zawodnika.")
        elif self.question.answer_type == "TEAM" and not cleaned.get("answer_team"):
            self.add_error("answer_team", "Wybierz drużynę.")
        elif self.question.answer_type == "NUMBER" and cleaned.get("answer_number") is None:
            self.add_error("answer_number", "Podaj liczbę.")
        return cleaned


class BetForm(forms.ModelForm):
    class Meta:
        model = Bet
        fields = ["home_score", "away_score"]
        widgets = {
            "home_score": forms.NumberInput(attrs={
                "min": 0, "max": 20,
                "class": "w-12 text-center border border-gray-300 rounded px-1 py-1 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-green-500",
            }),
            "away_score": forms.NumberInput(attrs={
                "min": 0, "max": 20,
                "class": "w-12 text-center border border-gray-300 rounded px-1 py-1 text-sm font-bold focus:outline-none focus:ring-2 focus:ring-green-500",
            }),
        }


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    invite_code = forms.CharField(max_length=20, label="Kod zaproszenia")

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2", "invite_code"]

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip().upper()
        try:
            invite = InviteCode.objects.get(code=code, is_used=False)
        except InviteCode.DoesNotExist:
            raise forms.ValidationError("Nieprawidłowy lub już użyty kod zaproszenia.")
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            code = self.cleaned_data["invite_code"]
            invite = InviteCode.objects.get(code=code)
            invite.used_by = user
            invite.is_used = True
            invite.save()
        return user
