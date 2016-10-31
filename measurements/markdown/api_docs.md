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

   `probe_asn=[string]` - the Authonomous system number in the format "ASXXX"

   `test_name=[string]` - the name of the test

   `start_date=[string]` - the start date of when measurements were run (ex.
    "2016-10-20T10:30:00")

   `end_date=[string]` - the end date of when measurement were run (ex. "2016-10-20T10:30:00")

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
      "test_start_time": "[string] start time for the measurement is ISO 8601 format",
      "url": "[string] url to the download"
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
