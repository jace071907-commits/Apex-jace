import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APEX_SECRET_KEY", "test-secret")

from apex import create_app, security, users  # noqa: E402
from tests.fake_supabase import FakeSupabase  # noqa: E402

PATCHED_MODULES = ("users", "routes.auth", "routes.main", "pends", "reviews", "notifications", "preferences")


def make_users():
    return [
        {"DOMAIN": "AA11111", "PASSWORD": "Temp123", "ROLE": "Associate", "ASSOCIATE NAME": "Jane Doe",
         "EMPLOYEE NUMBER": "1001", "PROGRAM": "Disputes and Intakes", "AM": "A M", "MANAGER NAME": "Mark Manager",
         "OM": "O M", "EMAIL ADDRESS": None},
        {"DOMAIN": "BB22222", "PASSWORD": "Temp456", "ROLE": "Supervisor", "ASSOCIATE NAME": "John Roe",
         "EMPLOYEE NUMBER": "1002", "PROGRAM": "", "AM": "", "MANAGER NAME": "", "OM": "", "EMAIL ADDRESS": None},
    ]


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSupabase({"User": make_users(), "Pend": []})
        for module in PATCHED_MODULES:
            patcher = mock.patch(f"apex.{module}.supabase", self.fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @property
    def user_rows(self):
        return self.fake.tables["User"]

    def csrf(self, path="/login"):
        html = self.client.get(path).get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

    def login(self, user, pw, portal):
        return self.client.post("/login", data={"_csrf": self.csrf(), "username": user, "password": pw, "portal": portal})

    def activate(self, index=0, password="Str0ngPass1", email=None):
        """Make a user fully set up (hashed password + Auth identity + Carelon email)."""
        row = self.user_rows[index]
        row["PASSWORD"] = security.hash_password(password)
        row["EMAIL ADDRESS"] = email or row["ASSOCIATE NAME"].lower().replace(" ", ".") + "@carelon.com"
        self.fake.admin_upsert_user(users.auth_user_id(row["DOMAIN"]), users.auth_email(row["DOMAIN"]), password)
        return row

    def sign_in_di(self, index=0):
        row = self.activate(index)
        portal = "associate" if row["ROLE"] == "Associate" else "admin"
        self.login(row["DOMAIN"], "Str0ngPass1", portal)
        r = self.client.post("/programs", data={"_csrf": self.csrf("/programs"), "program": "di"})
        landing = "/di/task-entry" if portal == "associate" else "/di/admin/pend-reports"
        self.assertTrue(r.headers["Location"].endswith(landing), r.headers.get("Location"))
        return row


__all__ = ["AppTestCase", "create_app", "security", "users"]
