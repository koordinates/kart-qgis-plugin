import os
import time

from qgis.PyQt.QtCore import QDate
from qgis.testing import start_app, unittest

start_app()

from kart.gui.historyviewer import commitDate  # noqa: E402


@unittest.skipUnless(hasattr(time, "tzset"), "requires time.tzset() (not available on Windows)")
class CommitDateTest(unittest.TestCase):
    """Regression tests for history date filtering (issue #87).

    Kart records commit times in UTC; the date filter must compare against
    the viewer's local date so commits near a UTC day boundary aren't hidden.
    """

    def setUp(self):
        # Pin to UTC-6 (the timezone reported in issue #87).
        self._tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Chicago"
        time.tzset()

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def test_commit_date_uses_local_time(self):
        # 02:16 UTC on the 8th is 20:16 on the 7th in UTC-6.
        self.assertEqual(commitDate("2022-11-08T02:16:11Z"), QDate(2022, 11, 7))

    def test_commit_date_same_day(self):
        # Daytime UTC stays on the same local day.
        self.assertEqual(commitDate("2021-11-16T08:57:57Z"), QDate(2021, 11, 16))
