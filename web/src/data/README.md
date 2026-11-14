# Map data

`ct-zcta.json` holds Connecticut ZIP Code Tabulation Areas (ZCTAs) for the dashboard's
"Where clients live" map. The map is drawn in the browser from this file, so nothing is
requested from outside the library's network.

## Source

- U.S. Census Bureau, 2020 ZIP Code Tabulation Areas, cartographic boundary file, 1:500,000
  (`cb_2020_us_zcta520_500k.zip`).
- Downloaded from https://www2.census.gov/geo/tiger/GENZ2020/shp/
- The data.gov listing shows this file as CC0 (public domain).

## How it was made

Built on 2026-11-14 by `scripts/prepare-ct-zips.sh`, using mapshaper 0.7.101:

1. Kept only ZIPs starting with `06` (289 of 33,791 areas).
2. Kept only the ZIP field, renamed to `zip`.
3. Simplified to 25% of the vertices, keeping small shapes (`keep-shapes`).
4. Wrote GeoJSON rounded to 0.0001 degrees (about 11 meters), with polygon rings wound
   clockwise, which is the direction the map library expects.

Result: 289 areas, about 134 KB. Coordinates are NAD83 longitude/latitude, which differs from
WGS84 by a meter or two. That is invisible at this scale.

To regenerate it (needs internet access for the download):

    sudo docker compose run --rm web sh scripts/prepare-ct-zips.sh

Then run `npm test`. `ct-zcta.test.js` checks the result, including the winding direction.
Do not edit the JSON by hand. Update the version and date above when you regenerate.

## Limits

- ZCTAs approximate ZIP codes. Census builds them from the most common ZIP code in each
  block, so some ZIPs (PO-box ZIPs, for example) have no area. The dashboard lists clients in
  those ZIPs beside the map and counts them in totals and the CSV export.
- Simplified for display. Do not use for geocoding, measuring areas, or deciding which ZIP an
  address belongs to.