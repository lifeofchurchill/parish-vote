"""
Import members from the church's CSV export, for the ACTIVE election.

    python manage.py import_members "path/to/members.csv" --dry-run   (check only)
    python manage.py import_members "path/to/members.csv"             (save)

- Imports only members who meet the active election's age rule, plus anyone
  whose date of birth is missing or unreadable (they go on the "needs checking" list).
- Safe to run again with a fresh export: matches people by their church id,
  so existing members are updated, never duplicated, and ticks are never touched.
- A date of birth the Commissioner added on the "Needs checking" page is kept
  when the export still has no readable date for that person.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from voting.cleaning import (
    clean_name,
    clean_phones,
    parse_birth_date,
    phone_looks_damaged,
    read_csv_rows,
)
from voting.models import Election, Member

# Columns we need from the church's export (others are ignored on purpose)
REQUIRED_COLUMNS = ["id", "name", "birthDate", "phone", "community"]

# Don't flood the terminal: show at most this many problem lines
MAX_PROBLEMS_SHOWN = 40


class Command(BaseCommand):
    help = "Import members who meet the active election's age rule from the church's CSV export."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the church's CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read and check the file, report what would happen, save nothing.",
        )

    def handle(self, *args, **options):
        # ---- 0. Which election are we importing for? ----
        election = Election.objects.active()
        if election is None:
            raise CommandError(
                "No active election. In the admin, open Elections and tick 'Is active' "
                "on the election you're running."
            )
        earliest, latest = election.dob_range()

        # ---- 1. Read the file ----
        try:
            encoding, rows = read_csv_rows(options["csv_path"], REQUIRED_COLUMNS)
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['csv_path']}")
        except ValueError as error:
            raise CommandError(str(error))

        counts = Counter()
        problems = []
        to_save = {}  # church_id -> cleaned fields (a dict, so repeated ids collapse)

        # Dates of birth the Commissioner added by hand: church_id -> date
        added_by_hand = dict(
            Member.objects.filter(dob_added_at__isnull=False, date_of_birth__isnull=False)
            .values_list("church_id", "date_of_birth")
        )

        # ---- 2. Clean and check every row (nothing is saved yet) ----
        for line_no, row in rows:
            church_id = (row.get("id") or "").strip()
            name = clean_name(row.get("name") or "")

            # Without an id or a name we can't identify the person
            if not church_id or not name:
                counts["skipped_no_id_or_name"] += 1
                problems.append(f"Line {line_no}: missing id or name, skipped")
                continue

            # Date of birth: blank -> None; unreadable -> None + reported
            raw_dob = row.get("birthDate") or ""
            try:
                dob = parse_birth_date(raw_dob)
            except ValueError as error:
                dob = None
                counts["unreadable_dob"] += 1
                problems.append(f"Line {line_no} (id {church_id}): {error}, imported for checking")

            # The church still has no readable date, but the Commissioner added one: keep it.
            # The church has a date now: theirs wins, and the "added by hand" mark is cleared.
            kept_hand_date = dob is None and church_id in added_by_hand
            if kept_hand_date:
                dob = added_by_hand[church_id]
                counts["kept_hand_dob"] += 1
            elif church_id in added_by_hand and dob != added_by_hand[church_id]:
                problems.append(
                    f"Line {line_no} (id {church_id}): church date {dob:%d/%m/%Y} replaces the one "
                    f"added by hand ({added_by_hand[church_id]:%d/%m/%Y})"
                )

            # Known date of birth outside the age rule: not a voter, don't store their data
            too_old = dob is not None and earliest is not None and dob < earliest
            too_young = dob is not None and latest is not None and dob > latest
            if too_old or too_young:
                counts["skipped_outside_age"] += 1
                continue

            # Phones: first number is shown (masked), the rest are only for search
            raw_phone = row.get("phone") or ""
            if phone_looks_damaged(raw_phone):
                counts["damaged_phone"] += 1
                problems.append(f"Line {line_no} (id {church_id}): phone damaged by Excel ({raw_phone.strip()})")
            phones = clean_phones(raw_phone)

            # Same id twice in the file: the later row wins
            if church_id in to_save:
                counts["duplicate_id"] += 1
                problems.append(f"Line {line_no}: id {church_id} appears more than once, later row used")

            fields = {
                "full_name": name[:150],
                "date_of_birth": dob,
                "phone": phones[0] if phones else "",
                "other_phones": " ".join(phones[1:])[:100],
                "community": " ".join((row.get("community") or "").split())[:100],
            }
            if not kept_hand_date:
                # The date (or its absence) now comes from the church: not "added by hand"
                fields["dob_added_by"] = None
                fields["dob_added_at"] = None
            to_save[church_id] = fields

        # ---- 3. Report ----
        with_dob = sum(1 for f in to_save.values() if f["date_of_birth"])
        without_dob = len(to_save) - with_dob
        already_in_db = set(Member.objects.values_list("church_id", flat=True))

        self.stdout.write(f"Election: {election.name} (ages {election.age_rule})")
        self.stdout.write(f"File read: {len(rows)} rows (encoding: {encoding})")
        self.stdout.write(f"  Meet the age rule:                    {with_dob}")
        self.stdout.write(f"  No/unreadable date of birth (check):  {without_dob}")
        self.stdout.write(f"  Kept dates added on Needs checking:   {counts['kept_hand_dob']}")
        self.stdout.write(f"  Skipped, outside the age rule:        {counts['skipped_outside_age']}")
        self.stdout.write(f"  Skipped, missing id or name:          {counts['skipped_no_id_or_name']}")
        self.stdout.write(f"  Phones damaged by Excel:              {counts['damaged_phone']}")
        self.stdout.write(f"  Repeated ids in file:                 {counts['duplicate_id']}")
        self.stdout.write(
            f"  Will be new: {len(set(to_save) - already_in_db)}, "
            f"will be updated: {len(set(to_save) & already_in_db)}"
        )

        if problems:
            self.stdout.write(self.style.WARNING(f"\nProblems ({len(problems)}):"))
            for line in problems[:MAX_PROBLEMS_SHOWN]:
                self.stdout.write(f"  - {line}")
            if len(problems) > MAX_PROBLEMS_SHOWN:
                self.stdout.write(f"  ... and {len(problems) - MAX_PROBLEMS_SHOWN} more")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run: nothing was saved."))
            return

        # ---- 4. Save: all rows or none (atomic), so a crash can't leave half an import ----
        with transaction.atomic():
            for church_id, fields in to_save.items():
                Member.objects.update_or_create(church_id=church_id, defaults=fields)

        self.stdout.write(self.style.SUCCESS(f"\nSaved {len(to_save)} members."))