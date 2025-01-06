# OONI bridges

**ATTENTION** Bridges were an experimental feature that is currently being researched and developed. It's implementation and deployment is not fully complete.

OONI bridges are a new design for handling the connectivity between
Probes and the backend components.

The provide a set of benefits compared to the previous architecture:

- Circumvention: the entry point for the API accepts all FDQN allowing
  mitigation for DPI-based blocking.

- Circumvention 2: bridges are designed to be deployed on both
  publicly known and \"static\" IP addresses as well as ephemeral,
  less visible addresses and/or lesser known hosting providers.

  - Bridges are stateless and could be deployed by
    [Test helper rotation](#test-helper-rotation)&thinsp;⚙.

  - Test helper VMs can run HaProxy and be used as bridges without
    impacting their ability to run test helpers as well.

- Faster connectivity: probes use the same HTTPS connection to a
  bridge for both traffic to the API and to the test helper.

- Resiliency: Test helpers are load-balanced using stateful
  connections. Anything affecting the test helpers is not going to
  impact the Probes, including: test helper rotation, CPU overload,
  network weather or datacenter outages.

The current configuration is based on [HaProxy](#haproxy)&thinsp;⚙ being run
as a load balancer in front of [Test helpers](#test-helpers)&thinsp;⚙ and
the previously configured [Nginx](#nginx)&thinsp;⚙ instance.

The configuration is stored in
<https://github.com/ooni/sysadmin/blob/master/ansible/roles/ooni-backend/templates/haproxy.cfg>

The following diagram shows the load balancing topology:

In the diagram caching for the API and proxying for various services is
still done by Nginx for legacy reasons but can be moved to HaProxy to
simplify configuration management and troubleshooting.

Bridges are deployed as:

- [ams-pg-test.ooni.org](#ams-pg-test.ooni.org)&thinsp;🖥
  <https://ams-pg-test.ooni.org:444/__haproxy_stats>

- [backend-hel.ooni.org](#backend-hel.ooni.org)&thinsp;🖥
  <https://backend-hel.ooni.org:444/__haproxy_stats>

- [bridge-greenhost.ooni.org](#bridge-greenhost.ooni.org)&thinsp;🖥
  <https://bridge-greenhost.ooni.org:444/__haproxy_stats>
