from pathlib import Path
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import psycopg2

from database import get_conn, init_db
from mongo import documents

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="scuola-secret")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def startup():
    init_db()


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                    (username, email, password),
                )
            conn.commit()
    except psycopg2.errors.UniqueViolation:
        return HTMLResponse('<p id="msg" class="text-red-500 text-sm mt-2">Username o email già in uso.</p>')

    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/login"
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username FROM users WHERE username = %s AND password_hash = %s",
                (username, password),
            )
            user = cur.fetchone()

    if not user:
        return HTMLResponse('<p id="msg" class="text-red-500 text-sm mt-2">Credenziali non valide.</p>')

    request.session["user_id"] = user[0]
    request.session["username"] = user[1]
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/dashboard"
    return resp


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, email, created_at FROM users WHERE user_id = %s",
                (user_id,),
            )
            user = cur.fetchone()

            cur.execute(
                """SELECT g.group_id, g.group_name FROM groups g
                   JOIN user_groups ug ON g.group_id = ug.group_id
                   WHERE ug.user_id = %s""",
                (user_id,),
            )
            groups = cur.fetchall()

            cur.execute(
                """SELECT i.invitation_id, g.group_name, u.username
                   FROM invitations i
                   JOIN groups g ON i.group_id = g.group_id
                   JOIN users u ON i.inviter_id = u.user_id
                   WHERE i.invitee_id = %s AND i.status = 'pending'""",
                (user_id,),
            )
            invitations = cur.fetchall()

    doc_count = documents.count_documents({"user_id": user_id})
    recent_docs = list(
        documents.find({"user_id": user_id}, {"content": 0})
        .sort("uploaded_at", -1)
        .limit(5)
    )
    for d in recent_docs:
        d["id"] = str(d["_id"])

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": {"username": user[0], "email": user[1], "created_at": user[2]},
        "groups": [{"id": g[0], "name": g[1]} for g in groups],
        "doc_count": doc_count,
        "recent_docs": recent_docs,
        "invitations": [{"id": i[0], "group_name": i[1], "inviter": i[2]} for i in invitations],
    })


# ── Gruppi ────────────────────────────────────────────────────────────────────

@app.get("/groups", response_class=HTMLResponse)
def list_groups(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT g.group_id, g.group_name, u.username,
                          (SELECT COUNT(*) FROM user_groups ug WHERE ug.group_id = g.group_id) AS members
                   FROM groups g
                   JOIN users u ON g.group_owner = u.user_id
                   JOIN user_groups ug2 ON g.group_id = ug2.group_id
                   WHERE ug2.user_id = %s""",
                (user_id,),
            )
            groups = cur.fetchall()

    return templates.TemplateResponse("groups.html", {
        "request": request,
        "groups": [{"id": g[0], "name": g[1], "owner": g[2], "members": g[3]} for g in groups],
    })


@app.post("/groups/new", response_class=HTMLResponse)
def create_group(request: Request, group_name: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO groups (group_owner, group_name) VALUES (%s, %s) RETURNING group_id",
                (user_id, group_name),
            )
            group_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s)",
                (user_id, group_id),
            )
        conn.commit()

    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = f"/groups/{group_id}"
    return resp


@app.get("/groups/{group_id}", response_class=HTMLResponse)
def view_group(request: Request, group_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT group_id, group_name, group_owner FROM groups WHERE group_id = %s",
                (group_id,),
            )
            group = cur.fetchone()
            if not group:
                return HTMLResponse("Gruppo non trovato.", status_code=404)

            cur.execute(
                """SELECT u.user_id, u.username FROM users u
                   JOIN user_groups ug ON u.user_id = ug.user_id
                   WHERE ug.group_id = %s""",
                (group_id,),
            )
            members = cur.fetchall()

            cur.execute(
                """SELECT u.username, i.status FROM invitations i
                   JOIN users u ON i.invitee_id = u.user_id
                   WHERE i.group_id = %s AND i.status = 'pending'""",
                (group_id,),
            )
            pending = cur.fetchall()

    is_owner = group[2] == user_id
    is_member = any(m[0] == user_id for m in members)
    if not is_member:
        return HTMLResponse("Non sei membro di questo gruppo.", status_code=403)

    return templates.TemplateResponse("group.html", {
        "request": request,
        "group": {"id": group[0], "name": group[1], "owner_id": group[2]},
        "members": [{"id": m[0], "username": m[1]} for m in members],
        "pending": [{"username": p[0]} for p in pending],
        "is_owner": is_owner,
    })


@app.post("/groups/{group_id}/invite", response_class=HTMLResponse)
def invite_user(request: Request, group_id: int, username: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Solo il proprietario può invitare
            cur.execute("SELECT group_owner FROM groups WHERE group_id = %s", (group_id,))
            row = cur.fetchone()
            if not row or row[0] != user_id:
                return HTMLResponse('<p id="invite-msg" class="text-red-500 text-sm">Solo il proprietario può invitare.</p>')

            cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            invitee = cur.fetchone()
            if not invitee:
                return HTMLResponse('<p id="invite-msg" class="text-red-500 text-sm">Utente non trovato.</p>')

            invitee_id = invitee[0]
            if invitee_id == user_id:
                return HTMLResponse('<p id="invite-msg" class="text-red-500 text-sm">Non puoi invitare te stesso.</p>')

            # Già membro?
            cur.execute(
                "SELECT 1 FROM user_groups WHERE user_id = %s AND group_id = %s",
                (invitee_id, group_id),
            )
            if cur.fetchone():
                return HTMLResponse('<p id="invite-msg" class="text-red-500 text-sm">Utente già nel gruppo.</p>')

            # Rimuove inviti precedenti (accettati/rifiutati) per permettere il re-invito
            cur.execute(
                "DELETE FROM invitations WHERE group_id = %s AND invitee_id = %s AND status != 'pending'",
                (group_id, invitee_id),
            )
            try:
                cur.execute(
                    "INSERT INTO invitations (group_id, inviter_id, invitee_id) VALUES (%s, %s, %s)",
                    (group_id, user_id, invitee_id),
                )
                conn.commit()
            except psycopg2.errors.UniqueViolation:
                return HTMLResponse('<p id="invite-msg" class="text-red-500 text-sm">Invito già inviato.</p>')

    return HTMLResponse(f'<p id="invite-msg" class="text-green-600 text-sm">Invito inviato a {username}.</p>')


@app.post("/invitations/{inv_id}/accept", response_class=HTMLResponse)
def accept_invitation(request: Request, inv_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT group_id FROM invitations WHERE invitation_id = %s AND invitee_id = %s AND status = 'pending'",
                (inv_id, user_id),
            )
            inv = cur.fetchone()
            if not inv:
                return HTMLResponse("")

            cur.execute(
                "UPDATE invitations SET status = 'accepted' WHERE invitation_id = %s",
                (inv_id,),
            )
            cur.execute(
                "INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, inv[0]),
            )
        conn.commit()

    return HTMLResponse(f'<div id="inv-{inv_id}"></div>')


@app.post("/invitations/{inv_id}/reject", response_class=HTMLResponse)
def reject_invitation(request: Request, inv_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE invitations SET status = 'rejected' WHERE invitation_id = %s AND invitee_id = %s",
                (inv_id, user_id),
            )
        conn.commit()

    return HTMLResponse(f'<div id="inv-{inv_id}"></div>')


@app.post("/groups/{group_id}/delete", response_class=HTMLResponse)
def delete_group(request: Request, group_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT group_owner FROM groups WHERE group_id = %s", (group_id,))
            row = cur.fetchone()
            if not row or row[0] != user_id:
                return HTMLResponse("Non autorizzato.", status_code=403)

            cur.execute("DELETE FROM user_groups WHERE group_id = %s", (group_id,))
            cur.execute("DELETE FROM groups WHERE group_id = %s", (group_id,))
        conn.commit()

    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/groups"
    return resp


@app.post("/groups/{group_id}/leave", response_class=HTMLResponse)
def leave_group(request: Request, group_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT group_owner FROM groups WHERE group_id = %s", (group_id,))
            row = cur.fetchone()
            if not row:
                return HTMLResponse("Gruppo non trovato.", status_code=404)
            if row[0] == user_id:
                return HTMLResponse('<p class="text-red-500 text-sm">Il proprietario non può uscire dal gruppo.</p>')

            cur.execute(
                "DELETE FROM user_groups WHERE user_id = %s AND group_id = %s",
                (user_id, group_id),
            )
        conn.commit()

    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/groups"
    return resp


# ── Documenti ─────────────────────────────────────────────────────────────────

@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload", response_class=HTMLResponse)
async def upload(request: Request, file: UploadFile = File(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return HTMLResponse('<p id="msg" class="text-red-500 text-sm mt-2">Solo file di testo UTF-8.</p>')

    documents.insert_one({
        "filename": file.filename,
        "content": text,
        "user_id": user_id,
        "uploaded_at": datetime.now(timezone.utc),
    })
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/documents"
    return resp


@app.get("/documents", response_class=HTMLResponse)
def list_documents(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    docs = list(documents.find({"user_id": user_id}, {"content": 0}).sort("uploaded_at", -1))
    for d in docs:
        d["id"] = str(d["_id"])
    return templates.TemplateResponse("documents.html", {"request": request, "docs": docs})


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
def view_document(request: Request, doc_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    doc = documents.find_one({"_id": ObjectId(doc_id), "user_id": user_id})
    if not doc:
        return HTMLResponse("Documento non trovato.", status_code=404)
    return templates.TemplateResponse("document.html", {"request": request, "doc": doc})


@app.post("/documents/{doc_id}/delete", response_class=HTMLResponse)
def delete_document(request: Request, doc_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)

    documents.delete_one({"_id": ObjectId(doc_id), "user_id": user_id})
    resp = HTMLResponse("")
    resp.headers["HX-Redirect"] = "/documents"
    return resp


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
