"""Enterprise Dashboard (left-nav Dashboard) — all Pend records, shared by Associate and Admin modules."""
import io
import json
import re
import unittest
import zipfile
from datetime import timedelta

from apex import dates
from tests.base import AppTestCase

TODAY = dates.today()


def pend(pid, **extra):
    row = {"id": pid, "INQUIRY_NUMBER": f"INQ-{pid}", "STATUS": "Pending", "DOMAIN": "XX00000", "ASSIGNED_TO": "Ann Lee",
           "MANAGER": "Mark Manager", "SUB_STATUS": None, "REMARKS": f"remark {pid}", "PEND_REVIEW": None,
           "REVIEWER": None, "REVIEWER_REMARKS": None, "DATE_REVIEWED": None, "REVIEWER_DOMAIN": None,
           "DATE_PENDED": (TODAY - timedelta(days=5)).isoformat(), "ACKNOWLEDGED": False, "PENDED_DAYS": 5}
    row.update(extra)
    return row


def seed():
    return [
        pend("1"),
        pend("2", STATUS="Completed", PEND_REVIEW="Valid", REVIEWER="Rita", DATE_REVIEWED=TODAY.isoformat(),
             REVIEWER_REMARKS="ok"),
        pend("3", MANAGER="Other Boss", ASSIGNED_TO="Bo Chan", PEND_REVIEW="Invalid", REVIEWER="Rita",
             DATE_REVIEWED=TODAY.isoformat(), SUB_STATUS="Escalated"),
        pend("4", MANAGER="Other Boss", ASSIGNED_TO="Bo Chan", STATUS="Completed", SUB_STATUS="Escalated",
             DATE_PENDED=(TODAY - timedelta(days=40)).isoformat()),
        pend("5", MANAGER=None, STATUS="In Progress"),
    ]


class EnterpriseDashboardTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.fake.tables["Pend"] = seed()

    def kpis(self, html):
        return dict(re.findall(r'sk-kpi-label">([^<]+)</p>\s*<p class="sk-kpi-value" data-count="(\d+)"', html))

    def charts(self, html):
        return json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1))

    def check_full_view(self, url):
        html = self.client.get(url).get_data(as_text=True)
        self.assertIn("Executive Dashboard", html)
        self.assertEqual(self.kpis(html), {"Total Pending": "2", "Total Completed": "2", "Total Valid": "1",
                                           "Total Invalid": "1"})
        charts = self.charts(html)
        self.assertEqual([s["value"] for s in charts["status_split"]], [2, 2])
        self.assertEqual([s["value"] for s in charts["review_split"]], [1, 1])
        self.assertEqual({d["label"]: d["value"] for d in charts["distribution"]},
                         {"Pending": 2, "Completed": 2, "In Progress": 1})
        managers = {m["label"]: m for m in charts["managers"]}
        self.assertEqual((managers["Mark Manager"]["pending"], managers["Mark Manager"]["completed"],
                          managers["Mark Manager"]["valid"]), (1, 1, 1))
        self.assertEqual((managers["Other Boss"]["pending"], managers["Other Boss"]["completed"],
                          managers["Other Boss"]["invalid"]), (1, 1, 1))
        self.assertIn("(No manager)", managers)
        self.assertEqual(sum(d["count"] for d in charts["trend"]), 2)
        for header in ("Status", "Remarks", "Assigned To", "Sub Status", "Manager", "Pend Review", "Reviewer",
                       "Reviewer Remarks", "Date Reviewed"):
            self.assertIn(f">\n    {header}<span", html)
        for pid in "12345":
            self.assertIn(f"INQ-{pid}", html)
        return html

    def test_associate_sees_entire_pend_table(self):
        self.sign_in_di(0)  # AA11111 owns none of these rows
        self.check_full_view("/di/dashboards")

    def test_admin_sees_same_data(self):
        self.sign_in_di(1)
        self.check_full_view("/di/admin/dashboards")

    def test_filters_refresh_everything(self):
        self.sign_in_di(0)
        html = self.client.get("/di/dashboards?manager=Other+Boss").get_data(as_text=True)
        self.assertEqual(self.kpis(html), {"Total Pending": "1", "Total Completed": "1", "Total Valid": "0",
                                           "Total Invalid": "1"})
        self.assertEqual([m["label"] for m in self.charts(html)["managers"]], ["Other Boss"])
        self.assertNotIn("INQ-1<", html)
        html = self.client.get("/di/dashboards?assigned_to=Bo+Chan&sub_status=Escalated").get_data(as_text=True)
        self.assertEqual(self.kpis(html)["Total Completed"], "1")
        frm = (TODAY - timedelta(days=10)).isoformat()
        html = self.client.get(f"/di/dashboards?from={frm}").get_data(as_text=True)
        self.assertNotIn("INQ-4<", html)
        self.assertIn("INQ-3<", html)
        self.assertIn("data-auto-refresh", html)
        for opt in ("<option>Mark Manager</option>", "<option>Bo Chan</option>", "<option>Escalated</option>"):
            self.assertIn(opt, self.client.get("/di/dashboards").get_data(as_text=True))

    def test_report_search_sort_and_pagination(self):
        self.fake.tables["Pend"] += [pend(f"p{i:02d}", REMARKS="bulk") for i in range(30)]
        self.sign_in_di(1)
        html = self.client.get("/di/admin/dashboards").get_data(as_text=True)
        self.assertIn("Page 1 of 2", html)
        self.assertIn("Showing 1–25 of 35", html)
        html = self.client.get("/di/admin/dashboards?page=2").get_data(as_text=True)
        self.assertIn("Showing 26–35 of 35", html)
        html = self.client.get("/di/admin/dashboards?q=remark+3").get_data(as_text=True)
        body = html.split("<tbody>")[1]
        self.assertEqual(re.findall(r"<strong>(INQ-[^<]+)</strong>", body), ["INQ-3"])
        html = self.client.get("/di/admin/dashboards?sort=ASSIGNED_TO&dir=asc&q=Chan").get_data(as_text=True)
        self.assertEqual(re.findall(r"<strong>(INQ-[^<]+)</strong>", html.split("<tbody>")[1]), ["INQ-3", "INQ-4"])
        html = self.client.get("/di/admin/dashboards?sort=INQUIRY_NUMBER&dir=desc").get_data(as_text=True)
        self.assertIn('aria-sort="descending"', html)
        self.assertIn("sort=INQUIRY_NUMBER", html)

    def _sheet(self, resp):
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return zipfile.ZipFile(io.BytesIO(resp.data)).read("xl/worksheets/sheet1.xml").decode()

    def test_export_filtered_and_all(self):
        self.sign_in_di(0)
        sheet = self._sheet(self.client.get("/di/dashboards/export?scope=filtered&manager=Other+Boss"))
        self.assertIn("INQ-3", sheet)
        self.assertNotIn("INQ-1<", sheet)
        resp = self.client.get("/di/dashboards/export?scope=all")
        self.assertIn("apex_pends_all_", resp.headers["Content-Disposition"])
        sheet = self._sheet(resp)
        for pid in "12345":
            self.assertIn(f"INQ-{pid}", sheet)
        self.assertNotIn("PASSWORD", sheet)

    def test_empty_table(self):
        self.fake.tables["Pend"] = []
        self.sign_in_di(1)
        html = self.client.get("/di/admin/dashboards").get_data(as_text=True)
        self.assertIn("The Pend table has no records yet.", html)
        self.assertEqual(self.kpis(html)["Total Pending"], "0")


if __name__ == "__main__":
    unittest.main()
