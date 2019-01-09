# ooni-api 1.0.5 [2019-01-09]

Changes:

* Updates to charts on stats page

Added:

* Support for error logging with sentry

# ooni-api 1.0.4 [2018-06-29]

Changes:

* Minimum length for input is now 3 characters

* Validate the test_name field in list_measurements

Fixes:

* Handle failure=true | failure=false query parameters to list_measurements

* Fix a deprecation warning with SQLAlchemy

# ooni-api 1.0.3 [2017-12-13]

[note: untagged]

Fixes:

* Properly get the centrifiguation URL env variable

# ooni-api 1.0.2 [2017-12-12]

Added:

* Private API endpoints for legacy OONI Explorer

* Styled 404 and 400 pages

Changes:

* Better 500 error handling

* Increase the query timeout threshold

Fixed:

* Backward compatibility with old report links

# ooni-measurements 1.0.1 [2017-09-29]

Changes:

* Remove in-process flask-cache

# ooni-measurements 1.0.0 [2017-09-29]

Added:

* API endpoints for listing and filtering anomalous measurements

* API endpoints for downloading full reports

Changed:

* Reverse sorting in `by_date` view and hide measurements from time travellers

* Better API documentation thanks to redoc based on OpenAPI 2.0

* Improve request validation thanks to connexion base on OpenAPI

* Oonify the UI

* Better testing

# ooni-measurements 1.0.0-rc.4 [2017-09-29]

Fixes:
* Critical bug in input handling

# ooni-measurements 1.0.0-rc.3 [2017-09-29]

Changes:
* Reverse sorting in `by_date` view and hide measurements from time travellers

* Improve the UI

* Update copy

# ooni-measurements 1.0.0-rc.2 [2017-09-28]

Fixes:
* API filtering anomaly,confirmed,failure

# ooni-measurements 1.0.0-rc.1 [2017-09-28]

Added:

* API endpoints for listing and filtering anomalous measurements

* API endpoints for downloading full reports

Changed:

* Better API documentation based on OpenAPI 2.0

* Improve request validation thanks to OpenAPI

* Oonify the UI

* Better testing

# ooni-measurements 1.0.0-beta.3 [2017-07-18]

* Add version API

* Fixes to the build system

# ooni-measurements 1.0.0-beta.2 [2017-07-18]

* Use as backend the new data processing pipeline

* Add API endpoint for searching measurements

* Add API endpoint for fetching a single measurement

