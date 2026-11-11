"""Program selection, Disputes and Intakes module, profile, settings and notifications."""
import json
import re
import unittest
from datetime import timedelta
from unittest import mock

from apex import dates
from tests.base import AppTestCase


class ProgramSelectionTests(AppTestCase):
    def test_assigned_program_is_highlighted_and_locked(self):
        self.activate(0)
        self.login("AA11111", "Str0ngPass1", "associate")
        html = self.client.get("/programs").get_data(as_text=True)
        self.assertIn("Your Program", html)
        self.assertEqual(html.count("is-glow"), 1)
        for name in ("DISPUTES AND INTAKES", "COB", "NON COB", "CASH CONTROL", "IQT", "PREPAY"):
            self.assertIn(name, html)
        self.assertEqual(html.count("Coming soon"), 5)
        token = self.csrf("/programs")
        r = self.client.post("/programs", data={"_csrf": token, "program": "cob"})
        self.assertIn("only open the program assigned", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/di/task-entry").status_code, 302)

    def test_blank_program_highlights_all_and_allows_selection(self):
        self.activate(1)
        self.login("BB22222", "Str0ngPass1", "admin")
        html = self.client.get("/programs").get_data(as_text=True)
        self.assertEqual(html.count("is-glow"), 6)
        token = self.csrf("/programs")
        r = self.client.post("/programs", data={"_csrf": token, "program": "iqt"})
        self.assertIn("coming soon", r.get_data(as_text=True))
        r = self.client.post("/programs", data={"_csrf": token, "program": "di"})
        self.assertTrue(r.headers["Location"].endswith("/di/admin/pend-reports"))

    def test_unavailable_assigned_program_blocks_continue(self):
        self.user_rows[0]["PROGRAM"] = "COB"
        self.activate(0)
        self.login("AA11111", "Str0ngPass1", "associate")
        html = self.client.get("/programs").get_data(as_text=True)
        self.assertIn("not available yet", html)
        self.assertRegex(html, r"data-program-continue\s+disabled")


class DisputesIntakesTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.row = self.sign_in_di(0)

    def token(self, path="/di/task-entry"):
        return self.csrf(path)

    def add_pend(self, inquiry="INQ-1001", days_ago=3, remarks="Missing docs"):
        return self.client.post("/di/task-entry", data={
            "_csrf": self.token(), "inquiry_number": inquiry, "remarks": remarks,
            "date_pended": (dates.today() - timedelta(days=days_ago)).isoformat(),
            # Tampering attempts on read-only fields must be ignored:
            "status": "Completed", "assigned_to": "Hacker", "domain": "ZZ99999",
        })

    def test_task_entry_saves_with_autofilled_fields(self):
        html = self.client.get("/di/task-entry").get_data(as_text=True)
        for text in ("Jane Doe", "AA11111", "Mark Manager", 'value="Pending"', "Clear Form", dates.today().isoformat()):
            self.assertIn(text, html)
        r = self.add_pend()
        self.assertEqual(r.status_code, 302)
        saved = self.fake.tables["Pend"][0]
        self.assertEqual(saved["STATUS"], "Pending")
        self.assertEqual(saved["DOMAIN"], "AA11111")
        self.assertEqual(saved["ASSIGNED_TO"], "Jane Doe")
        self.assertEqual(saved["MANAGER"], "Mark Manager")
        self.assertEqual(saved["PENDED_DAYS"], 3)
        self.assertEqual(saved["INQUIRY_NUMBER"], "INQ-1001")

    def test_task_entry_validation(self):
        r = self.client.post("/di/task-entry", data={"_csrf": self.token(), "inquiry_number": ""})
        self.assertIn("Inquiry Number is required.", r.get_data(as_text=True))
        future = (dates.today() + timedelta(days=2)).isoformat()
        r = self.client.post("/di/task-entry", data={"_csrf": self.token(), "inquiry_number": "X1", "date_pended": future})
        self.assertIn("cannot be in the future", r.get_data(as_text=True))
        r = self.client.post("/di/task-entry", data={"_csrf": self.token(), "inquiry_number": "a,b)"})
        self.assertIn("may only contain", r.get_data(as_text=True))
        self.assertEqual(self.fake.tables["Pend"], [])

    def test_pended_days_stored_but_never_displayed(self):
        self.add_pend(days_ago=2)
        pend = self.fake.tables["Pend"][0]
        self.assertEqual(pend["PENDED_DAYS"], 2)
        pend["PEND_REVIEW"] = "Valid"
        pages = ["/di/task-entry", "/di/update-pends", f"/di/update-pends?id={pend['id']}", "/di/reviewed-pends",
                 "/di/dashboard", f"/di/dashboard?q={pend['INQUIRY_NUMBER']}", "/di/dashboards"]
        for path in pages:
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotRegex(html, r"(?i)pended[ _]days", path)
        self.assertNotIn("pended_days", self.client.post("/di/task-entry", data={"_csrf": self.token()}).get_data(as_text=True).lower())

    def test_sidebar_dashboard_vs_my_dashboard_tab(self):
        html = self.client.get("/di/dashboards").get_data(as_text=True)
        self.assertIn("Executive Dashboard", html)
        self.assertIn("Total Pending", html)
        self.assertRegex(html, r'href="/di/dashboards" class="nav-link active"')
        self.assertIn("<span>Dashboard</span>", html)
        self.assertNotIn("Coming Soon", html)
        tab = self.client.get("/di/dashboard").get_data(as_text=True)
        self.assertIn("Total Pends", tab)
        self.assertRegex(tab, r'href="/di/dashboard" class="module-tab active"')

    def test_update_pends_search_select_and_update(self):
        self.add_pend("INQ-1001", 10)
        self.add_pend("INQ-2002", 1)
        self.fake.tables["Pend"].append({"id": 999, "DOMAIN": "BB22222", "INQUIRY_NUMBER": "OTHER-1",
                                         "STATUS": "Pending", "DATE_PENDED": dates.today().isoformat()})
        html = self.client.get("/di/update-pends").get_data(as_text=True)
        self.assertIn("INQ-1001", html)
        self.assertIn("INQ-2002", html)
        self.assertNotIn("OTHER-1", html)

        html = self.client.get("/di/update-pends?q=2002").get_data(as_text=True)
        self.assertNotIn("INQ-1001", html)
        start = (dates.today() - timedelta(days=5)).isoformat()
        html = self.client.get(f"/di/update-pends?from={start}").get_data(as_text=True)
        self.assertIn("INQ-2002", html)
        self.assertNotIn("INQ-1001", html)

        pid = self.fake.tables["Pend"][0]["id"]
        html = self.client.get(f"/di/update-pends?id={pid}").get_data(as_text=True)
        self.assertIn("Update Record", html)
        self.assertIn("Missing docs", html)
        r = self.client.post(f"/di/update-pends/{pid}", data={"_csrf": self.token(), "status": "Completed",
                                                              "last_note": "Docs received"})
        self.assertEqual(r.status_code, 302)
        saved = self.fake.tables["Pend"][0]
        self.assertEqual(saved["STATUS"], "Completed")
        self.assertEqual(saved["LAST_NOTE"], "Docs received")
        self.assertEqual(saved["LAST_DATE_UPDATE"], dates.today().isoformat())

        r = self.client.post(f"/di/update-pends/{pid}", data={"_csrf": self.token(), "status": "Bogus"})
        self.assertEqual(self.fake.tables["Pend"][0]["STATUS"], "Completed")
        r = self.client.post("/di/update-pends/999", data={"_csrf": self.token(), "status": "Completed"})
        self.assertEqual(self.fake.tables["Pend"][2]["STATUS"], "Pending")  # other user's record untouched

    def test_reviewed_pends_and_acknowledge(self):
        self.add_pend("INQ-V")
        self.add_pend("INQ-I")
        valid, invalid = self.fake.tables["Pend"]
        valid.update(PEND_REVIEW="Valid", REVIEWER="Rita Reviewer", REVIEWER_REMARKS="Good", DATE_REVIEWED="2026-11-01")
        invalid.update(PEND_REVIEW="Invalid", REVIEWER="Rita Reviewer", REVIEWER_REMARKS="Wrong code",
                       DATE_REVIEWED="2026-11-02", ACKNOWLEDGED=False)

        html = self.client.get("/di/task-entry").get_data(as_text=True)
        self.assertIn("1 invalid review that must be acknowledged", html)
        html = self.client.get("/di/reviewed-pends").get_data(as_text=True)
        for text in ("INQ-V", "INQ-I", "Rita Reviewer", "Wrong code", "Nov 02, 2026", "ACKNOWLEDGE"):
            self.assertIn(text, html)
        self.assertEqual(html.count("ACKNOWLEDGE</button>"), 1)
        html = self.client.get("/di/reviewed-pends?review=Valid").get_data(as_text=True)
        self.assertNotIn("INQ-I", html)

        r = self.client.post(f"/di/reviewed-pends/{invalid['id']}/acknowledge", data={"_csrf": self.token()})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(invalid["ACKNOWLEDGED"])
        self.assertEqual(invalid["ACKNOWLEDGED_BY"], "AA11111")
        self.assertNotIn("must be acknowledged", self.client.get("/di/task-entry").get_data(as_text=True))
        r = self.client.post(f"/di/reviewed-pends/{valid['id']}/acknowledge", data={"_csrf": self.token()})
        self.assertNotIn("ACKNOWLEDGED_BY", valid)

    def test_dashboard_cards_charts_and_history(self):
        self.add_pend("INQ-1", 0)
        self.add_pend("INQ-2", 40)
        self.add_pend("INQ-3", 1)
        p = self.fake.tables["Pend"]
        p[0]["STATUS"] = "Completed"
        p[1]["PEND_REVIEW"] = "Valid"
        p[2]["PEND_REVIEW"] = "Invalid"
        self.fake.tables["apex_pend_history"] = [
            {"id": 1, "pend_id": str(p[0]["id"]), "inquiry_number": "INQ-1", "domain": "AA11111", "action": "Created",
             "status": "Pending", "note": "first", "changed_by": "AA11111", "created_at": "2026-11-10T01:00:00+00:00"},
            {"id": 2, "pend_id": "x", "inquiry_number": "SECRET", "domain": "BB22222", "action": "Created",
             "created_at": "2026-11-10T01:00:00+00:00"},
        ]
        html = self.client.get("/di/dashboard").get_data(as_text=True)
        cards = dict(re.findall(r'stat-label">([^<]+)</p><p class="stat-value" data-count="(\d+)"', html))
        self.assertEqual(cards, {"Total Pends": "3", "Pending Pends": "2", "Completed Pends": "1",
                                 "Valid Pends": "1", "Invalid Pends": "1"})
        charts = json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(charts["review"], {"valid": 1, "invalid": 1, "unreviewed": 1})
        self.assertEqual(len(charts["monthly"]), 12)
        self.assertEqual(len(charts["daily"]), 30)
        self.assertEqual(sum(d["count"] for d in charts["daily"]), 2)
        self.assertIn("first", html)
        self.assertNotIn("SECRET", html)
        html = self.client.get("/di/dashboard?q=INQ-2").get_data(as_text=True)
        self.assertIn("Open in Update Pends", html)


class ProfileSettingsNotificationTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.row = self.sign_in_di(0)

    def test_profile_view_and_edit(self):
        html = self.client.get("/profile").get_data(as_text=True)
        for text in ("Jane Doe", "1001", "AA11111", "Disputes and Intakes", "Mark Manager", "jane.doe@carelon.com", "Edit"):
            self.assertIn(text, html)
        token = self.csrf("/profile/edit")
        base = {"_csrf": token, "Associate Name": "Jane Q Doe", "Employee Number": "1001",
                "Program": "DISPUTES AND INTAKES", "Manager Name": "New Manager", "Email Address": "jane.doe@gmail.com"}
        r = self.client.post("/profile/edit", data=base)
        self.assertIn("Please enter a valid Carelon email address.", r.get_data(as_text=True))
        r = self.client.post("/profile/edit", data={**base, "Email Address": "Jane.QDoe@carelon.com", "DOMAIN": "HACK"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.row["ASSOCIATE NAME"], "Jane Q Doe")
        self.assertEqual(self.row["MANAGER NAME"], "New Manager")
        self.assertEqual(self.row["EMAIL ADDRESS"], "jane.qdoe@carelon.com")
        self.assertEqual(self.row["PROGRAM"], "Disputes and Intakes")  # case-only change ignored
        self.assertEqual(self.row["DOMAIN"], "AA11111")

    def test_settings_persist_per_user(self):
        html = self.client.get("/settings").get_data(as_text=True)
        for text in ("Blue", "Violet", "Green", "Orange", "Pink", "Grey", "Light Mode", "Dark Mode", "Portrait", "Landscape"):
            self.assertIn(text, html)
        r = self.client.post("/settings", data={"_csrf": self.csrf("/settings"), "accent": "pink", "mode": "light",
                                                "orientation": "portrait"})
        self.assertEqual(r.status_code, 302)
        saved = self.fake.tables["apex_user_settings"][0]
        self.assertEqual((saved["domain"], saved["accent"], saved["mode"], saved["orientation"], saved["electric_border"]),
                         ("AA11111", "pink", "light", "portrait", False))
        html = self.client.get("/di/task-entry").get_data(as_text=True)
        self.assertIn('data-theme="light" data-accent="pink"', html)
        self.assertIn('data-electric="off"', html)
        self.assertIn('data-orientation="portrait"', html)

        r = self.client.post("/api/preferences", json={"mode": "dark", "accent": "evil"},
                             headers={"X-CSRF-Token": self.csrf("/settings")})
        self.assertEqual(r.get_json()["prefs"]["mode"], "dark")
        self.assertEqual(self.fake.tables["apex_user_settings"][0]["accent"], "pink")
        self.assertEqual(self.client.post("/api/preferences", json={"mode": "dark"}).status_code, 400)

        self.client.post("/logout", data={"_csrf": self.csrf("/settings")})
        self.login("AA11111", "Str0ngPass1", "associate")
        self.assertIn('data-accent="pink"', self.client.get("/programs").get_data(as_text=True))

    def test_notifications_bell_and_history(self):
        self.fake.tables["apex_notification"] = [
            {"id": 1, "domain": "AA11111", "kind": "invalid", "title": "Pend marked Invalid", "message": "m1",
             "is_read": False, "created_at": "2026-11-10T02:00:00+00:00"},
            {"id": 2, "domain": "AA11111", "kind": "status", "title": "Pend status changed", "message": "m2",
             "is_read": True, "created_at": "2026-11-09T02:00:00+00:00"},
            {"id": 3, "domain": "BB22222", "kind": "valid", "title": "Not mine", "is_read": False,
             "created_at": "2026-11-09T02:00:00+00:00"},
        ]
        data = self.client.get("/api/notifications").get_json()
        self.assertEqual(data["unread"], 1)
        self.assertEqual([n["id"] for n in data["items"]], [1, 2])
        html = self.client.get("/notifications").get_data(as_text=True)
        self.assertIn("Pend marked Invalid", html)
        self.assertNotIn("Not mine", html)
        token = self.csrf("/notifications")
        self.assertEqual(self.client.post("/api/notifications/read", json={"id": "1;drop"},
                                          headers={"X-CSRF-Token": token}).status_code, 400)
        self.client.post("/api/notifications/read", json={}, headers={"X-CSRF-Token": token})
        self.assertEqual(self.client.get("/api/notifications").get_json()["unread"], 0)
        self.assertFalse(self.fake.tables["apex_notification"][2]["is_read"])

    def test_header_brand_logos(self):
        html = self.client.get("/di/task-entry").get_data(as_text=True)
        for img in ("cb.png", "ct.png", "pi-black.png", "cw.png", "ctw.png", "pi-white.png", "ignite.png", "apex.png"):
            self.assertIn(img, html)
        for label in ("Task Entry", "Update Pends", "Reviewed Pends", "<span>Dashboard</span>", "My Dashboard", "Profile",
                      "Settings"):
            self.assertIn(label, html)


class PendedDaysTests(unittest.TestCase):
    def test_days_since(self):
        with mock.patch.object(dates, "today", return_value=dates.parse("2026-11-10")):
            self.assertEqual(dates.days_since("2026-11-01"), 9)
            self.assertEqual(dates.days_since("2026-11-01T08:00:00+00:00"), 9)
            self.assertEqual(dates.days_since("2026-11-12"), 0)
            self.assertIsNone(dates.days_since(None))


if __name__ == "__main__":
    unittest.main()
