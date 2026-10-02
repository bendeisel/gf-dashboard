"""Tests for first-name merge fields and their fallbacks."""
from __future__ import annotations

import unittest

from cli_anything.gohighlevel.utils import merge_fields as mf


class EnsureFallbackTests(unittest.TestCase):
    def test_bare_token_gets_a_fallback(self):
        self.assertEqual(
            mf.ensure_fallbacks("Hi {{contact.first_name}},"),
            'Hi {{default contact.first_name "there"}},',
        )

    def test_custom_fallback(self):
        self.assertEqual(
            mf.ensure_fallbacks("Hey {{contact.first_name}}", "friend"),
            'Hey {{default contact.first_name "friend"}}',
        )

    def test_whitespace_inside_braces_is_tolerated(self):
        self.assertEqual(
            mf.ensure_fallbacks("{{  contact.first_name  }}"),
            '{{default contact.first_name "there"}}',
        )

    def test_camelcase_variant_also_handled(self):
        self.assertIn("default contact.firstName",
                      mf.ensure_fallbacks("{{contact.firstName}}"))

    def test_every_occurrence_is_wrapped(self):
        out = mf.ensure_fallbacks(
            "{{contact.first_name}} ... {{contact.first_name}}")
        self.assertEqual(out.count("{{default"), 2)

    def test_is_idempotent(self):
        # Running twice must not double-wrap — create-campaign may be re-run on
        # copy that already went through it.
        once = mf.ensure_fallbacks("Hi {{contact.first_name}}")
        twice = mf.ensure_fallbacks(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("default"), 1)

    def test_existing_fallback_is_preserved_not_overwritten(self):
        original = '{{default contact.first_name "friend"}}'
        self.assertEqual(mf.ensure_fallbacks(original, "there"), original)

    def test_other_merge_fields_untouched(self):
        text = "{{contact.last_name}} {{contact.email}} {{location.name}}"
        self.assertEqual(mf.ensure_fallbacks(text), text)

    def test_quotes_in_fallback_are_escaped(self):
        out = mf.ensure_fallbacks("{{contact.first_name}}", 'the "boss"')
        self.assertIn(r'\"boss\"', out)

    def test_backslash_in_fallback_is_escaped_first(self):
        out = mf.ensure_fallbacks("{{contact.first_name}}", "a\\b")
        self.assertIn("a\\\\b", out)

    def test_empty_and_none_input_are_safe(self):
        self.assertEqual(mf.ensure_fallbacks(""), "")
        self.assertIsNone(mf.ensure_fallbacks(None))

    def test_works_inside_html(self):
        html = "<p>Hi {{contact.first_name}}, welcome</p>"
        out = mf.ensure_fallbacks(html)
        self.assertIn('<p>Hi {{default contact.first_name "there"}}, welcome</p>', out)


class DetectionTests(unittest.TestCase):
    def test_detects_bare_token(self):
        self.assertTrue(mf.has_first_name("Hi {{contact.first_name}}"))

    def test_detects_already_wrapped_token(self):
        self.assertTrue(
            mf.has_first_name('Hi {{default contact.first_name "there"}}'))

    def test_rejects_copy_with_no_personalization(self):
        self.assertFalse(mf.has_first_name("<p>Hello everyone</p>"))

    def test_other_contact_fields_do_not_count_as_first_name(self):
        self.assertFalse(mf.has_first_name("{{contact.last_name}}"))

    def test_empty_input_is_false_not_error(self):
        self.assertFalse(mf.has_first_name(""))
        self.assertFalse(mf.has_first_name(None))

    def test_counts_only_bare_tokens(self):
        text = ('{{contact.first_name}} '
                '{{default contact.first_name "x"}} '
                '{{contact.first_name}}')
        self.assertEqual(mf.count_bare_first_name(text), 2)

    def test_count_on_empty_is_zero(self):
        self.assertEqual(mf.count_bare_first_name(""), 0)
        self.assertEqual(mf.count_bare_first_name(None), 0)


if __name__ == "__main__":
    unittest.main()
