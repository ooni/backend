# Common

Library of utility functions shared by several API services.

It is not installed as a package. Each service bundles it through a symlink
(`src/<service>/common -> ../../../../common/src/common`), so it ships as part
of each service.
