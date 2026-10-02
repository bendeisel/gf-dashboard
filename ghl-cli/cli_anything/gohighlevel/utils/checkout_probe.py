"""Local checkout assets and a single-file, loopback-only iframe probe server."""
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def checkout_assets(form_id, annual_row_id, monthly_row_id, checkout_url,
                    output_dir, coupon_code=None, email=None):
    """Generate files only; never read credentials or change a remote page."""
    for value in (form_id, annual_row_id, monthly_row_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("DOM IDs must contain only letters, digits, _ and -")
    if annual_row_id == monthly_row_id:
        raise ValueError("Annual and Monthly row IDs must differ")
    url = urlsplit(checkout_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("checkout URL must be HTTPS without embedded credentials")
    query = parse_qsl(url.query, keep_blank_values=True)
    for name, value in (("coupon_code", coupon_code), ("email", email)):
        if value is not None:
            query = [(k, v) for k, v in query if k != name] + [(name, value)]
    src = urlunsplit(url._replace(query=urlencode(query)))
    css = f'''/* Hide only the inspected Annual row on this checkout. */
[id="{form_id}"] .product-description[id="{annual_row_id}"] {{
  display: none !important;
}}
'''
    footer = f'''<script>
(function () {{
  var checks = 0;
  var timer = setInterval(function () {{
    var form = document.getElementById("{form_id}");
    var monthly = form && form.querySelector('[id="{monthly_row_id}"] input[type="radio"]');
    if (monthly && !monthly.checked) monthly.click();
    if (++checks >= 60) {{
      clearInterval(timer);
      if (!monthly) console.error("GHL checkout: Monthly option did not render within 15 seconds.");
    }}
  }}, 250);
}})();
</script>
'''
    embed = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Checkout iframe probe</title>
<style>html,body{{margin:0}}iframe{{display:block;width:100%;height:1600px;border:0}}</style>
</head><body><iframe title="Checkout probe" src="{escape(src, quote=True)}"></iframe></body></html>
'''
    # A new directory prevents accidental replacement of evidence or a rollback point.
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=False)
    files = {"hide-annual.css": css, "select-monthly.html": footer, "embed.html": embed}
    for name, content in files.items():
        with (directory / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    return {name: str((directory / name).resolve()) for name in files}


def probe_server(html_file, port=8765):
    """Serve a snapshot of one explicit HTML file, never its evidence directory."""
    path = Path(html_file).expanduser()
    if path.suffix.lower() not in (".html", ".htm"):
        raise ValueError("probe must be an HTML file")
    content = path.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/embed.html":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            # Do not log query strings, email addresses, or other request data.
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
