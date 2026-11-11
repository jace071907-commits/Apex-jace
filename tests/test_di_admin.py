"""Disputes and Intakes — Admin (reviewer) module."""
import io
import re
import unittest
import zipfile
from datetime import timedelta

from apex import dates
from tests.base import AppTestCase


def pend(pid, inquiry, **extra):
    row = {"id": pid, "INQUIRY_NUMBER": inquiry, "STATUS": "Pending", "DOMAIN": "AA11111", "ASSIGNED_TO": "Jane Doe",
           "MANAGER": "Mark Manager", "DATE_PENDED": (dates.today() - timedelta(days=3)).isoformat(),
           "SUB_STATUS": None, "REVIEWER_DOMAIN": None, "PEND_REVIEW": None, "ACKNOWLEDGED": False,
           "REMARKS": "needs docs", "PENDED_DAYS": 3}
    row.update(extra)
    return row


class AdminModuleTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.fake.tables["Pend"] = [
            pend("p1", "INQ-100", SUB_STATUS="Awaiting docs"),
            pend("p2", "INQ-200", MANAGER="Other Manager", ASSIGNED_TO="Ann Lee", DOMAIN="CC33333"),
            pend("p3", "INQ-300", REVIEWER_DOMAIN=""),                       # blank reviewer -> still in queue
            pend("p4", "INQ-400", STATUS="Completed"),                       # completed -> hidden
            pend("p5", "INQ-500", REVIEWER_DOMAIN="ZZ99999", PEND_REVIEW="Valid", REVIEWER="Zed",
                 DATE_REVIEWED=dates.today().isoformat()),                    # other reviewer -> hidden
        ]
        self.admin = self.sign_in_di(1)

    def token(self, path="/di/admin/pend-reports"):
        return self.csrf(path)

    def review(self, pid, **data):
        form = {"_csrf": self.token(), "pend_review": "Invalid", "reviewer": "John Roe",
                "date_reviewed": dates.today().isoformat(), "reviewer_remarks": "Wrong code used", **data}
        return self.client.post(f"/di/admin/review/{pid}", data=form)

    # ---------------- access & navigation ----------------
    def test_navigation_tabs_and_access_split(self):
        html = self.client.get("/di/admin/pend-reports").get_data(as_text=True)
        for label in ("Pend Reports", "Reviewed Pends", "My Dashboard", "Dashboard", "Profile", "Settings",
                      "apex.png", "data-notif"):
            self.assertIn(label, html)
        self.assertNotIn("Task Entry", html)
        self.assertNotIn("Administration", html)
        self.assertIn("Admin</span>", html)
        nav = re.findall(r'class="nav-link[^"]*"[^>]*>.*?<span>([^<]+)</span>', html, re.S)
        self.assertEqual(nav[:5], ["Pend Reports", "Reviewed Pends", "Dashboard", "Profile", "Settings"])
        self.assertIn("Logout", nav)
        self.assertEqual(self.client.get("/di/task-entry").status_code, 403)
        self.assertEqual(self.client.get("/di/dashboards").status_code, 403)  # associate route; admins use /di/admin/dashboards
        dash = self.client.get("/di/admin/dashboards").get_data(as_text=True)
        self.assertIn("Executive Dashboard", dash)
        self.assertRegex(dash, r'href="/di/admin/dashboards" class="nav-link active"')

    def test_associate_cannot_open_admin_module(self):
        self.client.post("/logout", data={"_csrf": self.token()})
        self.sign_in_di(0)
        for path in ("/di/admin/pend-reports", "/di/admin/review/p1", "/di/admin/reviewed", "/di/admin/dashboard",
                     "/di/admin/export?scope=all"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    # ---------------- Tab 1: Pend Reports ----------------
    def test_pend_reports_queue_rules_and_columns(self):
        html = self.client.get("/di/admin/pend-reports").get_data(as_text=True)
        for inq in ("INQ-100", "INQ-200", "INQ-300"):
            self.assertIn(inq, html)
        for inq in ("INQ-400", "INQ-500"):
            self.assertNotIn(inq, html)
        for col in ("Inquiry Number", "Status", "Assigned To", "Manager", "Domain", "Date Pended", "Sub Status"):
            self.assertIn(f"<th>{col}</th>", html)
        self.assertIn("Awaiting docs", html)
        self.assertRegex(html, r'nav-badge nav-badge-info[^>]*>3<')

    def test_pend_reports_search_and_filters(self):
        html = self.client.get("/di/admin/pend-reports?q=200").get_data(as_text=True)
        self.assertIn("INQ-200", html)
        self.assertNotIn("INQ-100", html)
        html = self.client.get("/di/admin/pend-reports?manager=Mark+Manager").get_data(as_text=True)
        self.assertNotIn("INQ-200", html)
        self.assertIn("INQ-100", html)
        html = self.client.get("/di/admin/pend-reports?assigned_to=Ann+Lee").get_data(as_text=True)
        self.assertEqual(re.findall(r"INQ-\d+", html.split("<tbody>")[1]), ["INQ-200"])
        html = self.client.get("/di/admin/pend-reports?sub_status=Awaiting+docs").get_data(as_text=True)
        self.assertEqual(re.findall(r"INQ-\d+", html.split("<tbody>")[1]), ["INQ-100"])
        for opt in ("<option>Mark Manager</option>", "<option>Other Manager</option>", "<option>Ann Lee</option>"):
            self.assertIn(opt, self.client.get("/di/admin/pend-reports").get_data(as_text=True))

    # ---------------- Review tab ----------------
    def test_review_tab_defaults_validation_and_save(self):
        html = self.client.get("/di/admin/review/p1").get_data(as_text=True)
        self.assertIn("Review · INQ-100", html)
        self.assertIn("module-tab active module-tab-extra", html)
        for text in ("needs docs", 'value="John Roe"', 'value="BB22222"', f'value="{dates.today().isoformat()}"',
                     "<option>Valid</option>", "<option>Invalid</option>", "Save Review", "Cancel"):
            self.assertIn(text, html)
        self.assertIn("Remarks are required", self.review("p1", reviewer_remarks="  ").get_data(as_text=True))
        future = (dates.today() + timedelta(days=1)).isoformat()
        self.assertIn("cannot be in the future", self.review("p1", date_reviewed=future).get_data(as_text=True))
        self.assertIn("Valid or Invalid", self.review("p1", pend_review="Maybe").get_data(as_text=True))
        self.assertIsNone(self.fake.tables["Pend"][0]["PEND_REVIEW"])

        r = self.review("p1", reviewer_domain="HACKER")  # reviewer domain cannot be overridden
        self.assertTrue(r.headers["Location"].endswith("/di/admin/pend-reports"))
        saved = self.fake.tables["Pend"][0]
        self.assertEqual((saved["PEND_REVIEW"], saved["REVIEWER"], saved["REVIEWER_DOMAIN"], saved["REVIEWER_REMARKS"],
                          saved["DATE_REVIEWED"]),
                         ("Invalid", "John Roe", "BB22222", "Wrong code used", dates.today().isoformat()))
        html = self.client.get("/di/admin/pend-reports").get_data(as_text=True)
        self.assertIn("Review saved for Inquiry INQ-100 (Invalid).", html)
        self.assertNotIn('title="Open review">INQ-100<', html)
        self.assertIn('title="Open review">INQ-200<', html)
        # no double review
        r = self.review("p1", pend_review="Valid")
        self.assertEqual(self.fake.tables["Pend"][0]["PEND_REVIEW"], "Invalid")
        self.assertEqual(self.client.get("/di/admin/review/p4").status_code, 302)  # completed -> not reviewable

    # ---------------- Tab 2: Reviewed Pends + edit ----------------
    def test_reviewed_pends_and_edit(self):
        self.review("p1")
        self.review("p2", pend_review="Valid", reviewer_remarks="All good")
        html = self.client.get("/di/admin/reviewed").get_data(as_text=True)
        for text in ("INQ-100", "INQ-200", "Wrong code used", "All good", "John Roe", "Awaiting"):
            self.assertIn(text, html)
        self.assertNotIn("INQ-500", html)  # other reviewer's review
        html = self.client.get("/di/admin/reviewed?q=200").get_data(as_text=True)
        self.assertNotIn("INQ-100", html)
        html = self.client.get("/di/admin/reviewed?review=Invalid").get_data(as_text=True)
        self.assertNotIn("INQ-200", html)

        # Status column with coloured chips
        html = self.client.get("/di/admin/reviewed").get_data(as_text=True)
        self.assertIn("<th>Status</th><th>Pend Review</th><th>Reviewer</th><th>Date Reviewed</th><th>Reviewer Remarks</th>", html)
        self.assertIn('chip-status chip-orange">Pending<', html)
        self.assertIn('chip-status chip-red">Invalid<', html)
        self.assertIn('chip-status chip-emerald">Valid<', html)

        # Edit screen: current values shown; STATUS / PEND REVIEW / REMARKS editable; name + date read-only
        html = self.client.get("/di/admin/reviewed/p1/edit").get_data(as_text=True)
        self.assertIn("Edit Review · INQ-100", html)
        self.assertIn('class="current-review"', html)
        self.assertIn("Wrong code used", html)
        self.assertIn('<option selected>Invalid</option>', html)
        self.assertIn('name="status"', html)
        self.assertIn('<option selected>Pending</option><option>Completed</option>', html)
        self.assertNotIn('name="reviewer"', html)
        self.assertNotIn('name="date_reviewed"', html)
        yesterday = (dates.today() - timedelta(days=1)).isoformat()
        r = self.client.post("/di/admin/reviewed/p1/edit", data={
            "_csrf": self.token(), "status": "Pending", "pend_review": "Valid", "reviewer_remarks": "Re-checked: valid",
            "reviewer": "Tampered", "date_reviewed": yesterday})
        self.assertTrue(r.headers["Location"].endswith("/di/admin/reviewed"))
        saved = self.fake.tables["Pend"][0]
        self.assertEqual((saved["STATUS"], saved["PEND_REVIEW"], saved["REVIEWER_REMARKS"], saved["REVIEWER"],
                          saved["DATE_REVIEWED"], saved["UPDATED_BY"]),
                         ("Pending", "Valid", "Re-checked: valid", "John Roe", dates.today().isoformat(), "BB22222"))
        self.assertIn("valid status", self.client.post("/di/admin/reviewed/p1/edit", data={
            "_csrf": self.token(), "status": "Bogus", "pend_review": "Valid", "reviewer_remarks": "x"}).get_data(as_text=True))

        # Setting STATUS = Completed removes it from Reviewed Pends
        r = self.client.post("/di/admin/reviewed/p1/edit", data={
            "_csrf": self.token(), "status": "Completed", "pend_review": "Valid", "reviewer_remarks": "Done"})
        self.assertEqual(self.fake.tables["Pend"][0]["STATUS"], "Completed")
        html = self.client.get("/di/admin/reviewed").get_data(as_text=True)
        self.assertIn("moved out of Reviewed Pends", html)
        self.assertNotIn('title="Edit review">INQ-100<', html)

        r = self.client.get("/di/admin/reviewed/p5/edit")
        self.assertEqual(r.status_code, 302)  # cannot edit another reviewer's review
        self.client.post("/di/admin/reviewed/p5/edit", data={"_csrf": self.token(), "status": "Pending",
                                                            "pend_review": "Invalid", "reviewer_remarks": "x"})
        self.assertEqual(self.fake.tables["Pend"][4]["PEND_REVIEW"], "Valid")

    def test_edit_keeps_nonstandard_status_selectable(self):
        self.fake.tables["Pend"].append(pend("o1", "OPEN-9", STATUS="In Progress", REVIEWER_DOMAIN="BB22222",
                                             PEND_REVIEW="Invalid", REVIEWER="John Roe", REVIEWER_REMARKS="r",
                                             DATE_REVIEWED=dates.today().isoformat()))
        html = self.client.get("/di/admin/reviewed").get_data(as_text=True)
        self.assertIn('chip-status chip-purple">In Progress<', html)
        html = self.client.get("/di/admin/reviewed/o1/edit").get_data(as_text=True)
        self.assertIn("<option selected>In Progress</option>", html)

    def test_reviewed_pends_hide_completed(self):
        today = dates.today().isoformat()
        mine = dict(REVIEWER_DOMAIN="BB22222", PEND_REVIEW="Invalid", REVIEWER="John Roe", REVIEWER_REMARKS="r",
                    DATE_REVIEWED=today)
        self.fake.tables["Pend"] += [pend("c1", "OPEN-1", **mine), pend("c2", "DONE-1", STATUS="Completed", **mine),
                                     pend("c3", "NOSTATUS-1", STATUS=None, **mine)]
        html = self.client.get("/di/admin/reviewed").get_data(as_text=True)
        self.assertIn("OPEN-1", html)
        self.assertIn("NOSTATUS-1", html)
        self.assertNotIn("DONE-1", html)
        self.assertNotIn("DONE-1", self.client.get("/di/admin/reviewed?q=DONE").get_data(as_text=True))
        # Completed pends cannot be opened or edited directly
        self.assertEqual(self.client.get("/di/admin/reviewed/c2/edit").status_code, 302)
        self.client.post("/di/admin/reviewed/c2/edit", data={"_csrf": self.token(), "status": "Pending",
                                                            "pend_review": "Valid", "reviewer_remarks": "x"})
        self.assertEqual(self.fake.tables["Pend"][-2]["PEND_REVIEW"], "Invalid")
        self.assertEqual(self.fake.tables["Pend"][-2]["STATUS"], "Completed")
        # Edit still works for non-Completed reviews
        self.client.post("/di/admin/reviewed/c1/edit", data={"_csrf": self.token(), "status": "Pending",
                                                            "pend_review": "Valid", "reviewer_remarks": "fixed"})
        self.assertEqual(self.fake.tables["Pend"][-3]["PEND_REVIEW"], "Valid")
        # My Dashboard is unchanged: Completed reviews still count
        html = self.client.get("/di/admin/dashboard").get_data(as_text=True)
        self.assertRegex(html, r'Total Reviewed</p><p class="stat-value" data-count="3"')

    # ---------------- Tab 3: My Dashboard ----------------
    def test_reviewer_dashboard_views_and_dates(self):
        today = dates.today()
        self.fake.tables["Pend"] += [
            pend("d1", "D-1", REVIEWER_DOMAIN="BB22222", PEND_REVIEW="Valid", DATE_REVIEWED=today.isoformat()),
            pend("d2", "D-2", REVIEWER_DOMAIN="BB22222", PEND_REVIEW="Invalid", DATE_REVIEWED=today.isoformat()),
            pend("d3", "D-3", REVIEWER_DOMAIN="BB22222", PEND_REVIEW="Valid",
                 DATE_REVIEWED=(today - timedelta(days=60)).isoformat()),
        ]

        def cards(html):
            found = dict(re.findall(r'stat-label">([^<]+)</p><p class="stat-value"[^>]*>(\d+)', html))
            found.pop("Valid Rate", None)
            return found

        html = self.client.get("/di/admin/dashboard").get_data(as_text=True)
        self.assertEqual(cards(html), {"Total Reviewed": "2", "Total Valid": "1", "Total Invalid": "1"})
        self.assertIn("Daily", html)
        self.assertIn("50%", html)
        html = self.client.get("/di/admin/dashboard?view=monthly").get_data(as_text=True)
        self.assertEqual(cards(html)["Total Reviewed"], "3")
        self.assertIn("Reviews per Month", html)
        html = self.client.get("/di/admin/dashboard?view=weekly").get_data(as_text=True)
        self.assertIn("Reviews per Week", html)
        old = (today - timedelta(days=60)).isoformat()
        html = self.client.get(f"/di/admin/dashboard?view=daily&from={old}&to={old}").get_data(as_text=True)
        self.assertEqual(cards(html), {"Total Reviewed": "1", "Total Valid": "1", "Total Invalid": "0"})
        html = self.client.get("/di/admin/dashboard?view=daily&from=2000-01-01").get_data(as_text=True)
        self.assertIn("too large", html)

    # ---------------- Export ----------------
    def _sheet(self, resp):
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn(".xlsx", resp.headers["Content-Disposition"])
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        self.assertIn("xl/workbook.xml", zf.namelist())
        return zf.read("xl/worksheets/sheet1.xml").decode()

    def test_export_all_and_filtered(self):
        sheet = self._sheet(self.client.get("/di/admin/export?scope=all"))
        for inq in ("INQ-100", "INQ-400", "INQ-500"):
            self.assertIn(inq, sheet)
        self.assertIn("INQUIRY_NUMBER", sheet)
        self.assertNotIn("PASSWORD", sheet)   # Pend table only, never User
        sheet = self._sheet(self.client.get("/di/admin/export?scope=reports&q=200"))
        self.assertIn("INQ-200", sheet)
        self.assertNotIn("INQ-100", sheet)
        self.assertNotIn("INQ-400", sheet)
        resp = self.client.get("/di/admin/export?scope=reports&manager=Mark+Manager")
        self.assertIn("pend_reports_filtered", resp.headers["Content-Disposition"])
        self.review("p1")
        sheet = self._sheet(self.client.get("/di/admin/export?scope=reviewed"))
        self.assertIn("INQ-100", sheet)
        self.assertNotIn("INQ-500", sheet)

    def test_export_escapes_text_and_formulas(self):
        self.fake.tables["Pend"][0]["REMARKS"] = '=HYPERLINK("http://x") <b>&'
        sheet = self._sheet(self.client.get("/di/admin/export?scope=all"))
        self.assertIn('t="inlineStr"', sheet)
        self.assertIn('<t xml:space="preserve">=HYPERLINK("http://x") &lt;b&gt;&amp;</t>', sheet)
        self.assertNotIn("<f>", sheet)  # stored as text, never as a formula


class SubStatusTests(AppTestCase):
    def test_associate_sets_sub_status(self):
        self.sign_in_di(0)
        token = self.csrf("/di/task-entry")
        self.client.post("/di/task-entry", data={"_csrf": token, "inquiry_number": "S-1", "sub_status": "  Awaiting   docs ",
                                                 "date_pended": dates.today().isoformat()})
        row = self.fake.tables["Pend"][0]
        self.assertEqual(row["SUB_STATUS"], "Awaiting docs")
        self.client.post(f"/di/update-pends/{row['id']}", data={"_csrf": token, "status": "Pending", "sub_status": "Escalated"})
        self.assertEqual(row["SUB_STATUS"], "Escalated")
        html = self.client.get(f"/di/update-pends?id={row['id']}").get_data(as_text=True)
        self.assertIn('name="sub_status" value="Escalated"', html)


if __name__ == "__main__":
    unittest.main()
