# OONI measurements

Source for https://measurements.ooni.torproject.org/

## Requirements

This software is tested on python 3.5.

To install the required dependencies run:

```
pip install -r requirements.txt
```

Note: psycopg2 is only a requirement if you plan on using postgres.

## Usage

To start the development web server you can do:

```
python manage.py runserver -d
```

To start it using gunicorn you can do:

```
python manager.py runserver
```

You can fill the database with some report files by creating a listing of
report files and importing this listing from a text file with:

```
python updatefiles -f listing.txt
```

An example of `listing.txt` is:

```
/data/ooni/public/sanitised/2016-02-02/20160201T155514Z-US-AS16652-http_requests-37kq70ePFVqe1QM0MxpAv9X39JaQ8aytmGfYHc7a76jDEYrumzaXFxkSCtQPLBzF-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160201T054908Z-DE-AS31334-http_invalid_request_line-IlJzJoPd0P0PxpRY992v9poCauYe2eMM6vFH6RB5xlLtkOeJ5xECHK52uVtq3KIn-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160131T093413Z-FR-AS12322-http_requests-BEC2fZmaePcalA7Er5iFYtRUTkZquiHEW17lnyfORUmeYpdwYWmwlNxQ01GVLKJf-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160202T000520Z-US-AS7922-http_invalid_request_line-KJlUKWaOuumi1OpQIWw9VGF5ggOJsxgKsyMTttXQO87JVH5VfDT9zhYOqL9nJfhr-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160201T100539Z-PT-AS12353-http_requests-ShPyqdhPZpRRQoSdAkDG96UsmedciLxg4idz3dabMYLuBSPUL2gsplbu35C0oOZQ-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160201T214444Z-US-AS36351-http_requests-5kK0zb2PkfXBItsv8o7d3V46FM2hT760oFazAr3jxwJRGNntPwtjj02JSm4iLobb-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160201T060728Z-CH-AS41715-dns_consistency-Sql4iPUJpmO0t0Cs2pqJmVJUpFlI4ganPdBX67vqiMjMf0yoe5IEwuwvXaHiTaDk-0.1.0-probe.json
/data/ooni/public/sanitised/2016-02-02/20160201T062514Z-GB-AS786-http_invalid_request_line-ohiV8fWGE6IAmJ5YSOpWR5wTrzqHLZMfByhyQXCzxrReOs5gDEOipw1BVQNlabJj-0.1.0-probe.json
```

## Configuration

You should create a configuration file called `measurements.cfg` and set
the environment variable `MEASUREMENT_CONFIG` to point to it.

In particular you will want to set the following values in it:

```
SQLALCHEMY_DATABASE_URI = 'postgresql://USERNAME:PASSWORD@HOSTNAME/DATABASE'
WEBSERVER_ADDRESS = "0.0.0.0"
WEBSERVER_PORT = 3001
BASE_URL = 'https://measurements.ooni.torproject.org/'
REPORTS_DIRECTORY = '/data/ooni/public/sanitised/'
```

Be careful that the configuration file is actually loaded as a python file.

## Deployment notes

The database for the measurement files needs to be kept up to date as such it's
recommended that the following things are done:

On first run you ensure the database is initialized with the correct
report files.
You can do so in the following way:
```
python manage.py updatefiles -t TARGET_DIR
```
Where `TARGET_DIR` is generally going to be the same path as
`REPORTS_DIRECTORY` in the configuration file.

Then in the cronjob that runs periodically to sync reports with the
measurements server you should generate a listing of all the new reports file
(it's sufficient to put their filepaths inside of a text file) and then
run:

```
python manage.py updatefiles -f update-file.txt
```

`updatefiles` will check to see if the files are already in the database, but
it's much more performant to not run the update with files that are already in
the database.

It's recommended to run this in production using gunicorn.

Check out the [gunicorn deployment
docs](http://docs.gunicorn.org/en/stable/deploy.html) for using gunicorn in
production.
