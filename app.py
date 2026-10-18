import json, os, time
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, redirect, abort

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("FEEDBACK_DIR", str(ROOT / "data")))
DATA.mkdir(parents=True, exist_ok=True)
LOG = DATA / "proposal-feedback.jsonl"
TOKEN = os.environ.get("FEEDBACK_TOKEN", "")
ALLOWED = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff2", ".pdf"}
ALLOWED_ORIGINS = {
    "robotist.com.au",
    "www.robotist.com.au",
    "robotist-web.onrender.com",
    "robotist-proposal.onrender.com",
    "localhost:8000",
    "127.0.0.1:8000",
}
RATE = {}

app = Flask(__name__)


@app.get("/")
def home():
    return redirect("/proposals/looi-marriott-proposal.html", 302)


@app.get("/healthz")
def health():
    return jsonify(ok=True)


@app.get("/proposals/<path:name>")
def proposal(name):
    p = ROOT / "proposals" / name
    if not p.is_file() or p.suffix.lower() not in ALLOWED:
        abort(404)
    return send_from_directory(ROOT / "proposals", name)


@app.post("/api/proposal-feedback")
def post_feedback():
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    now = time.time()
    if now - RATE.get(ip, 0) < 5:
        return jsonify(ok=False, error="slow down"), 429
    RATE[ip] = now
    d = request.get_json(silent=True) or request.form.to_dict() or {}
    name = str(d.get("name", ""))[:120].strip()
    email = str(d.get("email", ""))[:160].strip()
    stance = str(d.get("stance", ""))[:60].strip()
    notes = str(d.get("notes", ""))[:4000].strip()
    if not name or "@" not in email:
        return jsonify(ok=False, error="name and email are required"), 400
    rec = {
        "id": int(now * 1000),
        "at": str(d.get("at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))[:40],
        "name": name,
        "email": email,
        "stance": stance,
        "notes": notes,
        "page": str(d.get("page", ""))[:200],
        "ip": ip,
        "ua": (request.headers.get("User-Agent") or "")[:200],
    }
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return jsonify(ok=True, id=rec["id"])


@app.get("/api/proposal-feedback")
def get_feedback():
    if not TOKEN or request.args.get("token") != TOKEN:
        abort(404)
    since = int(request.args.get("since", "0") or 0)
    items = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if int(r.get("id", 0)) > since:
                items.append(r)
    return jsonify(count=len(items), items=items[-50:], last=max([int(r["id"]) for r in items], default=since))


@app.delete("/api/proposal-feedback")
def clear_feedback():
    if not TOKEN or request.args.get("token") != TOKEN:
        abort(404)
    if LOG.exists():
        LOG.write_text("", encoding="utf-8")
    return jsonify(ok=True)


@app.route("/api/proposal-feedback", methods=["OPTIONS"])
def feedback_preflight():
    return ("", 204)


@app.after_request
def feedback_cors(resp):
    if request.path.startswith("/api/proposal-feedback"):
        origin = request.headers.get("Origin", "")
        host = origin.split("//")[-1].split("/")[0].lower()
        if host in ALLOWED_ORIGINS:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Vary"] = "Origin"
        if request.method == "OPTIONS":
            resp.headers["Access-Control-Max-Age"] = "600"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
