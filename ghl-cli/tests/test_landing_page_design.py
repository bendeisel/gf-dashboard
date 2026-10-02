import tempfile
import unittest
from pathlib import Path

from cli_anything.gohighlevel.utils.funnel_page_builder import build_page_data
from cli_anything.gohighlevel.utils.landing_page_design import (
    TEMPLATE_INFO,
    apply_design_system,
    lint_spec,
    render_preview,
    template_spec,
)


class LandingPageDesignTests(unittest.TestCase):
    def test_all_templates_build_valid_ghl_page_graphs(self):
        for name in TEMPLATE_INFO:
            with self.subTest(template=name):
                spec = template_spec(name)
                data = build_page_data(spec, page_id="page", funnel_id="funnel", location_id="location")
                self.assertGreaterEqual(len(data["sections"]), 3)
                self.assertIn("--headlinefont:'Inter'", data["pageStyles"])
                self.assertIn("--contentfont:'Roboto'", data["pageStyles"])
                self.assertIn("font-weight:700!important", data["pageStyles"])
                self.assertIn("lp-button", data["pageStyles"])
                self.assertIn("@media(max-width:991px)", data["pageStyles"])
                self.assertIn("@media(max-width:767px)", data["sections"][0]["general"]["sectionStyles"])
                button_nodes = [
                    node for section in data["sections"] for node in section["elements"]
                    if node.get("meta") == "button"
                ]
                self.assertTrue(all(
                    node["extra"]["action"]["value"] != "visit-website"
                    for node in button_nodes
                ))

    def test_theme_defaults_preserve_explicit_choices(self):
        source = {"designSystem": {"theme": "modern"}, "headlineFont": "Poppins",
                  "sections": [{"rows": [{"columns": [{"elements": [
                      {"type": "heading", "text": "One clear promise"},
                      {"type": "button", "text": "Get the plan"},
                  ]}]}]}]}
        result = apply_design_system(source)
        self.assertEqual(result["headlineFont"], "Poppins")
        self.assertEqual(result["contentFont"], "Roboto")
        self.assertEqual(result["sections"][0]["mobilePaddingLeft"], 20)
        self.assertIn("lp-button", result["sections"][0]["rows"][0]["columns"][0]["elements"][1]["customClass"])
        self.assertNotIn("headlineFont", source.get("sections", [{}])[0])

    def test_single_column_rows_center_their_contents(self):
        source = {"designSystem": {"theme": "modern"}, "sections": [{"rows": [{
            "columns": [{"elements": [
                {"type": "image", "url": "https://example.test/logo.png", "alt": "Logo", "align": "left"},
                {"type": "heading", "text": "Centered promise", "align": "left"},
                {"type": "paragraph", "text": "Centered explanation", "align": "left"},
                {"type": "button", "text": "Continue", "align": "left"},
                {"type": "calendar", "calendarId": "calendar-id"},
            ]}],
        }]}]}
        result = apply_design_system(source)
        row = result["sections"][0]["rows"][0]
        column = row["columns"][0]
        self.assertIn("lp-single-column", row["customClass"])
        self.assertEqual(column["alignItems"], "center")
        self.assertTrue(all(
            element.get("align") == "center"
            for element in column["elements"]
            if element["type"] != "calendar"
        ))
        self.assertNotIn("align", column["elements"][-1])
        self.assertIn(".lp-single-column", result["customCss"])

    def test_logo_and_centered_images_receive_explicit_centering_and_rhythm(self):
        source = {"designSystem": {"theme": "modern"}, "sections": [{"rows": [{
            "columns": [{"elements": [
                {"type": "image", "url": "https://example.test/brand-logo.png", "alt": "Brand logo"},
                {"type": "subHeading", "text": "A properly separated heading"},
            ]}],
        }]}]}
        result = apply_design_system(source)
        logo = result["sections"][0]["rows"][0]["columns"][0]["elements"][0]
        self.assertEqual(logo["role"], "logo")
        self.assertEqual(logo["align"], "center")
        self.assertGreaterEqual(logo["marginBottom"], 24)
        self.assertIn("lp-logo", logo["customClass"])
        self.assertIn(".lp-logo img", result["customCss"])

    def test_design_css_contains_native_survey_footer_geometry_guards(self):
        result = apply_design_system({
            "designSystem": {"theme": "modern"},
            "sections": [{"rows": [{"columns": [{"customClass": ["lp-form-card"], "elements": [
                {"type": "survey", "surveyId": "survey-id"},
            ]}]}]}],
        })
        css = result["customCss"]
        self.assertIn(".lp-form-card .ghl-footer{height:76px!important", css)
        self.assertIn(".lp-form-card .ghl-btn-placeholder{display:none!important}", css)
        self.assertIn(".lp-form-card .ghl-footer-back,.hl_page-preview--content .lp-form-card .ghl-footer-next", css)

    def test_tablet_stacking_is_opt_in_per_row(self):
        source = {"designSystem": {"theme": "modern"}, "sections": [{"rows": [{
            "stackOnTablet": True,
            "columns": [{"elements": []}, {"elements": []}],
        }]}]}
        result = apply_design_system(source)
        row = result["sections"][0]["rows"][0]
        self.assertIn("lp-stack-tablet", row["customClass"])
        data = build_page_data(result, page_id="p", funnel_id="f", location_id="l")
        self.assertIn("@media(max-width:991px)", data["pageStyles"])

    def test_lint_allows_separate_mobile_and_desktop_primary_headings(self):
        spec = template_spec("optin")
        spec["sections"][0]["hideDesktop"] = True
        spec["sections"][1]["hideMobile"] = True
        spec["sections"][1]["rows"][0]["columns"][0]["elements"].insert(
            0, {"type": "heading", "text": "Desktop-only promise", "hideMobile": True}
        )
        first_heading = next(
            el for row in spec["sections"][0]["rows"] for col in row["columns"]
            for el in col["elements"] if el.get("type") == "heading"
        )
        first_heading["hideDesktop"] = True
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertNotIn("type.h1-count", codes)

    def test_pricing_template_passes_design_lint(self):
        report = lint_spec(template_spec("pricing"))
        self.assertTrue(report["passed"], report["issues"])
        self.assertGreaterEqual(report["score"], 90)

    def test_integration_templates_fail_until_real_ids_are_inserted(self):
        for name, code in (("optin", "integration.placeholder"),
                           ("calendar", "integration.placeholder"),
                           ("intake", "integration.placeholder"),
                           ("roadmap", "integration.placeholder"),
                           ("application", "integration.placeholder"),
                           ("vsl-application", "integration.placeholder")):
            with self.subTest(template=name):
                report = lint_spec(template_spec(name))
                self.assertIn(code, {issue["code"] for issue in report["issues"]})
                self.assertFalse(report["passed"])

    def test_lint_catches_hierarchy_and_accessibility_problems(self):
        bad = {"designSystem": True, "sections": [{"paddingTop": 10, "rows": [{"columns": [
            {"width": 40, "elements": [{"type": "heading", "text": "First"},
                                         {"type": "heading", "text": "Second"},
                                         {"type": "image", "url": "x"},
                                         {"type": "button", "text": "Submit", "background": "#FFFFFF", "color": "#EEEEEE", "paddingTop": 1, "paddingBottom": 1}]},
            {"width": 40, "elements": []},
        ]}]}]}
        codes = {issue["code"] for issue in lint_spec(bad)["issues"]}
        self.assertTrue({"grid.width", "type.h1-count", "cta.generic", "cta.target-size", "media.alt", "color.contrast"} <= codes)

    def test_template_strategy_metadata_is_present(self):
        for name in TEMPLATE_INFO:
            with self.subTest(template=name):
                framework = template_spec(name).get("framework", {})
                self.assertTrue({"traffic", "awareness", "friction", "copyFramework"} <= set(framework))

    def test_new_archetypes_encode_required_argument_stages(self):
        for name in ("sales-letter", "membership", "vsl-application"):
            with self.subTest(template=name):
                codes = {issue["code"] for issue in lint_spec(template_spec(name))["issues"]}
                self.assertNotIn("structure.required-stage", codes)

    def test_lint_catches_reference_page_anti_patterns(self):
        spec = template_spec("membership")
        hero_elements = spec["sections"][0]["rows"][0]["columns"][0]["elements"]
        hero_elements[1]["text"] = "This is a deliberately overlong primary headline that cannot possibly scan cleanly within three lines on a typical mobile device"
        hero_elements.append({"type": "subHeading", "text": "How It Works"})
        spec["sections"][0]["rows"][0]["columns"][1]["elements"][0]["autoplay"] = True
        spec["sections"][1]["rows"][0]["columns"][0]["elements"].extend(
            {"type": "image", "url": f"https://example.com/{i}.jpg", "alt": f"Result {i}"}
            for i in range(21)
        )
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertTrue({"type.long-h1", "copy.generic-heading", "media.autoplay", "media.image-budget"} <= codes)

    def test_lint_blocks_collapsed_media_spacing_and_redundant_calendar_jump(self):
        spec = {
            "designSystem": False,
            "sections": [
                {"rows": [{"columns": [{"elements": [
                    {"type": "heading", "text": "Choose your call"},
                    {"type": "image", "url": "https://example.test/logo.png", "alt": "Brand logo", "align": "left", "marginBottom": "0px"},
                    {"type": "customCode", "role": "video", "html": '<div class="video-placeholder">Video</div>', "marginBottom": 0},
                    {"type": "button", "text": "Choose my time", "action": "scroll-to-element", "scrollToElement": "booking-calendar"},
                ]}]}]},
                {"id": "booking-calendar", "rows": [{"columns": [{"elements": [
                    {"type": "calendar", "calendarId": "calendar-id"},
                ]}]}]},
            ],
        }
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertIn("spacing.element-collapse", codes)
        self.assertIn("media.logo-center", codes)
        self.assertIn("cta.calendar-redundant", codes)

    def test_calendar_template_uses_the_calendar_as_its_primary_action(self):
        spec = template_spec("calendar")
        buttons = [
            el for section in spec["sections"] for row in section.get("rows", [])
            for column in row.get("columns", []) for el in column.get("elements", [])
            if el.get("type") == "button"
        ]
        self.assertEqual(buttons, [])
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertNotIn("hero.cta", codes)
        self.assertNotIn("cta.calendar-redundant", codes)

    def test_timer_requires_honest_urgency_and_expiry_behavior(self):
        spec = template_spec("pricing")
        spec["sections"][0]["rows"][0]["columns"][0]["elements"].append(
            {"type": "timer", "minutes": 30}
        )
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertTrue({"urgency.unexplained", "urgency.evergreen", "urgency.expiry"} <= codes)

    def test_preview_is_responsive_and_self_contained_html(self):
        with tempfile.TemporaryDirectory() as directory:
            path = render_preview(template_spec("vsl"), Path(directory) / "vsl.html")
            text = path.read_text()
        self.assertIn("<meta name=\"viewport\"", text)
        self.assertIn("@media(max-width:767px)", text)
        self.assertIn("The PR System", text)

    def test_popup_lint_enforces_single_purpose_dialogs(self):
        spec = template_spec("intake")
        spec["popup"] = {"width": 900, "exitIntent": True, "rows": [
            {"columns": [{"elements": [{"type": "button", "text": "One"}]}]},
            {"columns": [{"elements": [{"type": "button", "text": "Two"}]}]},
        ]}
        codes = {issue["code"] for issue in lint_spec(spec)["issues"]}
        self.assertTrue({"popup.complex", "popup.width", "popup.label", "popup.actions", "popup.intake"} <= codes)


if __name__ == "__main__":
    unittest.main()
