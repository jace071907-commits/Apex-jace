"""Authentication, first-time setup and RBAC tests.

Run:  python -m unittest discover -s tests -v
"""
import unittest

from tests.base import AppTestCase, security, users


class AuthFlowTests(AppTestCase):
    def test_pages_require_login(self):
        for path in ("/programs", "/di/task-entry", "/di/dashboard", "/administration", "/profile", "/settings"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers["Location"])
        self.assertEqual(self.client.get("/api/notifications").status_code, 302)

    def test_csrf_enforced(self):
        r = self.client.post("/login", data={"username": "AA11111", "password": "Temp123", "portal": "associate"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_credentials(self):
        r = self.login("AA11111", "wrong", "associate")
        self.assertIn("Invalid username or password.", r.get_data(as_text=True))

    def test_portal_role_enforcement(self):
        r = self.login("BB22222", "Temp456", "associate")
        self.assertIn("You are not authorized to use Associate Login.", r.get_data(as_text=True))
        r = self.login("AA11111", "Temp123", "admin")
        self.assertIn("You are not authorized to use Admin Login.", r.get_data(as_text=True))

    def test_first_time_setup_flow(self):
        r = self.login("aa11111", "Temp123", "associate")
        self.assertTrue(r.headers["Location"].endswith("/setup/password"))
        self.assertTrue(self.client.get("/programs").headers["Location"].endswith("/setup/password"))

        token = self.csrf("/setup/password")
        r = self.client.post("/setup/password", data={"_csrf": token, "new_password": "weak", "confirm_password": "weak"})
        self.assertIn("Password must contain", r.get_data(as_text=True))
        r = self.client.post("/setup/password", data={"_csrf": token, "new_password": "Str0ngPass", "confirm_password": "Str0ngPass"})
        self.assertTrue(r.headers["Location"].endswith("/setup/email"))
        self.assertTrue(security.is_hashed(self.user_rows[0]["PASSWORD"]))
        self.assertEqual(self.fake.auth[users.auth_email("AA11111")]["password"], "Str0ngPass")

        token = self.csrf("/setup/email")
        r = self.client.post("/setup/email", data={"_csrf": token, "email": "jane.doe@gmail.com"})
        self.assertIn("Please enter a valid Carelon email address.", r.get_data(as_text=True))
        r = self.client.post("/setup/email", data={"_csrf": token, "email": "Jane.Doe@carelon.com"})
        self.assertTrue(r.headers["Location"].endswith("/setup/complete"))
        self.assertEqual(self.user_rows[0]["EMAIL ADDRESS"], "jane.doe@carelon.com")
        self.assertIn("Account Successfully Created", self.client.get("/setup/complete").get_data(as_text=True))

        html = self.client.get("/programs").get_data(as_text=True)
        self.assertIn("Jane Doe", html)
        self.assertNotIn("Administration", html)
        self.assertEqual(self.client.get("/administration").status_code, 403)

        self.client.post("/logout", data={"_csrf": self.csrf("/programs")})
        self.assertEqual(self.client.get("/programs").status_code, 302)
        self.assertIn("Invalid username or password.", self.login("AA11111", "Temp123", "associate").get_data(as_text=True))
        self.assertTrue(self.login("AA11111", "Str0ngPass", "associate").headers["Location"].endswith("/programs"))

    def test_admin_access_and_role_change(self):
        self.activate(1)
        self.assertTrue(self.login("BB22222", "Str0ngPass1", "admin").headers["Location"].endswith("/programs"))
        html = self.client.get("/administration").get_data(as_text=True)
        self.assertIn("Employee Masterlist", html)
        self.assertNotIn("Temp456", html)
        self.user_rows[1]["ROLE"] = "Associate"
        self.assertIn("/login", self.client.get("/programs").headers["Location"])

    def test_email_rules(self):
        for ok in ("john.ariola@carelon.com", "juan.delacruz@carelon.com", "ana.de-leon@carelon.com"):
            self.assertTrue(security.is_carelon_email(ok), ok)
        for bad in ("john@carelon.com", "john.ariola@carelon.co", "john.ariola@gmail.com", "john..a@carelon.com",
                    "john.ariola@carelon.com.evil.io"):
            self.assertFalse(security.is_carelon_email(bad), bad)


if __name__ == "__main__":
    unittest.main()
