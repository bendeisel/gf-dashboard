import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cli_anything.gohighlevel.gohighlevel_cli import _write_page_backup
from cli_anything.gohighlevel.utils.funnel_page_builder import build_page_data, count_summary


class FunnelPageBuilderTests(unittest.TestCase):
    def setUp(self):
        self.spec = {
            "primaryColor": "#123456",
            "sections": [{"name": "Hero", "rows": [{"columns": [
                {"width": 60, "elements": [
                    {"type": "heading", "text": "A visible headline", "fontSize": 48},
                    {"type": "paragraph", "text": "Supporting copy"},
                    {"type": "divider"},
                ]},
                {"width": 40, "elements": [
                    {"type": "image", "url": "https://example.test/image.png", "alt": "Example"}
                ]},
            ]}]}],
        }

    def test_builds_flat_linked_hierarchy_and_css(self):
        data = build_page_data(self.spec, page_id="page", funnel_id="funnel", location_id="location")
        section = data["sections"][0]
        nodes = {node["id"]: node for node in section["elements"]}
        row = nodes[section["metaData"]["child"][0]]

        self.assertEqual(row["meta"], "row")
        self.assertEqual(len(row["child"]), 2)
        self.assertEqual([nodes[c]["styles"]["width"]["value"] for c in row["child"]], ["60", "40"])
        self.assertTrue(all(nodes[c]["extra"]["justifyContentColumnLayout"]["value"] == "flex-start" for c in row["child"]))
        self.assertTrue(all(child in nodes for col in row["child"] for child in nodes[col]["child"]))
        self.assertIn("A visible headline", next(n for n in nodes.values() if n["meta"] == "heading")["extra"]["text"]["value"])
        self.assertIn(section["id"], section["general"]["sectionStyles"])
        self.assertIn("justify-content:flex-start", section["general"]["sectionStyles"])
        self.assertIn("--primary:#123456", data["pageStyles"])
        self.assertEqual(count_summary(data), "1 section(s), 1 row(s), 4 element(s)")

    def test_heading_html_is_wrapped_without_being_escaped(self):
        self.spec["sections"][0]["rows"][0]["columns"][0]["elements"] = [{
            "type": "heading",
            "html": "THE SYSTEM <span style=\"color: #ED0D51ff\">BOOKS CALLS</span>",
        }]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        node = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "heading")
        self.assertEqual(
            node["extra"]["text"]["value"],
            '<h1>THE SYSTEM <span style="color: #ED0D51ff">BOOKS CALLS</span></h1>',
        )
        self.assertEqual(node["styles"]["fontWeight"]["value"], "700")

    def test_default_font_pair_is_inter_and_roboto(self):
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        self.assertIn("--headlinefont:'Inter'", data["pageStyles"])
        self.assertIn("--contentfont:'Roboto'", data["pageStyles"])
        self.assertEqual(data["general"]["general"]["fontsToLoad"], ["Inter", "Roboto"])

    def test_page_backup_is_written_before_replacement(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "backups" / "page-before.json"
            path = _write_page_backup("page", {"sections": [{"id": "old"}]}, output)
            self.assertEqual(path, output)
            self.assertIn('"id": "old"', output.read_text(encoding="utf-8"))

    def test_form_requires_an_id(self):
        self.spec["sections"][0]["rows"][0]["columns"][0]["elements"] = [{"type": "form"}]
        with self.assertRaisesRegex(ValueError, "formId"):
            build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")

    def test_major_native_element_families(self):
        elements = [
            {"type": "subHeading", "text": "Sub"},
            {"type": "bulletList", "items": ["One", "Two"]},
            {"type": "button", "text": "Continue", "url": "https://example.test"},
            {"type": "video", "url": "https://vimeo.com/123"},
            {"type": "countdown", "endDate": "2026-08-15", "endTime": "23:59"},
            {"type": "timer", "minutes": 10},
            {"type": "faq", "items": [{"question": "Q", "answer": "A"}]},
            {"type": "logoShowcase", "logos": [{"image": "https://example.test/logo.png"}]},
            {"type": "customCode", "html": "<p>Safe HTML</p>"},
            {"type": "form", "formId": "form-id"},
            {"type": "survey", "surveyId": "survey-id"},
            {"type": "calendar", "calendarId": "calendar-id"},
            {"type": "oneStepOrder"},
            {"type": "twoStepOrder"},
            {"type": "orderConfirmation"},
        ]
        self.spec["sections"][0]["rows"][0]["columns"] = [{"elements": elements}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        metas = {n["meta"] for n in data["sections"][0]["elements"] if n.get("type") == "element"}
        self.assertEqual(metas, {"sub-heading", "bulletList", "button", "video", "countdown", "minute-timer",
            "faq", "logo-showcase", "custom-code", "form", "survey", "calendar",
            "one-step-order", "two-setp-order", "order-confirmation"})
        bullet = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "bulletList")
        self.assertEqual(bullet["styles"]["fontFamily"]["value"], "var(--contentfont)")
        self.assertIn("font-family:var(--contentfont)", data["sections"][0]["general"]["sectionStyles"])
        button = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "button")
        self.assertEqual(button["extra"]["typography"]["value"], "var(--contentfont)")

    def test_button_accepts_ghl_color_aliases(self):
        self.spec["sections"][0]["rows"][0]["columns"] = [{"elements": [{
            "type": "button", "text": "Choose a time",
            "backgroundColor": "#ED0D51", "textColor": "#FFFFFF",
        }]}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        button = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "button")
        self.assertEqual(button["styles"]["backgroundColor"]["value"], "#ED0D51")
        self.assertEqual(button["styles"]["color"]["value"], "#FFFFFF")

    def test_centered_images_emit_runtime_centering_and_safe_spacing(self):
        self.spec["sections"][0]["rows"][0]["columns"] = [{"elements": [{
            "type": "image",
            "url": "https://example.test/logo.png",
            "alt": "Example logo",
            "width": "152px",
            "align": "center",
        }]}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        section = data["sections"][0]
        image = next(n for n in section["elements"] if n.get("meta") == "image")
        self.assertEqual(image["wrapper"]["textAlign"]["value"], "center")
        self.assertEqual(image["wrapper"]["marginBottom"]["value"], 20)
        self.assertIn(f".{image['id']} img{{display:block;margin-left:auto;margin-right:auto}}", section["general"]["sectionStyles"])

    def test_fixed_countdown_uses_native_ghl_schema(self):
        self.spec["sections"][0]["rows"][0]["columns"] = [{"elements": [{
            "type": "countdown", "endDate": "2026-08-15", "endTime": "23:59",
            "timezone": "America/New_York", "language": "English",
            "expireAction": "url", "redirectUrl": "https://otterpr.com",
        }]}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        node = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "countdown")
        self.assertEqual(node["tagName"], "c-countdown")
        self.assertEqual(node["extra"]["endDate"]["value"], "2026-08-15")
        self.assertEqual(node["extra"]["endTime"]["value"], "23:59")
        self.assertEqual(node["extra"]["timezone"]["value"], "America/New_York")
        self.assertEqual(node["extra"]["timerType"], {"value": "countdown", "disabled": True})

    def test_fixed_countdown_requires_end_date(self):
        self.spec["sections"][0]["rows"][0]["columns"] = [
            {"elements": [{"type": "countdown"}]}]
        with self.assertRaisesRegex(ValueError, "endDate"):
            build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")

    def test_native_escape_hatch_rekeys_node(self):
        original = {"id": "old", "type": "element", "child": [], "meta": "future-widget",
                    "tagName": "c-future-widget", "extra": {"nodeId": "cold"}}
        self.spec["sections"][0]["rows"][0]["columns"] = [
            {"elements": [{"type": "native", "id": "future-new", "node": original}]}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        node = next(n for n in data["sections"][0]["elements"] if n.get("type") == "element")
        self.assertEqual(node["id"], "future-new")
        self.assertEqual(node["extra"]["nodeId"], "cfuture-new")
        self.assertEqual(original["id"], "old")

    def test_advanced_native_overrides_are_deep_merged(self):
        self.spec["sections"][0]["rows"][0]["columns"] = [{"elements": [{
            "type": "button", "text": "Animated", "styles": {"backgroundColor": {"value": "#ff0000"}},
            "extra": {"customClass": {"value": ["animate-pulse"]}},
            "mobileStyles": {"width": {"value": 100, "unit": "%"}}
        }]}]
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        node = next(n for n in data["sections"][0]["elements"] if n.get("meta") == "button")
        self.assertEqual(node["styles"]["backgroundColor"]["value"], "#ff0000")
        self.assertEqual(node["extra"]["customClass"]["value"], ["animate-pulse"])
        self.assertEqual(node["mobileStyles"]["width"]["value"], 100)

    def test_popup_background_and_page_features(self):
        self.spec["headlineFont"] = "Poppins"
        self.spec["contentFont"] = "Open Sans"
        self.spec["customCss"] = ".custom-test{display:block}"
        self.spec["trackingCode"] = {"head": "<!-- test -->"}
        self.spec["sections"][0]["backgroundImage"] = "https://example.test/bg.jpg"
        self.spec["popup"] = {"title": "Lead Popup", "rows": [{"columns": [
            {"elements": [{"type": "heading", "text": "Popup headline"}]}
        ]}]}
        data = build_page_data(self.spec, page_id="p", funnel_id="f", location_id="l")
        self.assertEqual(data["popups"][0]["meta"], "hl_main_popup")
        self.assertIn("background-image", data["sections"][0]["general"]["sectionStyles"])
        self.assertIn(".custom-test", data["pageStyles"])
        self.assertEqual(data["trackingCode"]["head"], "<!-- test -->")
        self.assertIn("Poppins", data["pageStyles"])


if __name__ == "__main__":
    unittest.main()
