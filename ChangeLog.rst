ChangeLog
=========

1.3.6 (Mon, 25 Mar 2019)
------------------------

* Implement the OONI bouncer v2.0.0 spec

1.3.5 (Thu, 21 Feb 2019)
------------------------

* Disable collecting reports from ooniprobe-android 2.0.0

1.3.4 (Tue, 26 Sep 2017)
------------------------

* fix(report/handlers): accept more semver versions (#111)

* README.rst: also apt-get install libdumbnet-dev (#108)

1.3.3 (Thu, 2 Feb 2017)
-------------------------
* Add support for allows clients to send HTTP request headers

* Ignore redirects to localhost

1.3.2 (Mon, 30 Jan 2017)
-------------------------

* Fix backward compatibility with legacy clients when stripping invalid tcp_connect fields

1.3.1 (Thu, 26 Jan 2017)
-------------------------

* Add support for intermediate certificate (#95)

* Add support for specifying collector-alternate field (#92)

* Move state of reports to filesystem (#91)

* Strip invalid tcp_connect fields in web_connectivity test helper

1.3.0 (Mon, 30 May 2016)
-------------------------

* Add web connectivity test helper

* Add support for HTTPS collectors and bouncers

* Fix problems with priviledge shedding and daemonisation
  https://github.com/TheTorProject/ooni-backend/issues/65

1.2.0 (Wed, 27 Apr 2016)
-------------------------

* Add support for receiving JSON based reports

1.1.4 (Wed, 1 Oct 2014)
-----------------------

* Fix bug that lead test helpers to not being started

1.1.3 (Mon, 29 Sep 2014)
-----------------------

* Add support for specifying the report archive path from config file

* Write tor notice level logs to file

1.1.2 (Wed, 3 Sep 2014)
-----------------------

* Fix bug that lead oonib not running when a test helper was disabled.

1.1.1 (Wed, 3 Sep 2014)
-----------------------

* Fix daemonize API breakage when upgrading from Twisted <= 13.1 to >= 13.2
  https://trac.torproject.org/projects/tor/ticket/12644

* Make it possible to use a reports directory on a different volume than the
  archive directory.

1.1.0 (Tue, 2 Sep 2014)
-----------------------

* Make changes to the bouncer API to make it aware of the policy of collectors.

* Improve the bouncer API to make it more RESTful.

* Add test helper that can be used to discover the DNS resolver being used by
  the probe.

* Code coverage and unittesting improvements.

* Fix compatibility with latest txtorcon versions.

1.0.2 (Wed, 21 May 2014)
------------------------

Various code improvements and fixes following the Least Authority release
engineering work.

1.0.0 (Wed, 26 Mar 2014)
------------------------

First public release of oonibackend

* Implements collector for receiver reports.

* Implements HTTPReturnJSONHeaders HTTP helper

* Implement DNS resolver helper

* Implements TCP echo helper

* Implements bouncer for directing directing probes to an adequate collector
  and test helper.
