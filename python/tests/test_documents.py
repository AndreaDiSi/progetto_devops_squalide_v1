import unittest
import tests.helpers as helpers


class TestDocuments(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        helpers.create_test_db()

    def setUp(self):
        helpers.clean_tables()
        self.client = helpers.register_and_login(helpers.new_client(), "docuser")

    def _upload(self, content=b"contenuto di test", filename="test.txt"):
        return self.client.post(
            "/upload",
            files={"file": (filename, content, "text/plain")},
        )

    # ── Upload ───────────────────────────────────────────────────────────────

    def test_upload_requires_auth(self):
        guest = helpers.new_client()
        r = guest.get("/upload", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_upload_txt_success(self):
        r = self._upload()
        self.assertEqual(r.status_code, 200)
        self.assertIn("HX-Redirect", r.headers)
        self.assertEqual(r.headers["HX-Redirect"], "/documents")

    def test_upload_binary_rejected(self):
        r = self._upload(content=bytes([0x80, 0x81, 0x82, 0xFF]), filename="bin.txt")
        self.assertIn("UTF-8", r.text)
        self.assertNotIn("HX-Redirect", r.headers)

    # ── Lista documenti ──────────────────────────────────────────────────────

    def test_list_documents_empty(self):
        r = self.client.get("/documents")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Nessun documento", r.text)

    def test_list_documents_shows_uploaded(self):
        self._upload(filename="mio_file.txt")
        r = self.client.get("/documents")
        self.assertIn("mio_file.txt", r.text)

    # ── Visualizzazione ──────────────────────────────────────────────────────

    def test_view_document(self):
        self._upload(content=b"hello world")
        r = self.client.get("/documents")
        # Estrae il primo link href="/documents/<id>"
        import re
        match = re.search(r'href="/documents/([a-f0-9]{24})"', r.text)
        self.assertIsNotNone(match)
        doc_id = match.group(1)

        r = self.client.get(f"/documents/{doc_id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("hello world", r.text)

    def test_other_user_cannot_view_document(self):
        self._upload(content=b"segreto")
        r = self.client.get("/documents")
        import re
        match = re.search(r'href="/documents/([a-f0-9]{24})"', r.text)
        doc_id = match.group(1)

        other = helpers.register_and_login(helpers.new_client(), "altrouser")
        r = other.get(f"/documents/{doc_id}")
        self.assertEqual(r.status_code, 404)

    # ── Cancellazione ────────────────────────────────────────────────────────

    def test_delete_document(self):
        self._upload(filename="da_cancellare.txt")
        r = self.client.get("/documents")
        import re
        match = re.search(r'href="/documents/([a-f0-9]{24})"', r.text)
        doc_id = match.group(1)

        r = self.client.post(f"/documents/{doc_id}/delete")
        self.assertEqual(r.status_code, 200)
        self.assertIn("HX-Redirect", r.headers)

        r = self.client.get("/documents")
        self.assertIn("Nessun documento", r.text)


if __name__ == "__main__":
    unittest.main()
