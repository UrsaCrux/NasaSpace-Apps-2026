"""Export of fields and their results to one ZIP file.

    options = ExportOptions(geojson=True, status=True, trends=True,
                            analyses=("water",))
    bundles = [collect(field, options) for field in fields]   # slow: worker thread
    write_zip("PACHI_export.zip", bundles, options)           # UI thread (charts)

The ZIP holds a readable report (informe.pdf) and, per field, the GeoJSON,
the measurements (CSV) and each result as JSON + CSV + PNG charts. A part
that could not be downloaded is written as its reason, never as made-up
numbers. See docs/export.md.
"""

from fieldshift.export.collect import ExportOptions, FieldBundle, collect  # noqa: F401
