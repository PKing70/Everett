# Everett Police Incidents for Splunk

Version 1.0.0. A Python 3 modular input and two classic Simple XML dashboards for the City of Everett Police Incidents dataset, `f6vp-3svh`. No third-party Python libraries are required.

## Install and enable

1. Install `everett_police-1.0.0.tar.gz` with Splunk Web **Apps > Manage Apps > Install app from file** on a Splunk Enterprise instance with Python 3. Restart Splunk if prompted. This package has not been certified through AppInspect or tested on a running Splunk instance.
2. In the app directory, create `local/inputs.conf` with:

   ```ini
   [everett_police://incidents]
   disabled = 0
   index = main
   ```

   Alternatively configure the input through **Settings > Data inputs > Everett Police Incidents**. Enable only one collector for this dataset. The shipped input is disabled to let you choose the destination index first.
3. Restart Splunk after file-based configuration changes. Open **Everett Police Incidents**. By default, collection scans a rolling 30-day incident window plus one calendar day for timezone boundary coverage; subsequent scans run 3600 seconds after the previous scan finishes. Set lookback_days = 0 for all history, or another positive number for a different window. The live dataset contained 1,606,532 rows during development, so full history has materially greater ingestion and API cost.
4. Check **Collection Health** for a successful scan. Verify with `index=main sourcetype=everett:police:collection` and `index=main sourcetype=everett:police:incident | head 10`.

To use another index, provision it using your normal index administration process, change the input's `index`, and override both macros in `local/macros.conf` with that index. Users need search access to that index. No index is created automatically.

For distributed deployments, run collection on one Python-enabled heavy forwarder or Enterprise instance; install parsing props on the parsing tier and the app on the search head for extraction and dashboards. Do not enable multiple collectors. Splunk Cloud deployment requires the applicable app review and an appropriate external collection tier; this archive is not a claim of Cloud approval. A universal forwarder without Python is not a supported collector.

## Authentication and transport

The exact supplied SODA3 endpoint is used via HTTPS POST with JSON `query` and `page`. A two-row unauthenticated request returned HTTP 200 during development on 2026-09-14. Socrata's documentation nevertheless requires authentication or an application token; configure `SOCRATA_APP_TOKEN` in the Splunk service environment for dependable operation. Restart the service after environment changes. `token_env` can select another environment variable. Never put a token directly in inputs.conf. Tokens are sent only as `X-App-Token`; the endpoint is fixed to Everett. TLS verification stays enabled and uses the Python runtime's trust store. For a managed CA, configure the runtime trust store or `SSL_CERT_FILE`; do not disable verification.

HTTP 429 and transient 5xx/network failures retry up to five attempts with bounded delays. Persistent failures produce collection health events and sanitized stderr messages. HTTP 401/403 usually requires checking the token; no API response bodies or credentials are logged.

## Collection semantics

Each scan reads ordered pages within the configured incident window. A SQLite checkpoint in Splunk's supplied checkpoint directory stores the content hash of each `eventnumber`. New or changed rows emit a JSON event; unchanged rows do not. Missing identifiers or unexpected response shapes fail the scan. Checkpoints commit after a page has been flushed to stdout. A crash may replay that page; transport to Splunk is not transactionally acknowledged, so this is not an exactly-once guarantee. The dashboards deduplicate by `eventnumber` using latest index time.

Window rescans discover corrections within the configured incident window without assuming a reliable source update timestamp. Corrections outside that window are not collected unless you expand it or set lookback_days = 0. The API does not promise a frozen snapshot across requests: concurrent publication can shift page boundaries. The next scan reconciles available records within its window. Source deletions do not delete previously indexed events, and the app retains historical records after they leave the public feed. Set index retention according to your needs. Checkpoint storage grows with unique incident identifiers; stopping the input and removing its checkpoint causes a replay of the configured window. Renaming an input also starts a new checkpoint.

Dashboard time ranges select incident timestamps before deduplication. If the source changes an incident's timestamp across the selected time boundary, an older version may remain visible in that time range. Use an all-time search and dedup before applying time filters for audits requiring the latest version across all history. Concurrent updates indexed within the same second may have a tied latest index time.

## Fields and timestamps

Original API fields are retained: `eventnumber`, `eventyear`, `datetimereceived`, `incidenttype`, `incidentprogress`, `howreceived`, `eventaddressby100block`, `disposition`, `neighborhood`, `beat`, `area`, `precinct`, and `geomcoordinate`. Missing fields remain absent. GeoJSON coordinates are mapped to `longitude` and `latitude` in that order. `everett_collected_at` and `everett_record_hash` are added for auditing.

The source's calendar timestamp has no UTC offset. The app interprets it as `America/Los_Angeles`, an explicit assumption based on the city's locality; override `TZ` in local/props.conf if the publisher confirms different semantics. Fall-back DST times are intrinsically ambiguous in the source. Splunk displays times in the viewer's timezone. Collection health uses an explicit epoch event time.

Incidents are calls for police response, including officer-initiated activity, rather than adjudicated crimes. The publisher obfuscates addresses and coordinates to the nearest 100 block and warns that some points can be substantially displaced. The app does not attempt to reconstruct locations. See the publisher's description for exclusions and the distinction between incidents and cases.

## Verification and sources

Live checks verified dataset metadata, field names, and the exact SODA3 POST response. Offline automated tests cover protocol XML, validation, pagination, unchanged/changed records, retry handling, malformed responses, and failed output checkpoint behavior. A Splunk runtime is still required to validate installation, SPL execution, and dashboard rendering.

- Dataset and publisher description: https://data.everettwa.gov/Public-Safety/Police-Incidents/f6vp-3svh
- Metadata: https://data.everettwa.gov/api/views/f6vp-3svh.json
- Query endpoint: https://data.everettwa.gov/api/v3/views/f6vp-3svh/query.json
- SODA3 request format and authentication: https://dev.socrata.com/docs/queries/
- Pagination: https://dev.socrata.com/docs/queries/page
- Splunk modular input protocol: https://help.splunk.com/en/splunk-enterprise/developing-views-and-apps-for-splunk-web/10.2/modular-inputs/set-up-streaming

This is an independent integration and is not endorsed by the City of Everett or Splunk. The package contains no bundled incident data or credentials.


## Run the packaged tests

With Python 3, run: python test_everett.py. The runner reads the adjacent app archive in memory and runs nine offline tests.


