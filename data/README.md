# data/

Small datasets bundled with the app.

| File | Content | Source / licence |
|------|---------|------------------|
| `countries.geojson` | Country outlines (1:110m), fields `name`, `iso_a3`, `continent` | [Natural Earth](https://www.naturalearthdata.com/) — public domain |

`countries.geojson` is loaded under the OpenStreetMap tiles so the map shows
something even without an internet connection.

Put large or downloaded datasets (NASA rasters, etc.) somewhere else and keep
them out of git (`data/local/` is ignored).
