from __future__ import annotations

import html
import sqlite3
import urllib.parse
from datetime import date
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "crm.db"
HOST = "0.0.0.0"
PORT = 5000


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS youths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            gender TEXT NOT NULL,
            phone TEXT,
            zone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youth_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            amount REAL NOT NULL CHECK (amount >= 0),
            method TEXT NOT NULL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (youth_id) REFERENCES youths (id) ON DELETE CASCADE
        );
        """
    )
    db.commit()
    db.close()


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def esc(value: object) -> str:
    return html.escape(str(value) if value is not None else "")


def money(value: float) -> str:
    return f"UGX {value:,.2f}"


def page(title: str, body: str, flash: str = "") -> str:
    flash_html = f"<div class='message'>{esc(flash)}</div>" if flash else ""
    return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>{esc(title)}</title>
  <link rel='stylesheet' href='/static/styles.css'>
</head>
<body>
  <header class='site-header'>
    <h1>Heart of Worship Restoration Center</h1>
    <p>Youth Payment CRM</p>
    <nav>
      <a href='/'>Dashboard</a>
      <a href='/youths'>Youth Members</a>
      <a href='/payments'>Payments</a>
    </nav>
  </header>
  <main>
    {flash_html}
    {body}
  </main>
</body>
</html>"""


def dashboard_html() -> str:
    db = get_db()
    summary = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM youths) AS total_youths,
            (SELECT COALESCE(SUM(amount), 0) FROM payments) AS total_payments,
            (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE strftime('%Y-%m', payment_date) = strftime('%Y-%m', 'now')) AS monthly_payments
        """
    ).fetchone()

    recent = db.execute(
        """
        SELECT p.payment_date, p.payment_type, p.amount, p.method, y.full_name
        FROM payments p JOIN youths y ON y.id = p.youth_id
        ORDER BY p.payment_date DESC, p.id DESC LIMIT 10
        """
    ).fetchall()

    outstanding = db.execute(
        """
        SELECT y.full_name, y.zone, COALESCE(SUM(p.amount), 0) AS paid
        FROM youths y LEFT JOIN payments p ON p.youth_id = y.id
        GROUP BY y.id ORDER BY paid ASC, y.full_name ASC LIMIT 10
        """
    ).fetchall()
    db.close()

    recent_rows = "".join(
        f"<tr><td>{esc(r['payment_date'])}</td><td>{esc(r['full_name'])}</td><td>{esc(r['payment_type'])}</td><td>{money(r['amount'])}</td><td>{esc(r['method'])}</td></tr>"
        for r in recent
    ) or "<tr><td colspan='5'>No payments recorded yet.</td></tr>"

    outstanding_rows = "".join(
        f"<tr><td>{esc(r['full_name'])}</td><td>{esc(r['zone'] or '-')}</td><td>{money(r['paid'])}</td></tr>"
        for r in outstanding
    ) or "<tr><td colspan='3'>No youth members yet.</td></tr>"

    return f"""
<section class='cards'>
  <article><h2>Total Youths</h2><p>{summary['total_youths']}</p></article>
  <article><h2>Total Contributions</h2><p>{money(summary['total_payments'])}</p></article>
  <article><h2>This Month</h2><p>{money(summary['monthly_payments'])}</p></article>
</section>
<section class='grid-2'>
  <div><h3>Recent Payments</h3>
    <table><thead><tr><th>Date</th><th>Name</th><th>Type</th><th>Amount</th><th>Method</th></tr></thead><tbody>{recent_rows}</tbody></table>
  </div>
  <div><h3>Youths by Lowest Contributions</h3>
    <table><thead><tr><th>Name</th><th>Zone</th><th>Total Paid</th></tr></thead><tbody>{outstanding_rows}</tbody></table>
  </div>
</section>
"""


def youths_html() -> str:
    db = get_db()
    youths = db.execute(
        """
        SELECT y.id, y.full_name, y.gender, y.phone, y.zone, COALESCE(SUM(p.amount), 0) AS total_paid
        FROM youths y LEFT JOIN payments p ON p.youth_id = y.id
        GROUP BY y.id ORDER BY y.full_name
        """
    ).fetchall()
    db.close()

    rows = "".join(
        f"<tr><td>{esc(r['full_name'])}</td><td>{esc(r['gender'])}</td><td>{esc(r['phone'] or '-')}</td><td>{esc(r['zone'] or '-')}</td><td>{money(r['total_paid'])}</td></tr>"
        for r in youths
    ) or "<tr><td colspan='5'>No members yet.</td></tr>"

    return f"""
<section class='panel'>
  <h2>Add Youth Member</h2>
  <form method='post' action='/youths' class='form-grid'>
    <label>Full Name<input type='text' name='full_name' required></label>
    <label>Gender
      <select name='gender' required>
        <option value=''>Select</option><option value='Male'>Male</option><option value='Female'>Female</option>
      </select>
    </label>
    <label>Phone<input type='tel' name='phone' placeholder='+256...'></label>
    <label>Zone/Cell<input type='text' name='zone' placeholder='e.g. Zone A'></label>
    <button type='submit'>Save Member</button>
  </form>
</section>
<section class='panel'>
  <h2>Registered Youth Members</h2>
  <table><thead><tr><th>Name</th><th>Gender</th><th>Phone</th><th>Zone</th><th>Total Paid</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""


def payments_html() -> str:
    db = get_db()
    youths = db.execute("SELECT id, full_name FROM youths ORDER BY full_name").fetchall()
    payments = db.execute(
        """
        SELECT p.id, p.payment_date, p.payment_type, p.amount, p.method, p.notes, y.full_name
        FROM payments p JOIN youths y ON y.id = p.youth_id
        ORDER BY p.payment_date DESC, p.id DESC
        """
    ).fetchall()
    db.close()

    youth_options = "".join(f"<option value='{r['id']}'>{esc(r['full_name'])}</option>" for r in youths)
    rows = "".join(
        f"""<tr><td>{esc(r['payment_date'])}</td><td>{esc(r['full_name'])}</td><td>{esc(r['payment_type'])}</td>
        <td>{money(r['amount'])}</td><td>{esc(r['method'])}</td><td>{esc(r['notes'] or '-')}</td>
        <td><form method='post' action='/payments/{r['id']}/delete'><button class='danger' type='submit'>Delete</button></form></td></tr>"""
        for r in payments
    ) or "<tr><td colspan='7'>No payments yet.</td></tr>"

    return f"""
<section class='panel'>
  <h2>Record Payment</h2>
  <form method='post' action='/payments' class='form-grid'>
    <label>Youth Member
      <select name='youth_id' required><option value=''>Select member</option>{youth_options}</select>
    </label>
    <label>Payment Date<input type='date' name='payment_date' value='{date.today().isoformat()}' required></label>
    <label>Payment Type
      <select name='payment_type' required>
        <option value=''>Select type</option><option>Tithe</option><option>Offering</option><option>Special Seed</option><option>Project Contribution</option>
      </select>
    </label>
    <label>Amount (UGX)<input type='number' min='0' step='0.01' name='amount' required></label>
    <label>Payment Method
      <select name='method' required>
        <option value=''>Select method</option><option>Cash</option><option>Mobile Money</option><option>Bank Transfer</option>
      </select>
    </label>
    <label>Notes<input type='text' name='notes' placeholder='Optional notes'></label>
    <button type='submit'>Save Payment</button>
  </form>
</section>
<section class='panel'>
  <h2>Payment History</h2>
  <table><thead><tr><th>Date</th><th>Youth</th><th>Type</th><th>Amount</th><th>Method</th><th>Notes</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""


class Handler(BaseHTTPRequestHandler):
    def respond_html(self, html_content: str) -> None:
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def parse_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        parsed = urllib.parse.parse_qs(payload)
        return {k: v[0] for k, v in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/static/styles.css"):
            css = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(css)))
            self.end_headers()
            self.wfile.write(css)
            return

        parsed = urllib.parse.urlparse(self.path)
        flash = urllib.parse.parse_qs(parsed.query).get("flash", [""])[0]

        if parsed.path == "/":
            self.respond_html(page("Dashboard", dashboard_html(), flash))
        elif parsed.path == "/youths":
            self.respond_html(page("Youth Members", youths_html(), flash))
        elif parsed.path == "/payments":
            self.respond_html(page("Payments", payments_html(), flash))
        else:
            self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/youths":
            form = self.parse_form()
            full_name = form.get("full_name", "").strip()
            gender = form.get("gender", "").strip()
            phone = form.get("phone", "").strip()
            zone = form.get("zone", "").strip()

            if not full_name or not gender:
                self.redirect("/youths?flash=Full+name+and+gender+are+required")
                return

            db = get_db()
            db.execute("INSERT INTO youths (full_name, gender, phone, zone) VALUES (?, ?, ?, ?)", (full_name, gender, phone, zone))
            db.commit()
            db.close()
            self.redirect("/youths?flash=Youth+member+added+successfully")
            return

        if self.path == "/payments":
            form = self.parse_form()
            required = [form.get("youth_id", ""), form.get("payment_date", ""), form.get("payment_type", ""), form.get("amount", ""), form.get("method", "")]
            if not all(required):
                self.redirect("/payments?flash=All+required+payment+fields+must+be+filled")
                return

            try:
                amount = float(form.get("amount", "0"))
                if amount < 0:
                    raise ValueError
            except ValueError:
                self.redirect("/payments?flash=Please+provide+a+valid+non-negative+amount")
                return

            db = get_db()
            db.execute(
                "INSERT INTO payments (youth_id, payment_date, payment_type, amount, method, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (form["youth_id"], form["payment_date"], form["payment_type"], amount, form["method"], form.get("notes", "")),
            )
            db.commit()
            db.close()
            self.redirect("/payments?flash=Payment+recorded+successfully")
            return

        if self.path.startswith("/payments/") and self.path.endswith("/delete"):
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "payments" and parts[2] == "delete":
                payment_id = parts[1]
                db = get_db()
                db.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
                db.commit()
                db.close()
                self.redirect("/payments?flash=Payment+removed")
                return

        self.send_error(404, "Not found")


def run() -> None:
    init_db()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
