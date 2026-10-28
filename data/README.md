# South Florida land layer

Made with Natural Earth. Source: [1:10m land](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/), [public-domain terms](https://www.naturalearthdata.com/about/terms-of-use/).

The bundled JSON uses longitude/latitude coordinates. It includes land polygon exteriors, holes, and separately clipped coastlines. Regional extent: [-82, 24.5, -78.5, 28]. Source archive URL and SHA-256 are included in the JSON.

Prepared by clipping the original polygons to the regional extent and simplifying at 0.0005 degrees with topology preservation. Source boundaries were intersected with the regional extent separately to avoid portraying artificial clip edges as coastline.

Natural Earth's 1:10m notation means 1:10,000,000 map scale, not 10-meter accuracy. This generalized layer is only for visual context.

## Offline MMSI country lookup

`mid-countries.json` contains 292 Maritime Identification Digit assignments from the [ITU allocation table](https://www.itu.int/gladapp/Allocation/MIDs), retrieved October 27, 2026. It preserves the ITU country/administration names. Only ordinary nine-digit ship MMSIs beginning with 2–7 are inferred; special station/auxiliary identifiers are left unknown. Flag country inferred this way is not independent registry verification.

Regenerate from a downloaded ITU HTML page with `python tools/build_mid_table.py path/to/itu-mids.html`. The raw source is kept locally under ignored `.local/` and is not required at runtime.

Field interpretation references: [AISstream message schema](https://github.com/aisstream/ais-message-models/blob/master/type-definition.yaml), [USCG AIS Class A fields](https://www.navcen.uscg.gov/ais-class-a-reports), [USCG MMSI formats](https://www.navcen.uscg.gov/mmsi-formats). Dimensions use A+B for length and C+D for beam; capped offsets are lower bounds. ETA has no transmitted year. Class B auxiliary-craft dimension bits are not interpreted as dimensions.

