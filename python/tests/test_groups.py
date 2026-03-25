import unittest
import tests.helpers as helpers


def _get_group_id_from_redirect(response):
    location = response.headers.get("HX-Redirect", "")
    return int(location.split("/")[-1])


def _get_invitation_id(group_id):
    from database import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invitation_id FROM invitations WHERE group_id = %s", (group_id,))
            row = cur.fetchone()
    return row[0] if row else None


class TestGroups(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        helpers.create_test_db()

    def setUp(self):
        helpers.clean_tables()
        self.owner = helpers.register_and_login(helpers.new_client(), "owner")
        self.member = helpers.register_and_login(helpers.new_client(), "member")

    def _create_group(self, name="Gruppo Test"):
        return self.owner.post("/groups/new", data={"group_name": name})

    def _create_group_and_get_id(self, name="Gruppo Test"):
        r = self._create_group(name)
        return _get_group_id_from_redirect(r)

    def _invite(self, group_id, username="member"):
        return self.owner.post(f"/groups/{group_id}/invite", data={"username": username})

    def _accept(self, inv_id):
        return self.member.post(f"/invitations/{inv_id}/accept")

    def _reject(self, inv_id):
        return self.member.post(f"/invitations/{inv_id}/reject")

    # ── Creazione gruppo ──────────────────────────────────────────────────────

    def test_create_group_success(self):
        r = self._create_group()
        self.assertEqual(r.status_code, 200)
        self.assertIn("HX-Redirect", r.headers)
        self.assertIn("/groups/", r.headers["HX-Redirect"])

    def test_created_group_visible_in_list(self):
        self._create_group("Mio Gruppo")
        r = self.owner.get("/groups")
        self.assertIn("Mio Gruppo", r.text)

    # ── Invito utente ─────────────────────────────────────────────────────────

    def test_invite_user_success(self):
        gid = self._create_group_and_get_id()
        r = self._invite(gid)
        self.assertIn("Invito inviato", r.text)

    def test_invite_nonexistent_user(self):
        gid = self._create_group_and_get_id()
        r = self.owner.post(f"/groups/{gid}/invite", data={"username": "nessuno"})
        self.assertIn("non trovato", r.text)

    def test_invite_self_fails(self):
        gid = self._create_group_and_get_id()
        r = self.owner.post(f"/groups/{gid}/invite", data={"username": "owner"})
        self.assertIn("te stesso", r.text)

    def test_invite_already_member_fails(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)
        r = self._invite(gid)  # re-invito a chi è già dentro
        self.assertIn("già nel gruppo", r.text)

    def test_invite_requires_owner(self):
        gid = self._create_group_and_get_id()
        r = self.member.post(f"/groups/{gid}/invite", data={"username": "owner"})
        self.assertIn("proprietario", r.text)

    def test_duplicate_pending_invite(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        r = self._invite(gid)  # secondo invito a pending
        self.assertIn("già inviato", r.text)

    # ── Accetta / Rifiuta ─────────────────────────────────────────────────────

    def test_accept_invitation_adds_to_group(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)

        r = self.owner.get(f"/groups/{gid}")
        self.assertIn("member", r.text)

    def test_reject_invitation(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        r = self._reject(inv_id)
        self.assertEqual(r.status_code, 200)

        r = self.member.get(f"/groups/{gid}", follow_redirects=False)
        self.assertEqual(r.status_code, 403)  # non è membro

    def test_invitation_visible_on_dashboard(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        r = self.member.get("/dashboard")
        self.assertIn("Gruppo Test", r.text)

    # ── Uscita dal gruppo ─────────────────────────────────────────────────────

    def test_leave_group(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)

        r = self.member.post(f"/groups/{gid}/leave")
        self.assertIn("HX-Redirect", r.headers)

        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_groups WHERE group_id = %s", (gid,)
                )
                count = cur.fetchone()[0]
        self.assertEqual(count, 1)  # solo owner rimasto

    def test_owner_cannot_leave(self):
        gid = self._create_group_and_get_id()
        r = self.owner.post(f"/groups/{gid}/leave")
        self.assertIn("proprietario", r.text)

    # ── Ri-invito dopo uscita ─────────────────────────────────────────────────

    def test_reinvite_after_leave(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)
        self.member.post(f"/groups/{gid}/leave")

        r = self._invite(gid)  # ri-invito
        self.assertIn("Invito inviato", r.text)

    # ── Eliminazione gruppo ───────────────────────────────────────────────────

    def test_delete_group_as_owner(self):
        gid = self._create_group_and_get_id()
        r = self.owner.post(f"/groups/{gid}/delete")
        self.assertIn("HX-Redirect", r.headers)

        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM groups WHERE group_id = %s", (gid,))
                self.assertIsNone(cur.fetchone())

    def test_delete_group_as_non_owner_fails(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)

        r = self.member.post(f"/groups/{gid}/delete", follow_redirects=False)
        self.assertEqual(r.status_code, 403)

    def test_delete_group_removes_all_members(self):
        gid = self._create_group_and_get_id()
        self._invite(gid)
        inv_id = _get_invitation_id(gid)
        self._accept(inv_id)
        self.owner.post(f"/groups/{gid}/delete")

        from database import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM user_groups WHERE group_id = %s", (gid,))
                self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
