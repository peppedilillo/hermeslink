from django.test import TestCase
from django.db.models import Q
from django.utils import timezone
import datetime
from configs.search import interpret_search_query, ParseError


class SearchParserTest(TestCase):
    def test_basic_model_queries(self):
        self.assertEqual(str(interpret_search_query("h1")), str(Q(model="H1")))
        self.assertEqual(str(interpret_search_query("h2")), str(Q(model="H2")))
        self.assertEqual(str(interpret_search_query("h6")), str(Q(model="H6")))

    def test_config_existence_queries(self):
        self.assertEqual(str(interpret_search_query("acq")), str(Q(acq__isnull=False)))
        self.assertEqual(str(interpret_search_query("asic1")), str(Q(asic1__isnull=False)))
        self.assertEqual(str(interpret_search_query("bee")), str(Q(bee__isnull=False)))

    def test_status_queries(self):
        self.assertEqual(str(interpret_search_query("uplinked")), str(Q(uplinked=True)))
        self.assertEqual(str(interpret_search_query("submitted")), str(Q(submitted=True)))

        # Test status with username
        self.assertEqual(
            str(interpret_search_query("submitted by admin")),
            str(Q(author__username="admin"))
        )
        self.assertEqual(
            str(interpret_search_query("uplinked by testuser")),
            str(Q(uplinked_by__username="testuser"))
        )

    def test_date_comparison_queries(self):
        test_date = timezone.make_aware(datetime.datetime(2023, 1, 1))

        # date comparison operators
        date_str = "2023-01-01"
        self.assertEqual(
            str(interpret_search_query(f"submitted > {date_str}")),
            str(Q(submit_time__gt=test_date))
        )
        self.assertEqual(
            str(interpret_search_query(f"submitted >= {date_str}")),
            str(Q(submit_time__gte=test_date))
        )
        self.assertEqual(
            str(interpret_search_query(f"submitted < {date_str}")),
            str(Q(submit_time__lt=test_date))
        )
        self.assertEqual(
            str(interpret_search_query(f"submitted <= {date_str}")),
            str(Q(submit_time__lte=test_date))
        )
        self.assertEqual(
            str(interpret_search_query(f"submitted = {date_str}")),
            str(Q(submit_time=test_date))
        )
        self.assertEqual(
            str(interpret_search_query(f"submitted != {date_str}")),
            str(~Q(submit_time=test_date))
        )

    def test_id_queries(self):
        self.assertEqual(str(interpret_search_query("id = 42")), str(Q(pk=42)))
        self.assertEqual(str(interpret_search_query("id > 100")), str(Q(pk__gt=100)))
        self.assertEqual(str(interpret_search_query("id >= 200")), str(Q(pk__gte=200)))
        self.assertEqual(str(interpret_search_query("id < 50")), str(Q(pk__lt=50)))
        self.assertEqual(str(interpret_search_query("id <= 75")), str(Q(pk__lte=75)))
        self.assertEqual(str(interpret_search_query("id != 10")), str(~Q(pk=10)))

    def test_logical_operators(self):
        # AND operator (explicit and implicit)
        self.assertEqual(
            str(interpret_search_query("h1 and submitted")),
            str(Q(model="H1") & Q(submitted=True))
        )
        self.assertEqual(
            str(interpret_search_query("h1 submitted")),
            str(Q(model="H1") & Q(submitted=True))
        )

        # Test OR operator
        self.assertEqual(
            str(interpret_search_query("h1 or h2")),
            str(Q(model="H1") | Q(model="H2"))
        )

        # Test NOT operator
        self.assertEqual(
            str(interpret_search_query("not uplinked")),
            str(~Q(uplinked=True))
        )

    def test_grouping(self):
        # grouping with parentheses
        self.assertEqual(
            str(interpret_search_query("(h1 or h2) and uplinked")),
            str((Q(model="H1") | Q(model="H2")) & Q(uplinked=True))
        )
        self.assertEqual(
            str(interpret_search_query("h1 or (h2 and uplinked)")),
            str(Q(model="H1") | (Q(model="H2") & Q(uplinked=True)))
        )

    def test_complex_queries(self):
        self.assertEqual(
            str(interpret_search_query("(h1 or h2) and (submitted and not uplinked)")),
            str((Q(model="H1") | Q(model="H2")) & (Q(submitted=True) & ~Q(uplinked=True)))
        )

        self.assertEqual(
            str(interpret_search_query("id > 100 and (h1 or uplinked)")),
            str(Q(pk__gt=100) & (Q(model="H1") | Q(uplinked=True)))
        )

    def test_error_cases(self):
        with self.assertRaises(ParseError):
            interpret_search_query("id >")  # Missing value

        with self.assertRaises(ParseError):
            interpret_search_query("id = abc")  # Wrong value type

        with self.assertRaises(ParseError):
            interpret_search_query("(h1")  # Unclosed parenthesis

        with self.assertRaises(ParseError):
            interpret_search_query("submitted > baddate")  # Invalid date