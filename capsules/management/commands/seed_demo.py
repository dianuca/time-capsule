from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from capsules.models import Capsule


# Stable keys keep reruns safe even after the user edits a demo capsule.
SCENARIOS = [
    ("draft", "first-letter", "Prima mea scrisoare către viitor", 30, "Un început mic, cu mult curaj."),
    ("draft", "empty-message", "O idee încă nescrisă", 7, "Ciornă cu mesaj gol."),
    ("draft", "no-description", "Doar pentru mine", 90, ""),
    ("draft", "long-title", "O scrisoare despre toate lucrurile mici pe care vreau să mi le amintesc atunci când viața va arăta cu totul altfel decât astăzi", 365, "Titlu lung pentru verificarea cardului și a meniului."),
    ("draft", "expired", "Planuri care au nevoie de o dată nouă", -2, "Ciornă rămasă cu data în trecut; trebuie corectată la editare."),
    ("draft", "long-letter", "Jurnalul unei zile obișnuite", 180, "O scrisoare lungă, cu paragrafe și liste."),
    ("sealed", "soon", "Ne revedem într-un sfert de oră", 15 / 1440, "Un termen apropiat pentru testarea schimbării stării."),
    ("sealed", "tomorrow", "Un gând pentru mâine", 1, "O mică încurajare pentru o nouă zi."),
    ("sealed", "week", "După prima săptămână", 7, "Ce ai descoperit între timp?"),
    ("sealed", "year", "Pentru mine, peste un an", 365, "Visuri, curaj și pași mici."),
    ("sealed", "far-future", "Deschide când ai uitat de ea", 3650, "O amintire trimisă departe în viitor."),
    ("sealed", "unicode", "Bucurii mici 🌷 — acasă, în România", 60, "Ș, ț, ă, â, î; café, déjà-vu și amintiri ✨."),
    ("available", "now", "Momentul a sosit", 0, "Disponibilă chiar la momentul generării."),
    ("available", "yesterday", "Scrisoarea de ieri", -1, "Așteaptă să fie redescoperită."),
    ("available", "month", "Un anotimp nou", -30, "Ce s-a schimbat în ultima lună?"),
    ("available", "no-description", "O surpriză fără indiciu", -7, ""),
    ("available", "long-description", "Un album de gânduri", -90, "O descriere mai lungă pentru a verifica așezarea textului pe card, spațiul dintre elemente și alinierea acțiunilor atunci când amintirile au nevoie de mai multe cuvinte. " + "Detalii despre o zi frumoasă. " * 3),
    ("available", "literal-markup", 'Ghilimele „acasă” & <amintiri>', -2, "Text literal: <b>amintire</b> & prieteni; nu este HTML."),
    ("opened", "gratitude", "Lucrurile pentru care sunt recunoscătoare", -3, "O întâlnire cu mine din trecut."),
    ("opened", "journey", "După o călătorie frumoasă", -14, "Locuri, oameni și o hartă cu notițe."),
    ("opened", "birthday", "O aniversare de păstrat 🎂", -60, "Bucuria unui nou început."),
    ("opened", "old-letter", "Scrisoare dintr-un alt capitol", -730, "O capsulă veche, deja deschisă."),
    ("opened", "short", "Azi", -1, "Un gând."),
    ("opened", "multiline", "Lista de lucruri pe care le-am învățat", -120, "Un bilanț personal, cu rânduri separate."),
]


class Command(BaseCommand):
    help = "Adaugă 24 de capsule demo unui utilizator existent, fără duplicate sau suprascrieri."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="dianaciodolan")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            owner = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Utilizatorul nu există. Seed-ul nu creează conturi sau parole.") from exc
        now = timezone.now()
        created_count = 0
        for index, (state, key, title, days, description) in enumerate(SCENARIOS):
            opens_at = now + timedelta(days=days)
            sealed_at = min(now - timedelta(days=10), opens_at - timedelta(days=1))
            message = (
                "Dragă eu din viitor,\n\n"
                "Astăzi aleg să păstrez această amintire. Sper că ai găsit timp pentru lucrurile care te bucură.\n\n"
                "• Fă un pas mic către un vis.\n• Sună pe cineva drag.\n• Bucură-te de prezent.\n\n"
                "Cu drag,\nEu de atunci 🌷"
            )
            if key == "empty-message":
                message = ""
            elif key == "long-letter":
                message = (message + "\n\n") * 15
            elif key == "short":
                message = "Ai încredere în tine."
            elif key == "literal-markup":
                message = '<script>alert("demo")</script>\nAcest text trebuie afișat literal, niciodată executat.'
            capsule, created = Capsule.objects.get_or_create(
                pk=uuid5(NAMESPACE_URL, f"time-capsule/demo/v1/{owner.pk}/{state}/{key}"),
                defaults={
                    "owner": owner, "title": title, "description": description,
                    "message": message, "opens_at": opens_at,
                    "sealed_at": None if state == "draft" else sealed_at,
                    "first_opened_at": opens_at + (now - opens_at) / 2 if state == "opened" else None,
                },
            )
            if created:
                # Spread creation dates to exercise ordering without changing existing records.
                created_at = min(now - timedelta(days=index), opens_at - timedelta(days=2), sealed_at)
                Capsule.objects.filter(pk=capsule.pk).update(created_at=created_at, updated_at=created_at)
                created_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"{owner.username}: {created_count} capsule demo create, {len(SCENARIOS) - created_count} deja existente."
        ))
