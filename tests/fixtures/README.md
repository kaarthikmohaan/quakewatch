# Source fixtures

- `normal_event.json` is the complete USGS GeoJSON feature for public event `uw714110682`, copied from the first row of the Seattle 2026-09-28 UTC capture in ignored `data/raw/20260929T075452Z-26375840ea/events.jsonl`.
- `synthetic_revision_event.json` is test data derived from `normal_event.json`. It keeps the same event ID and origin time, moves `properties.updated` forward by 60 seconds, changes `properties.mag` from 1.08 to 1.28, and updates the title's rounded magnitude. USGS did not publish this edited record.
- `deleted_event.json` is the complete public GeoJSON feature for USGS event `nn00925000`, fetched on 2026-09-29 with `format=geojson`, `starttime=2026-09-01`, `endtime=2026-09-29`, `includedeleted=only`, and `limit=1`. Its `properties.status` is `deleted`. This single sample is not a count reconciliation or a coverage claim. [USGS documents the `includedeleted` parameter](https://earthquake.usgs.gov/fdsnws/event/1/).
- `malformed_response.txt` is intentionally truncated JSON. It represents a whole HTTP 200 query response that must fail parsing, not an empty event collection.
- `additive_field_event.json` is synthetic test data derived from `normal_event.json`. It adds the nested `properties.future_catalog_field` value and changes nothing else. The field checks that extraction keeps unfamiliar source content.
- `count_mismatch_case.json` is a synthetic response scenario: count before and after says two events, while the query response contains the single feature in `normal_event.json`. Its one-microsecond window cannot split further, so the extractor must report the unresolved mismatch.
- `over_limit_case.json` is a synthetic response scenario: the parent window counts 20,000 events, reaching the FDSN result limit, while each child counts zero. It checks that the parent is split before a feature query and that both child windows are audited.
- `incomplete_window_case.json` is a synthetic persistent mismatch: both count requests say one event while the feature response is empty. It checks that an unsplittable window marks the saved batch manifest as failed.

The event JSON files contain source features only. Scenario files describe mocked API responses. Batch metadata is added separately by the extractor and is not part of a source GeoJSON feature.
