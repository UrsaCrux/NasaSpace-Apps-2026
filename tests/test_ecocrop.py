"""Tests for fieldshift.crops.ecocrop and the crop widgets of the field
dialog (no network: EcoCrop pages are small samples of the real layout)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import crops, i18n  # noqa: E402
from fieldshift.crops import ecocrop  # noqa: E402
from qt_app import get_app  # noqa: E402

LIST_PAGE = """<table><tr><th>Name</th><th>Synonyms</th><th>Common Names</th></tr>
<tr><td><a onClick="javascript:load(&quot;/ecocrop/srv/en/cropView?id=1796&quot;)"
 href="javascript:load(%22/ecocrop/srv/en/cropView?id=1796%22)" class="serviceLink">Prunus persica</a></td><td>Amygdalus persica Linn., Prunus persicae Stokes</td><td>melocoton, peach, p&ecirc;che, Pfirsich</td><td>x</td></tr>
<tr><td><a onClick="javascript:load(&quot;/ecocrop/srv/en/cropView?id=10895&quot;)"
 href="x" class="serviceLink">Vitis labrusca</a></td><td></td><td>fox grape, Isabella grape</td><td>x</td></tr>
<tr><td><a onClick="javascript:load(&quot;/ecocrop/srv/en/cropView?id=1877&quot;)"
 href="x" class="serviceLink">Rubus idaeus ssp. idaeus</a></td><td>Rubus idaeus ssp. idaeus L., Rubus idaeus ssp. vulgatus Arrhen., 1839</td><td>frambuesa, raspberry</td><td>x</td></tr>
<tr><td><a onClick="javascript:load(&quot;/ecocrop/srv/en/cropView?id=2175&quot;)"
 href="x" class="serviceLink">Zea mays</a></td><td>Zea curagua Molina</td><td>corn, maize, ma&iacute;z</td><td>x</td></tr>
</table>"""

VIEW_INLINE = """<h2>Prunus persica</h2><table><tr><td><img src="/ecocrop/ec_images/1796.jpg"></td><td>
<table><tr><th class="label">Authority</th><td>(L.)Batsch</td></tr>
<tr><th class="label">Family</th><td>Magnoliopsida:Rosidae:Rosales:Rosaceae</td></tr>
<tr><th class="label">Synonyms</th><td>Amygdalus persica Linn., Prunus persica Stokes</td></tr>
<tr><th class="label">Common names</th><td>melocoton, peach, p&ecirc;che</td></tr></table></td></tr></table>
<table width="100%"><th>
\t\t\t\tNotes
\t\t\t</th>
<tr>
<td>BRIEF DESCRIPTION  A shrub or small deciduous tree reaching up to 8 m in height. USES  The fruit can be used fresh. KILLING T  Opened flowers are killed by frosts. FURTHER INF  Peach is native of Iran or China.</td>
</tr>
<th>
\t\t\t\tSources
\t\t\t</th>
<tr>
<td>SOURCES (P. persica)<br>
Duke J 1979 pp 100 [PH, RAIN, TEMP]</td>
</tr></table>"""

VIEW_LINES = """<h2>Rubus idaeus ssp. idaeus</h2>
<table><th>Notes</th>
<tr>
<td>SOURCES<br>
Dube P 1982 pp 18<br>
<br>
GROWING PERIOD<br>
Perennial shrub, with an economical life of about 20 years. <br>
<br>
FURTHER INF<br>
Red rasberry is native of Europe.<br>
</td>
</tr>
<th>Sources</th>
<tr>
<td></td>
</tr></table>"""

VIEW_COLON = """<h2>Zea mays</h2><table><th>Notes</th>
<tr>
<td>DESCRIPTION: A tall vigorous annual grass, and grain crop. USES: Grain, fodder. GROWING PERIOD: Annual.</td>
</tr></table>"""

SHEET = """<table><tr><th colspan="4">Description</th></tr>
<tr><th>Life form</th><td>shrub, tree</td><th>Physiology</th><td>deciduous</td></tr>
<tr><th>Habit</th><td>erect</td><th>Category</th><td>fruits &amp; nuts</td></tr>
<tr><th>Life span</th><td>perennial</td><th>Plant attributes</th><td>grown on large scale</td></tr></table>
<table><tr><th colspan="8">Ecology</th></tr>
<tr><td></td><td>Min</td><td>Max</td><td>Min</td><td>Max</td><th>Soil depth</th><td>deep (&gt;&gt;150 cm)</td><td>medium (50-150 cm)</td></tr>
<tr><th>Temperat. requir.</th><td>20</td><td>33</td><td>7</td><td>35</td><th>Soil texture</th><td>medium, light</td><td>heavy, medium, light</td></tr>
<tr><th>Rainfall (annual)</th><td>900</td><td>1100</td><td>750</td><td>1600</td><th>Soil fertility</th><td>high</td><td>moderate</td></tr>
<tr><th>Altitude</th><td>
\t---
</td><td>---</td><td>-</td><td>1000</td><th>Soil salinity</th><td>low (&lt;4 dS/m)</td><td>low (&lt;4 dS/m)</td></tr>
<tr><th>Soil PH</th><td>5.5</td><td>6.3</td><td>4.5</td><td>7.5</td><th>Soil drainage</th><td>well (dry spells)</td><td>well (dry spells)</td></tr></table>
<table><tr><th>Climate zone</th><td>subtropical dry summer (Cs)</td><th>Photoperiod</th><td>neutral day (12-14 hours)</td></tr>
<tr><th>Killing temp. during rest</th><td>-5</td><th>Killing temp. early growth</th><td>-3</td></tr></table>
<table><tr><th colspan="5">Cultivation</th></tr><tr><td colspan="3"></td><td>Min</td><td>Max</td></tr>
<tr><th>Product. system</th><td>home garden</td><th>Crop cycle</th><td>240</td><td>270</td></tr></table>
<table><tr><th>Main use</th><th>Detailed use</th><th>Used part</th></tr>
<tr><td>food &amp; beverage</td><td>vitamins</td><td>fruits</td></tr></table>"""


def setUpModule():
    get_app()


class _Cache(unittest.TestCase):
    """Each test gets an empty cache and no index in memory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_CACHE": self._tmp.name})
        env.start()
        self.addCleanup(env.stop)
        ecocrop.set_index(None)
        self.addCleanup(ecocrop.set_index, None)
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "en")


class ParseTest(unittest.TestCase):
    def test_index(self):
        entries = ecocrop.parse_index(LIST_PAGE)
        self.assertEqual([e.id for e in entries], [1796, 10895, 1877, 2175])
        peach = entries[0]
        self.assertEqual(peach.name, "Prunus persica")
        self.assertIn("pêche", peach.common_names)
        self.assertEqual(entries[2].synonyms, ("Rubus idaeus ssp. idaeus L.",
                                               "Rubus idaeus ssp. vulgatus Arrhen."))  # no "1839"

    def test_three_note_layouts(self):
        peach = ecocrop.parse_crop_view(VIEW_INLINE, 1796)
        self.assertEqual(peach.brief, "A shrub or small deciduous tree reaching up to 8 m in height.")
        self.assertEqual(list(peach.sections), ["BRIEF DESCRIPTION", "USES", "KILLING T",
                                                "FURTHER INF"])
        self.assertEqual((peach.authority, peach.common_names[2]), ("(L.)Batsch", "pêche"))
        self.assertEqual(peach.image_url, "https://ecocrop.apps.fao.org/ecocrop/ec_images/1796.jpg")
        self.assertEqual(peach.sources[1], "Duke J 1979 pp 100 [PH, RAIN, TEMP]")
        rasp = ecocrop.parse_crop_view(VIEW_LINES, 1877)
        self.assertEqual(rasp.brief, "Red rasberry is native of Europe.")    # not the sources
        self.assertTrue(rasp.sources)                                       # moved from notes
        self.assertNotIn("Dube", rasp.description)
        maize = ecocrop.parse_crop_view(VIEW_COLON, 2175)
        self.assertEqual(maize.brief, "A tall vigorous annual grass, and grain crop.")
        self.assertEqual(maize.sections["USES"], "Grain, fodder.")

    def test_data_sheet(self):
        info = ecocrop.parse_data_sheet(SHEET, ecocrop.CropInfo(1796, "Prunus persica"))
        self.assertEqual(info.temperature, ecocrop.Range(20, 33, 7, 35))
        self.assertEqual(info.rainfall, ecocrop.Range(900, 1100, 750, 1600))
        self.assertEqual(info.ph, ecocrop.Range(5.5, 6.3, 4.5, 7.5))
        self.assertEqual(info.altitude, ecocrop.Range(None, None, None, 1000))
        self.assertEqual(info.soil_texture, {"optimal": "medium, light",
                                             "absolute": "heavy, medium, light"})
        self.assertEqual(info.soil_salinity["optimal"], "low (<4 dS/m)")
        self.assertEqual((info.killing_temp_rest, info.killing_temp_early_growth), (-5, -3))
        self.assertEqual((info.crop_cycle_min, info.crop_cycle_max), (240, 270))
        self.assertEqual((info.life_form, info.category), ("shrub, tree", "fruits & nuts"))
        self.assertEqual(info.uses, [{"use": "food & beverage", "detail": "vitamins",
                                      "part": "fruits"}])


class SearchTest(_Cache):
    def setUp(self):
        super().setUp()
        self.index = ecocrop.parse_index(LIST_PAGE)

    def test_scientific_variety_and_common_names(self):
        def names(text):
            return [e.name for e in ecocrop.search(text, index=self.index)]
        self.assertEqual(names("prunus persica"), ["Prunus persica"])          # scientific
        self.assertEqual(names("amygdalus")[:1], ["Prunus persica"])           # synonym
        self.assertEqual(names("vulgatus"), ["Rubus idaeus ssp. idaeus"])      # variety
        self.assertEqual(names("MELOCOTON"), ["Prunus persica"])               # common
        self.assertEqual(names("peche"), ["Prunus persica"])                   # accents
        self.assertEqual(names("isabella"), ["Vitis labrusca"])                # any word
        self.assertEqual(names("maiz"), ["Zea mays"])
        self.assertEqual(names("x"), [])                                       # too short

    def test_find(self):
        self.assertEqual(ecocrop.find(2175, index=self.index).name, "Zea mays")
        self.assertEqual(ecocrop.find("raspberry", index=self.index).id, 1877)
        self.assertIsNone(ecocrop.find("unobtainium", index=self.index))


class NetworkCacheTest(_Cache):
    def test_index_and_crop_are_downloaded_once(self):
        pages = {ecocrop.LIST_URL: LIST_PAGE, ecocrop.VIEW_URL.format(id=1796): VIEW_INLINE,
                 ecocrop.SHEET_URL.format(id=1796): SHEET}
        with mock.patch.object(ecocrop, "_get", side_effect=lambda url, **kw: pages[url]) as get:
            self.assertEqual(len(ecocrop.load_index()), 4)
            info = ecocrop.get_crop("melocoton")
            again = ecocrop.get_crop(1796)
            ecocrop.set_index(None)
            self.assertEqual(len(ecocrop.load_index()), 4)        # from the disk cache
        self.assertEqual(get.call_count, 3)
        self.assertEqual(info.to_dict(), again.to_dict())
        self.assertEqual(again.temperature.optimal_min, 20)

    def test_unknown_crop(self):
        with mock.patch.object(ecocrop, "_get", return_value=LIST_PAGE):
            with self.assertRaises(LookupError):
                ecocrop.get_crop("unobtainium")

    def test_image_and_missing_image(self):
        import requests
        jpeg = b"\xff\xd8\xff\xe0 fake jpeg"
        with mock.patch.object(ecocrop, "_get", return_value=jpeg) as get:
            self.assertEqual(ecocrop.get_image(1796), jpeg)
            self.assertEqual(ecocrop.get_image(1796), jpeg)
        self.assertEqual(get.call_count, 1)
        missing = requests.HTTPError(response=mock.Mock(status_code=404))
        with mock.patch.object(ecocrop, "_get", side_effect=missing):
            self.assertIsNone(ecocrop.get_image(1313))
        with mock.patch.object(ecocrop, "_get") as get:
            self.assertIsNone(ecocrop.get_image(1313))          # 404 remembered
        get.assert_not_called()

    def test_cli(self):
        from io import StringIO
        pages = {ecocrop.LIST_URL: LIST_PAGE, ecocrop.VIEW_URL.format(id=1796): VIEW_INLINE,
                 ecocrop.SHEET_URL.format(id=1796): SHEET}
        out = StringIO()
        with mock.patch.object(ecocrop, "_get", side_effect=lambda url, **kw: pages[url]), \
                mock.patch("sys.stdout", out):
            self.assertEqual(ecocrop.main(["peach"]), 0)
        self.assertIn('"scientific_name": "Prunus persica"', out.getvalue())


class CatalogLinkTest(unittest.TestCase):
    def test_every_catalogue_crop_names_its_ecocrop_plant(self):
        import json
        catalog = json.loads(crops.CATALOG_PATH.read_text("utf-8"))["crops"]
        self.assertTrue(all(c.get("ecocrop") for c in catalog))
        self.assertEqual(crops.ecocrop_name("peach.v2"), "Prunus persica")
        self.assertEqual(crops.crop_for_ecocrop("Zea mays"), "maize")
        self.assertEqual(crops.ecocrop_number("ecocrop:1796"), 1796)
        self.assertTrue(crops.is_variety("ecocrop:10895"))
        self.assertFalse(crops.is_variety("ecocrop:abc"))


class _WidgetCase(_Cache):
    def search(self, **kw):
        from fieldshift.ui.crop_widgets import CropSearch
        index = ecocrop.parse_index(LIST_PAGE)
        widget = CropSearch(load_index=lambda: index, **kw)
        from test_fields_ui import wait_until
        wait_until(widget.has_ecocrop)
        return widget

    def type(self, widget, text):
        widget.setText(text)
        widget.textEdited.emit(text)


class CropSearchEcoCropTest(_WidgetCase):
    def test_ecocrop_plants_join_the_suggestions(self):
        search = self.search()
        self.type(search, "isabella")
        self.assertEqual(search.suggestions(), ["Vitis labrusca — fox grape, Isabella grape  (EcoCrop)"])
        search._on_activated(search.suggestions()[0])
        self.assertEqual(search.selected(), "ecocrop:10895")
        self.assertEqual(search.text(), "Vitis labrusca")
        self.assertEqual(search.selected_name(), "Vitis labrusca")

    def test_a_catalogue_crop_found_by_scientific_name_offers_its_varieties(self):
        search = self.search()
        self.type(search, "Prunus persica")
        self.assertEqual(search.suggestions()[:3], ["Peach – variety 1", "Peach – variety 2",
                                                    "Peach – variety 3"])
        self.assertFalse(any("EcoCrop" in s for s in search.suggestions()))
        self.type(search, "vitis lab")
        self.type(search, "Vitis labrusca")                      # exact name chooses it
        self.assertEqual(search.selected(), "ecocrop:10895")

    def test_without_ecocrop_only_the_catalogue(self):
        from fieldshift.ui.crop_widgets import CropSearch
        search = CropSearch()                                      # offline in the tests
        self.assertFalse(search.has_ecocrop())
        self.type(search, "isabella")
        self.assertEqual(search.suggestions(), [])


class CropInfoPanelTest(_WidgetCase):
    def info(self, brief="A shrub.", image=True):
        from fieldshift.qt import QtCore, QtGui
        info = ecocrop.CropInfo(1796, "Prunus persica", common_names=["peach", "melocoton"],
                                brief=brief, description=brief, url="https://x/1796")
        data = None
        if image:
            img = QtGui.QImage(400, 100, QtGui.QImage.Format.Format_RGB32)  # very wide
            img.fill(QtGui.QColor("#cc6633"))
            buffer = QtCore.QBuffer()
            buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
            img.save(buffer, "PNG")
            data = bytes(buffer.data())
        return info, data

    def panel(self, fetch):
        from fieldshift.ui.crop_widgets import CropInfoPanel
        panel = CropInfoPanel(fetch=fetch)
        self.addCleanup(panel.cancel)
        return panel

    def test_shows_picture_names_and_short_description(self):
        from fieldshift.ui.crop_widgets import IMAGE_H, IMAGE_W, MAX_DESCRIPTION_CHARS
        from test_fields_ui import wait_until
        long_text = "word " * 200
        asked = []
        panel = self.panel(lambda target: (asked.append(target), self.info(long_text))[1])
        self.assertTrue(panel.isHidden())
        panel.show_crop("peach.v1")
        self.assertEqual(panel.state(), "loading")
        self.assertFalse(panel.isHidden())
        wait_until(lambda: panel.state() == "ready")
        self.assertEqual(asked, ["Prunus persica"])                # catalogue crop -> EcoCrop
        self.assertEqual(panel.name_label.text(), "Prunus persica")
        self.assertEqual(panel.common_label.text(), "Peach, melocoton")   # catalogue name first
        text = panel.description_label.text()
        self.assertTrue(text.endswith("..."))
        self.assertLessEqual(len(text), MAX_DESCRIPTION_CHARS + 3)
        self.assertIn("word word", panel.description_label.toolTip())   # full text on hover
        pixmap = panel.image_label.pixmap()
        self.assertEqual((pixmap.width(), pixmap.height()), (IMAGE_W, IMAGE_H))  # cropped
        self.assertIn("FAO EcoCrop", panel.source_label.text())

    def test_ecocrop_plant_and_hiding(self):
        from test_fields_ui import wait_until
        asked = []
        panel = self.panel(lambda target: (asked.append(target), self.info())[1])
        panel.show_crop("ecocrop:10895")
        wait_until(lambda: panel.state() == "ready")
        self.assertEqual(asked, [10895])
        self.assertEqual(panel.common_label.text(), "peach, melocoton")
        self.assertEqual(panel.description_label.text(), "A shrub.")      # short: unchanged
        panel.show_crop(None)
        self.assertTrue(panel.isHidden())

    def test_failure_and_missing_picture(self):
        from test_fields_ui import wait_until

        def fail(target):
            raise ConnectionError("offline")
        panel = self.panel(fail)
        panel.show_crop("peach.v1")
        wait_until(lambda: panel.state() == "missing")
        self.assertIn("No information", panel.description_label.text())
        self.assertEqual(panel.name_label.text(), "Prunus persica")       # still named
        panel = self.panel(lambda target: self.info(image=False))
        panel.show_crop("peach.v1")
        wait_until(lambda: panel.state() == "ready")
        self.assertEqual(panel.image_label.text(), "no picture")

    def test_shorten(self):
        from fieldshift.ui.crop_widgets import shorten
        self.assertEqual(shorten("short text", 50), "short text")
        self.assertEqual(shorten("one two three four", 12), "one two...")
        self.assertEqual(shorten("one, two, three", 9), "one, two...")


class DialogTest(_WidgetCase):
    def test_choosing_a_crop_fills_the_panel_and_the_data(self):
        from fieldshift.fields import FieldStore
        from fieldshift.ui.field_dialog import FieldDialog
        from test_fields_ui import SQUARE, fake_fetch, wait_until
        index = ecocrop.parse_index(LIST_PAGE)
        info = ecocrop.CropInfo(10895, "Vitis labrusca", common_names=["fox grape"],
                                brief="Deciduous herbaceous vine.", url="u")
        dialog = FieldDialog(FieldStore(Path(self._tmp.name) / "f"), vertices=SQUARE,
                             fetch=fake_fetch, crop_info_fetch=lambda t: (info, None),
                             load_ecocrop=lambda: index)
        self.addCleanup(dialog.done, 0)
        wait_until(lambda: dialog.crop_search.has_ecocrop() and not dialog.is_loading())
        self.assertTrue(dialog.crop_info.isHidden())
        self.type(dialog.crop_search, "Vitis labrusca")
        wait_until(lambda: dialog.crop_info.state() == "ready")
        self.assertEqual(dialog.crop_info.description_label.text(), "Deciduous herbaceous vine.")
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(dialog.data()["crop"], {"value": "ecocrop:10895", "source": "user",
                                                 "name": "Vitis labrusca"})


if __name__ == "__main__":
    unittest.main()
