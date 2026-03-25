import unittest
import tests.helpers as helpers  # deve essere il primo import


class TestAuth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        helpers.create_test_db()

    def setUp(self):
        helpers.clean_tables()
        self.client = helpers.new_client()

    # ── Registrazione ────────────────────────────────────────────────────────

    def test_register_success(self):
        r = self.client.post("/register", data={
            "username": "user1", "email": "u1@test.com", "password": "pw"
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("HX-Redirect", r.headers)
        self.assertEqual(r.headers["HX-Redirect"], "/login")

    def test_register_duplicate_username(self):
        self.client.post("/register", data={"username": "user1", "email": "u1@test.com", "password": "pw"})
        r = self.client.post("/register", data={"username": "user1", "email": "u2@test.com", "password": "pw"})
        self.assertIn("già in uso", r.text)
        self.assertNotIn("HX-Redirect", r.headers)

    def test_register_duplicate_email(self):
        self.client.post("/register", data={"username": "user1", "email": "u1@test.com", "password": "pw"})
        r = self.client.post("/register", data={"username": "user2", "email": "u1@test.com", "password": "pw"})
        self.assertIn("già in uso", r.text)

    # ── Login ────────────────────────────────────────────────────────────────

    def test_login_success(self):
        self.client.post("/register", data={"username": "user1", "email": "u1@test.com", "password": "pw"})
        r = self.client.post("/login", data={"username": "user1", "password": "pw"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("HX-Redirect", r.headers)
        self.assertEqual(r.headers["HX-Redirect"], "/dashboard")

    def test_login_wrong_password(self):
        self.client.post("/register", data={"username": "user1", "email": "u1@test.com", "password": "pw"})
        r = self.client.post("/login", data={"username": "user1", "password": "sbagliata"})
        self.assertIn("Credenziali non valide", r.text)
        self.assertNotIn("HX-Redirect", r.headers)

    def test_login_nonexistent_user(self):
        r = self.client.post("/login", data={"username": "nessuno", "password": "pw"})
        self.assertIn("Credenziali non valide", r.text)

    # ── Accesso protetto ─────────────────────────────────────────────────────

    def test_dashboard_requires_auth(self):
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["location"])

    def test_logout_clears_session(self):
        self.client.post("/register", data={"username": "user1", "email": "u1@test.com", "password": "pw"})
        self.client.post("/login", data={"username": "user1", "password": "pw"})
        # Dashboard accessibile
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 200)
        # Dopo logout
        self.client.get("/logout")
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)


if __name__ == "__main__":
    unittest.main()
