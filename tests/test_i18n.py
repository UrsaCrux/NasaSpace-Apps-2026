"""Tests for the translation files (no Qt needed)."""

import json
import unittest
from unittest import mock

from fieldshift import i18n


class I18nTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_every_language_has_the_english_keys(self):
        english = set(i18n._load("en"))
        for code in i18n.available_languages():
            with self.subTest(language=code):
                keys = set(json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text("utf-8")))
                self.assertEqual(keys, english)

    def test_switch_language_and_fill_values(self):
        i18n.set_language("es")
        self.assertEqual(i18n.tr("fields.draw"), "Marcar terreno")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("fields.export_done", count=2, path="x"),
                         "2 field(s) exported to x")

    def test_unknown_key_returns_the_key(self):
        self.assertEqual(i18n.tr("no.such.key"), "no.such.key")

    def test_unknown_language_raises(self):
        with self.assertRaises(ValueError):
            i18n.set_language("xx")


class CommandLineTest(unittest.TestCase):
    def test_lang_option_is_taken_out_of_the_qt_arguments(self):
        from fieldshift.app import parse_args
        self.assertEqual(parse_args(["fieldshift", "--lang", "es", "-style", "fusion"]),
                         ("es", ["fieldshift", "-style", "fusion"]))
        self.assertEqual(parse_args(["fieldshift"]), (None, ["fieldshift"]))

    def test_unknown_language_is_refused(self):
        from fieldshift.app import parse_args
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            parse_args(["fieldshift", "--lang", "xx"])


if __name__ == "__main__":
    unittest.main()
