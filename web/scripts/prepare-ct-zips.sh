#!/bin/sh
# Builds src/data/ct-zcta.json: Connecticut ZIP Code Tabulation Areas, for the dashboard map.
# Run this file from the project's root:
#   sudo docker compose run --rm web sh scripts/prepare-ct-zips.sh
set -eu

URL="https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
OUT="src/data/ct-zcta.json"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Downloading the Census ZCTA boundary file (about 64 MB)..."
node -e 'fetch(process.argv[1]).then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.arrayBuffer()}).then(b=>require("node:fs").writeFileSync(process.argv[2],Buffer.from(b)))' "$URL" "$WORK/zcta.zip"
unzip -q "$WORK/zcta.zip" -d "$WORK"
SHP="$(ls "$WORK"/*.shp | head -n 1)"

mkdir -p src/data
echo "mapshaper version:"
npx --yes mapshaper -version
echo "Fields in the file:"
npx --yes mapshaper "$SHP" -info | head -n 30

npx --yes mapshaper "$SHP" \
  -filter 'String(ZCTA5CE20).indexOf("06") === 0' \
  -filter-fields ZCTA5CE20 \
  -rename-fields zip=ZCTA5CE20 \
  -simplify 25% keep-shapes \
  -o "$OUT" format=geojson precision=0.0001 reverse-winding

node -e '
const fs = require("node:fs");
const data = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const bad = data.features.filter((f) => !/^06\d{3}$/.test(String(f.properties.zip)));
if (data.features.length < 150 || bad.length) {
  console.error("Unexpected result: " + data.features.length + " features, " + bad.length + " with a bad ZIP");
  process.exit(1);
}
console.log("OK: " + data.features.length + " Connecticut ZIP areas");
' "$OUT"
ls -l "$OUT"