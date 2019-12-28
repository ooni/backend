# OONI Measurements API

This is the documentation for version 1 of the OONI measurements API.

All the API endpoints start with the URL `/api/v1/`.

# Pagination

Some API endpoints support pagination. In these cases the response will have
 the following structure:

```
{
    "metadata": {
        "offset": "an integer specifying the current offset into the data",
        "limit": "an integer specifying how many results should be presented",
        "count": "an integer expressing the total number of items",
        "pages": "the number of pages, or the number of requests you will"
                 "have to do with the current value of limit to obtain the"
                 "full set of records",
        "next_url": "the url to be used to fetch the next set of items"
    },
    "results": [
        "a list containing generally dictionaries of the result in question"
    ]
}
```

## Search files

Returns a listing of the files matching the given search criteria.

This API endpoints supports pagination and will by default return 100
results per response.

### Request

**URL**

  /api/v1/files

**Method**

  `GET`

**URL Params**

   `probe_cc=[string]` - the two letter country code.

   `probe_asn=[string]` - the
   [Autonomous system](https://en.wikipedia.org/wiki/Autonomous_system_(Internet))
   number in the format "ASXXX"

   `test_name=[string]` - the name of the test

   `since=[string]` - the start date of when measurements were run (ex.
    "2016-10-20T10:30:00")

   `until=[string]` - the end date of when measurement were run (ex.
   "2016-10-20T10:30:00")

   `since_index=[integer]` - return results only strictly greater than the
   provided index.

   `order_by=[string]` - by which key the results should be ordered by (default: test_start_time)

   `order=[string] ("desc", "asc")` - if the order should be ascending or descending.

   `offset=[integer]` - offset into the result set (default: 0)

   `limit=[integer]` - number of records to return (default: 100)

**Data Params**

  None

### Response

#### Success

**Code:** 200 <br />
**Content:**

```
{
  "metadata": {
    "count": "[integer] total number of rows",
    "limit": "[integer] current limit to returned results",
    "next_url": "[string] URL pointing to next page of results or none if no more pages are available",
    "offset": "[integer] the current offset into the result set",
    "pages": "[integer] total number of pages"
    "current_page": "[integer] current page"
  },
  "results": [
    {
      "probe_asn": "[string] the Autonomous system number of the result",
      "probe_cc": "[string] the country code of the result",
      "test_name": "[string] the name of the test that was run",
      "index": "[integer] the index of this result (useful when using since_index)",
      "test_start_time": "[string] start time for the measurement is ISO 8601 format",
      "download_url": "[string] url to the download. Note: if the download URL ends with '.gz' it should be considered compressed with gzip."
    }
  ]
}
```

#### Error

**Code:** 400 BAD REQUEST <br />
**Content:**

```
{
    "error_code": 400,
    "error_message": "Some error message"
}
```

## Search measurements

Returns the IDs for the measurements that match the specified search
criteria.

### Request

**URL**

  /api/v1/measurements

**Method**

  `GET`

**URL Params**

   `report_id=[string]` - the report ID of the requested measurement

   `input=[string]` - the input for the requested measurement

   `probe_cc=[string]` - the two letter country code.

   `probe_asn=[string]` - the
   [Autonomous system](https://en.wikipedia.org/wiki/Autonomous_system_(Internet))
   number in the format "ASXXX"

   `test_name=[string]` - the name of the test

   `since=[string]` - the start date of when measurements were run (ex.
    "2016-10-20T10:30:00")

   `until=[string]` - the end date of when measurement were run (ex.
   "2016-10-20T10:30:00")

   `order_by=[string]` - by which key the results should be ordered by (default: test_start_time)

   `order=[string] ("desc", "asc")` - if the order should be ascending or descending.

   `offset=[integer]` - offset into the result set (default: 0)

   `limit=[integer]` - number of records to return (default: 100)

**Data Params**

  None

### Response

#### Success

**Code:** 200 <br />
**Content:**

```
{
  "metadata": {
    "count": "[integer] total number of rows",
    "limit": "[integer] current limit to returned results",
    "next_url": "[string] URL pointing to next page of results or none if no more pages are available",
    "offset": "[integer] the current offset into the result set",
    "pages": "[integer] total number of pages"
    "current_page": "[integer] current page"
  },
  "results": [
    {
      "measurement_id": "[string] the ID of the measurement returned",
      "measurement_url": "[string] link to fetch the measurement (probably in the form of $BASEURL/api/v1/measurement/<ID>)"
    }
  ]
}
```

#### Error

**Code:** 400 BAD REQUEST <br />
**Content:**

```
{
    "error_code": 400,
    "error_message": "Some error message"
}
```


## Fetch measurement

Returns the specified measurement.

### Request

**URL**

  `/api/v1/measurement/<measurement_id>`

**Method**

  `GET`

### Response

#### Success

**Code:** 200 <br />
**Content:**

```
{
  "id": "XXXX",
  "data": {
    "probe_cc": "XX",
    "probe_asn": "XX",
    ...
    "test_keys": {},
  }
}
```

#### Error

**Code:** 400 BAD REQUEST <br />
**Content:**

```
{
    "error_code": 400,
    "error_message": "Some error message"
}
```
