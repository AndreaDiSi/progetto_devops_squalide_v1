import unittest
import tests.helpers as helpers


def _create_group(client, name="Gruppo Test"):
    r = client.post("/groups/new", data={"group_name": name})
    location = r.headers.get("HX-Redirect", "")
    return int(location.split("/")[-1])


def _get_invitation_id(group_id):
    from database import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invitation_id FROM invitations WHERE group_id = %s", (group_id,))
            row = cur.fetchone()
    return row[0] if row else None


def _upload_file(client, content=b"contenuto di test", filename="test.txt"):
    return client.post("/upload", files={"file": (filename, content, "text/plain")})


class TestFolder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        helpers.create_test_db()

    def setUp(self):
        helpers.clean_tables()
        self.owner = helpers.register_and_login(helpers.new_client(), "owner")
        self.member = helpers.register_and_login(helpers.new_client(), "member")
        self.gid = _create_group(self.owner)
        # invita e fa entrare member
        self.owner.post(f"/groups/{self.gid}/invite", data={"username": "member"})
        inv_id = _get_invitation_id(self.gid)
        self.member.post(f"/invitations/{inv_id}/accept")

    # ── Accesso ──────────────────────────────────────────────────────────────

    def test_folder_requires_auth(self):
        guest = helpers.new_client()
        r = guest.get(f"/groups/{self.gid}/folder", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_non_member_cannot_access_folder(self):
        outsider = helpers.register_and_login(helpers.new_client(), "outsider")
        r = outsider.get(f"/groups/{self.gid}/folder")
        self.assertEqual(r.status_code, 403)

    def test_member_can_view_empty_folder(self):
        r = self.member.get(f"/groups/{self.gid}/folder")
        self.assertEqual(r.status_code, 200)

    # ── Upload diretto nel folder ─────────────────────────────────────────────

    def test_upload_to_folder_success(self):
        r = self.owner.post(
            f"/groups/{self.gid}/folder/upload",
            files={"file": ("doc.txt", b"testo del documento", "text/plain")},
        )
        self.assertIn("HX-Redirect", r.headers)
        self.assertEqual(r.headers["HX-Redirect"], f"/groups/{self.gid}/folder")

    def test_upload_to_folder_binary_rejected(self):
        r = self.owner.post(
            f"/groups/{self.gid}/folder/upload",
            files={"file": ("bin.txt", bytes([0x80, 0xFF]), "text/plain")},
        )
        self.assertNotIn("HX-Redirect", r.headers)
        self.assertIn("UTF-8", r.text)

    def test_uploaded_file_appears_in_folder(self):
        self.owner.post(
            f"/groups/{self.gid}/folder/upload",
            files={"file": ("visibile.txt", b"ciao", "text/plain")},
        )
        r = self.member.get(f"/groups/{self.gid}/folder")
        self.assertIn("visibile.txt", r.text)

    # ── Aggiungi doc dal profilo ──────────────────────────────────────────────

    def test_add_own_document_to_folder(self):
        _upload_file(self.owner, filename="mio.txt")
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT document_id FROM documents WHERE file_name = 'mio.txt'")
                doc_id = cur.fetchone()[0]

        r = self.owner.post(f"/groups/{self.gid}/folder/add", data={"document_id": doc_id})
        self.assertIn("HX-Redirect", r.headers)

    def test_cannot_add_other_users_document(self):
        _upload_file(self.member, filename="altrui.txt")
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT document_id FROM documents WHERE file_name = 'altrui.txt'")
                doc_id = cur.fetchone()[0]

        r = self.owner.post(f"/groups/{self.gid}/folder/add", data={"document_id": doc_id})
        self.assertNotIn("HX-Redirect", r.headers)

    def test_cannot_add_duplicate_document(self):
        self.owner.post(
            f"/groups/{self.gid}/folder/upload",
            files={"file": ("dup.txt", b"testo", "text/plain")},
        )
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT document_id FROM documents WHERE file_name = 'dup.txt'")
                doc_id = cur.fetchone()[0]

        r = self.owner.post(f"/groups/{self.gid}/folder/add", data={"document_id": doc_id})
        self.assertIn("già nel folder", r.text)

    # ── Visualizza documento nel folder ───────────────────────────────────────

    def _upload_to_folder_and_get_fdoc_id(self, client=None, filename="doc.txt"):
        c = client or self.owner
        c.post(
            f"/groups/{self.gid}/folder/upload",
            files={"file": (filename, b"contenuto", "text/plain")},
        )
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT fd.id FROM folder_documents fd
                       JOIN folders f ON fd.folder_id = f.folder_id
                       WHERE f.group_id = %s AND fd.is_deleted = FALSE
                       ORDER BY fd.created_at DESC LIMIT 1""",
                    (self.gid,),
                )
                return cur.fetchone()[0]

    def test_member_can_view_folder_document(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        r = self.member.get(f"/groups/{self.gid}/folder/{fdoc_id}/view")
        self.assertEqual(r.status_code, 200)
        self.assertIn("contenuto", r.text)

    def test_non_member_cannot_view_folder_document(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        outsider = helpers.register_and_login(helpers.new_client(), "outsider2")
        r = outsider.get(f"/groups/{self.gid}/folder/{fdoc_id}/view")
        self.assertEqual(r.status_code, 403)

    # ── Elimina documento dal folder (soft delete) ────────────────────────────

    def test_owner_can_delete_folder_document(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        r = self.owner.post(f"/groups/{self.gid}/folder/{fdoc_id}/delete")
        self.assertEqual(r.status_code, 200)
        r = self.owner.get(f"/groups/{self.gid}/folder")
        self.assertIn("Nessun documento nel folder", r.text)

    def test_member_without_permission_cannot_delete(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        r = self.member.post(f"/groups/{self.gid}/folder/{fdoc_id}/delete")
        self.assertEqual(r.status_code, 403)

    def test_delete_is_soft(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        self.owner.post(f"/groups/{self.gid}/folder/{fdoc_id}/delete")
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT is_deleted, deleted_at FROM folder_documents WHERE id = %s",
                    (fdoc_id,),
                )
                row = cur.fetchone()
        self.assertTrue(row[0])
        self.assertIsNotNone(row[1])

    # ── Modifica documento nel folder ─────────────────────────────────────────

    def test_owner_can_edit_folder_document(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        r = self.owner.post(
            f"/groups/{self.gid}/folder/{fdoc_id}/edit",
            data={"content": "nuovo contenuto"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 302)
        r = self.owner.get(f"/groups/{self.gid}/folder/{fdoc_id}/view")
        self.assertIn("nuovo contenuto", r.text)

    def test_member_without_permission_cannot_edit(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        r = self.member.get(f"/groups/{self.gid}/folder/{fdoc_id}/edit")
        self.assertEqual(r.status_code, 403)

    # ── Permessi ─────────────────────────────────────────────────────────────

    def _get_member_user_id(self):
        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE username = 'member'")
                return cur.fetchone()[0]

    def test_owner_can_grant_edit_permission(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        member_id = self._get_member_user_id()
        self.owner.post(
            f"/groups/{self.gid}/folder/{fdoc_id}/permissions",
            data={"target_user_id": member_id, "can_edit": "true", "can_delete": "false"},
        )
        r = self.member.get(f"/groups/{self.gid}/folder/{fdoc_id}/edit")
        self.assertEqual(r.status_code, 200)

    def test_member_with_delete_permission_can_delete(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        member_id = self._get_member_user_id()
        self.owner.post(
            f"/groups/{self.gid}/folder/{fdoc_id}/permissions",
            data={"target_user_id": member_id, "can_edit": "false", "can_delete": "true"},
        )
        r = self.member.post(f"/groups/{self.gid}/folder/{fdoc_id}/delete")
        self.assertEqual(r.status_code, 200)

    def test_non_owner_cannot_set_permissions(self):
        fdoc_id = self._upload_to_folder_and_get_fdoc_id()
        member_id = self._get_member_user_id()
        r = self.member.post(
            f"/groups/{self.gid}/folder/{fdoc_id}/permissions",
            data={"target_user_id": member_id, "can_edit": "true", "can_delete": "true"},
        )
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
