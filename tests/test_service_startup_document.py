"""T-831: the service serves the EFFECTIVE startup document.

The service / SAIWORK iframe used to bypass the startup optimization
completely: ``/`` and ``/index.html`` mapped to the raw 34-locale template.
Now both render per the CURRENT backend config locale, in memory, through the
same GUI-neutral renderer the desktop uses -- and never touch a generated
``index.lite.html`` file.

Transport notes: the service binds loopback only with a per-launch token; the
startup page is deliberately UNAUTHENTICATED like the health endpoint because
the SAIWORK iframe cannot attach the token to its initial document GET --
the page itself is static UI and every data surface behind it (RPC/SSE)
remains token-guarded.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from saipenview.service import SaipenViewService

STATIC = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static"


@pytest.fixture()
def service(tmp_config_path):
    svc = SaipenViewService(
        host="127.0.0.1", port=0, token="test-token-123", auto_scan=False
    )
    svc.start()
    yield svc
    svc.stop()


def _get(svc, path):
    """GET a static path; returns (status, headers, body bytes)."""
    req = urllib.request.Request(f"http://127.0.0.1:{svc.bound_port}{path}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _set_locale(svc, value):
    """Change the live backend config locale through the allowlisted RPC."""
    headers = {"Content-Type": "application/json", "X-Saipenview-Token": "test-token-123"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{svc.bound_port}/api/rpc",
        data=json.dumps({"method": "save_view_config", "args": [{"locale": value}]}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body.get("ok") is True, body


def _locale_tags(body: bytes) -> list[str]:
    html = body.decode("utf-8")
    return re.findall(r'src="(locale-[^"]+\.js)"', html)


class TestStartupDocument:
    def test_root_locale_en_serves_one_en_tag(self, service):
        status, headers, body = _get(service, "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        tags = _locale_tags(body)
        assert tags == ["locale-en.js"]
        # Content-Length matches the exact rendered bytes.
        assert int(headers["Content-Length"]) == len(body)

    def test_root_locale_ru_serves_en_plus_ru(self, service):
        _set_locale(service, "ru")
        status, _h, body = _get(service, "/")
        assert status == 200
        assert _locale_tags(body) == ["locale-en.js", "locale-ru.js"]

    def test_index_html_is_the_same_effective_document(self, service):
        """No raw-template bypass: /index.html renders exactly like /."""
        _set_locale(service, "ru")
        for path in ("/", "/index.html"):
            status, _h, body = _get(service, path)
            assert status == 200
            assert _locale_tags(body) == ["locale-en.js", "locale-ru.js"]
        _a, _h1, raw = _get(service, "/")
        _b, _h2, raw_index = _get(service, "/index.html")
        assert raw == raw_index

    def test_config_locale_change_is_served_on_next_get(self, service):
        status, _h, body = _get(service, "/")
        assert _locale_tags(body) == ["locale-en.js"]
        _set_locale(service, "et")
        status, _h, body = _get(service, "/")
        assert _locale_tags(body) == ["locale-en.js", "locale-et.js"]
        _set_locale(service, "en")
        status, _h, body = _get(service, "/")
        assert _locale_tags(body) == ["locale-en.js"]

    def test_unknown_locale_serves_en_only(self, service):
        _set_locale(service, "klingon")
        status, _h, body = _get(service, "/")
        assert status == 200
        assert _locale_tags(body) == ["locale-en.js"]

    def test_serving_startup_html_never_creates_index_lite(self, service):
        generated = STATIC / "index.lite.html"
        existed_before = generated.exists()
        before = generated.read_bytes() if existed_before else None
        try:
            _get(service, "/")
            _get(service, "/index.html")
            if existed_before:
                # A pre-existing file must not have been touched either.
                assert generated.read_bytes() == before
            else:
                assert not generated.exists()
        finally:
            # Restore the pre-existing state exactly (tests must not leave a
            # generated file in the repository's static dir).
            if not existed_before and generated.exists():
                generated.unlink()

    def test_startup_document_has_no_filesystem_side_effects(
        self, service, tmp_path, monkeypatch
    ):
        """ Belt-and-braces: the serving path renders IN MEMORY -- even with
        the renderer's module dir redirected to a temp dir, serving / leaves
        it with only the template (no generated page, no temp files)."""
        import saipenview.ui.index_page as index_page

        d = tmp_path / "static"
        d.mkdir()
        (d / "index.html").write_bytes((STATIC / "index.html").read_bytes())
        monkeypatch.setattr(index_page, "_STATIC_DIR", d)
        _get(service, "/")
        _get(service, "/index.html")
        assert sorted(p.name for p in d.rglob("*")) == ["index.html"]

    def test_renderer_failure_is_a_controlled_5xx(
        self, service, tmp_path, monkeypatch
    ):
        """A broken template must produce a real error status, never a fake
        200 page; the diagnostic stays on the server side."""
        import saipenview.ui.index_page as index_page

        d = tmp_path / "static"
        d.mkdir()
        (d / "index.html").write_text("<html>no locale block</html>", encoding="utf-8")
        monkeypatch.setattr(index_page, "_STATIC_DIR", d)
        status, headers, body = _get(service, "/")
        assert 500 <= status < 600
        assert b"locale-en.js" not in body  # no fabricated page

    def test_app_js_remains_directly_servable(self, service):
        status, headers, body = _get(service, "/app.js")
        assert status == 200
        assert headers["Content-Type"] == "application/javascript"
        assert b"loadLocaleTable" in body

    def test_style_css_remains_directly_servable(self, service):
        status, headers, _body = _get(service, "/style.css")
        assert status == 200
        assert headers["Content-Type"] == "text/css"

    def test_locale_ru_js_remains_directly_servable(self, service):
        status, headers, body = _get(service, "/locale-ru.js")
        assert status == 200
        assert headers["Content-Type"] == "application/javascript"
        assert body[:2] == b"//"

    def test_traversal_rejection_remains_green(self, service):
        status, _h, _b = _get(service, "/..%2f..%2fpyproject.toml".replace("%2f", "/"))
        assert status == 404
        status, _h, _b = _get(service, "/../../pyproject.toml")
        assert status == 404

    def test_dotfile_rejection_remains_green(self, service):
        status, _h, _b = _get(service, "/.gitignore")
        assert status == 404


class TestServingPathIsolation:
    def test_service_module_never_imports_window_or_webview(self):
        """The service serving path must stay GUI-free: importing the service
        module must not pull in the window stack, and (checked transitively in
        the renderer tests) the shared renderer imports neither."""
        import subprocess
        import sys

        code = (
            "import sys; import saipenview.service; "
            "print(','.join(sorted(m for m in sys.modules if m in {"
            "'webview', 'saipenview.ui.window'})))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "", (
            f"service pulled in GUI modules: {proc.stdout}"
        )
