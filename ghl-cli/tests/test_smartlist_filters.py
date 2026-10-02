"""Tests for the smart-list --filter expression parser."""
from __future__ import annotations

import unittest

import click

from cli_anything.gohighlevel.gohighlevel_cli import _parse_filter


class ParseFilterTests(unittest.TestCase):
    def test_valueless_operator(self):
        self.assertEqual(
            _parse_filter("email:exists"),
            {"operator": "exists", "field": "email"},
        )

    def test_valueless_operator_rejects_a_value(self):
        with self.assertRaises(click.BadParameter):
            _parse_filter("email:exists:yes")

    def test_scalar_value(self):
        self.assertEqual(
            _parse_filter("firstName:eq:Jay"),
            {"operator": "eq", "field": "firstName", "value": "Jay"},
        )

    def test_booleans_are_coerced(self):
        self.assertIs(_parse_filter("valid_email:eq:true")["value"], True)
        self.assertIs(_parse_filter("dnd:not_eq:False")["value"], False)

    def test_comma_list_becomes_array_with_minimum_match(self):
        leaf = _parse_filter("tags:not_eq:blacklist,unsubbed")
        self.assertEqual(leaf["value"], ["blacklist", "unsubbed"])
        self.assertEqual(leaf["options"], {"minimumMatch": 1})

    def test_comma_list_trims_and_drops_blanks(self):
        self.assertEqual(
            _parse_filter("tags:eq: a , ,b ")["value"], ["a", "b"])

    def test_dotted_field_paths_survive(self):
        # GHL uses paths like dnd_settings.Email.status
        leaf = _parse_filter("dnd_settings.Email.status:not_eq:true")
        self.assertEqual(leaf["field"], "dnd_settings.Email.status")

    def test_value_may_contain_colons(self):
        leaf = _parse_filter("website:eq:https://x.com")
        self.assertEqual(leaf["value"], "https://x.com")

    def test_missing_operator_rejected(self):
        with self.assertRaises(click.BadParameter):
            _parse_filter("email")

    def test_operator_needing_value_rejected_without_one(self):
        with self.assertRaises(click.BadParameter):
            _parse_filter("firstName:eq")


if __name__ == "__main__":
    unittest.main()
