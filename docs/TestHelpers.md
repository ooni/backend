## Test helpers

Test helpers are hosts that provide the test helper `oohelperd` service
to probes. They are deployed by
[Test helper rotation](#test-helper-rotation)&thinsp;⚙ and tracked in
[test_helper_instances table](#test_helper_instances-table)&thinsp;⛁.

They have names and DNS entries `<number>.th.ooni.org`. See
[Test helper rotation](#test-helper-rotation)&thinsp;⚙ for details on the deployment
process.

Test helpers send metrics to [Prometheus](#prometheus)&thinsp;🔧 and send
logs to [monitoring.ooni.org](#monitoring.ooni.org)&thinsp;🖥.

See [Test helpers dashboard](#test-helpers-dashboard)&thinsp;📊 for metrics and
alarming and [Test helpers failure runbook](#test-helpers-failure-runbook)&thinsp;📒 for
troubleshooting.

The address of the test helpers are provided to the probes by the API in
[Test helpers list](#test-helpers-list)&thinsp;🐝.
`0.th.ooni.org` is treated differently from other test helpers.
