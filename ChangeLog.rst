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
