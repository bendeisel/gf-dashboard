"""Offline tests: scoped generation, evidence preservation and HTTP isolation."""
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen, Request
from urllib.parse import parse_qs, urlsplit
from html.parser import HTMLParser

import pytest
from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils.checkout_probe import checkout_assets, probe_server


def generate(path, **overrides):
    args = dict(form_id="form-1", annual_row_id="annual", monthly_row_id="monthly",
                checkout_url="https://example.test/checkout?email=old&keep=1",
                output_dir=path, coupon_code="TEST49", email="test@example.com")
    return checkout_assets(**(args | overrides))


def test_scoped_assets_and_encoded_prefills(tmp_path):
    files = generate(tmp_path / "new")
    css = Path(files["hide-annual.css"]).read_text()
    assert '[id="form-1"] .product-description[id="annual"]' in css
    assert "monthly" not in css
    script = Path(files["select-monthly.html"]).read_text()
    assert '[id="monthly"] input[type="radio"]' in script
    assert "!monthly.checked" in script and "++checks >= 60" in script
    assert "}, 250)" in script

    class Parser(HTMLParser):
        src = None
        def handle_starttag(self, tag, attrs):
            if tag == "iframe":
                self.src = dict(attrs)["src"]
    parser = Parser()
    parser.feed(Path(files["embed.html"]).read_text())
    assert parse_qs(urlsplit(parser.src).query) == {
        "keep": ["1"], "email": ["test@example.com"], "coupon_code": ["TEST49"]}


@pytest.mark.parametrize("overrides", [
    {"form_id": 'x" onclick="bad'}, {"annual_row_id": "monthly"},
    {"checkout_url": "javascript:alert(1)"},
    {"checkout_url": "https://user:secret@example.test/"},
])
def test_invalid_inputs_do_not_create_output(tmp_path, overrides):
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        generate(output, **overrides)
    assert not output.exists()


def test_existing_evidence_is_never_overwritten(tmp_path):
    files = generate(tmp_path / "evidence")
    original = {name: Path(path).read_bytes() for name, path in files.items()}
    with pytest.raises(FileExistsError):
        generate(tmp_path / "evidence", coupon_code="CHANGED")
    assert original == {name: Path(path).read_bytes() for name, path in files.items()}


def test_server_only_serves_explicit_document_and_stops(tmp_path):
    page = tmp_path / "probe.html"
    page.write_text("<iframe></iframe>")
    (tmp_path / "backup.json").write_text("private backup")
    with probe_server(page, 0) as server:
        assert server.server_address[0] == "127.0.0.1"
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/embed.html") as response:
                assert response.read() == page.read_bytes()
                assert response.headers["Cache-Control"] == "no-store"
            for path in ("/", "/backup.json", "/../backup.json", "/embed.html?secret=1"):
                with pytest.raises(HTTPError) as error:
                    urlopen(base + path)
                assert error.value.code == 404
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + "/embed.html", data=b"test", method="POST"))
            assert error.value.code == 501
        finally:
            server.shutdown()
            worker.join(timeout=2)
            assert not worker.is_alive()


def test_cli_local_generation_needs_no_api(monkeypatch, tmp_path):
    from cli_anything.gohighlevel.utils import ghl_client
    monkeypatch.setattr(ghl_client, "get", lambda *a, **k: pytest.fail("API called"))
    result = CliRunner().invoke(cli, ["--json", "funnels", "checkout-assets",
        "--form-id", "form", "--annual-row-id", "annual", "--monthly-row-id", "monthly",
        "--checkout-url", "https://example.test", "--output-dir", str(tmp_path / "new")])
    assert result.exit_code == 0, result.output
    assert set(json.loads(result.output)) == {"hide-annual.css", "select-monthly.html", "embed.html"}
