## GitHub CI workflows

**ATTENTION** this section needs to be updated to include the fact we are now deploying in both AWS codepipeline for things that should be deployed on ECS, while we keep github CI for those which have not yet been ported over.

There are 5 main workflows that a run by GitHub Actions when new pull
requests are created or updated the backend repository.

They are configured using YAML files in the repository, plus secret keys
and other variables that can be edited on
<https://github.com/ooni/backend/settings/secrets/actions>

The workflow files are:

- .github/workflows/build_deb_packages.yml

- .github/workflows/docgen.yaml

- .github/workflows/mypy.yml

- .github/workflows/test_fastpath.yaml

- .github/workflows/test_new_api.yml

> **warning**
> the workflows handle sensitive credentials. GitHub provides security
> features to prevent 3rd party contributors from running CI actions
> through pull requests that might expose credentials.

### Debian package build and publish

#### Quick checklist

You would like to make a new release of a software that follows the debops CI procedure? Read ahead.

1. Write your code and push it to a branch
2. Edit the `debian/changelog` file to add an entry like follows (eg. `backend/api/debian/changelog`)

```
ooni-api (1.0.89) unstable; urgency=medium

  * Some changes

 -- OONITarian <contact@ooni.org>  Wed, 21 Feb 2024 16:24:18 +0100
```

**Attention** Be sure to update the timestamp and the version string to a newer
date, otherwise the package update may not be triggered.

3. Commit your changelog entry and wait for CI to build
4. Login to the host where you would like to test deploy it and list the available packages

```
sudo apt-get update
apt-cache madison ooni-api
```

5. From the list look for the version number of the package you would like to test. Be sure to first test deploy it on a staging or testing host.

```
  ooni-api | 1.0.89~pr806-275 | https://ooni-internal-deb.s3.eu-central-1.amazonaws.com unstable/main amd64 Packages
  ooni-api | 1.0.89~pr792-273 | https://ooni-internal-deb.s3.eu-central-1.amazonaws.com unstable/main amd64 Packages
```

6. You can then install the desired version by running:

```
sudo apt-get install ooni-api=1.0.89~pr806-275
```

7. Do some validation to ensure the new version is working as intended

Here is a sample python snippet:

```
import requests
r = requests.post(
    "https://backend-hel.ooni.org/api/v1/check-in",
    headers={
        #"X-Real-IP": '34.34.19.34',
        "X-Forwarded-For": '1.34.1.1'
    },
    json={
        'probe_cc': 'IT',
        'probe_asn': 'AS8220',
        'platform': 'desktop',
        'software_name': 'notooniprobe',
        'software_version': '1.0.0',
        'on_wifi': False,
        'charging': False,
        'run_type': 'manual',
        'web_connectivity': {
            'category_codes': []
        }
    }
)
```

8. Once you are happy with the new version, you can push it to production. Merge
   the PR and do the same you did now for production.

#### More information

Builds one or more .deb files from the backend repository and uploads
them to Debian archives on S3.

The configuration file is:

    .github/workflows/build_deb_packages.yml

The workflow installs the required dependencies as Debian packages and
then fetches the [debops-ci tool](#debops-ci-tool)&thinsp;🔧 from the [sysadmin repository](https://github.com/ooni/sysadmin/tree/master/tools)

#### debops-ci tool

A Python script that automates package builds and CI/CD workflows:

- Detects `debian/` directories in the current repository. It inspects
  file changes tracked by git to identify which projects are being
  modified.

- Bumps up version numbers according to the [package versioning](#package-versioning)&thinsp;💡 criteria described below.

- Builds Debian packages as needed.

- Generates a Debian archive on S3. Uploads .deb files into it to make
  them available for deployment.

The script has been designed to address the following requirements:

- Remove dependencies from 3rd party services that might become expensive or be shut down.
- Serverless: do not require a dedicated CI/CD server
- Stateless: allow the script to run in CI and on developer desktops without requiring a local database, cache etc.
- Compatible: generate a package archive that can be used by external users to install ooniprobe on their hosts using standard tooling.
- CI-friendly: minimize the amount of data that needs to be deployed on servers to update a backend component or probe.
- Reproducible: given the same sources the generated output should be virtually identical across different systems. I.e. it should not depend on other software installed locally.

It is used in the CI workflow as:

```bash
./debops-ci --show-commands ci --bucket-name ooni-internal-deb
```

##### debops-ci details

The tool requires the following environment variables for automated ci
runs:

- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in order to write to
  S3 buckets.

- `DEB_GPG_KEY` or `DEB_GPG_KEY_BASE64` to GPG-sign packages. The
  first variable can contain a PEM-encoded private key, while the
  second is base64-encoded.

Other configuration parameters can be set from the command line. See the
`-h` CLI option:

    usage:
    Version 2023-10-20.1

    Builds deb packages and uploads them to S3-compatible storage.
    Works locally and on GitHub Actions and CircleCI
    Detects which package[s] need to be built.
    Support "release" and PR/testing archives.

    scan              - scan the current repository for packages to be built
    build             - locate and build packages
    upload <filename> - upload one package to S3
    ci                - detect CircleCI PRs, build and upload packages

    Features:
     - Implement CI/CD workflow using package archives
     - Support adding packages to an existing S3 archive without requiring a
       local mirror
     - Support multiple packages in the same git repository
     - GPG signing
     - Support multiple architectures
     - Update changelogs automatically
     - Easy to debug
     - Phased updates (rolling deployments)

    positional arguments:
      {upload,scan,ci,build}

    options:
      -h, --help            show this help message and exit
      --bucket-name BUCKET_NAME
                            S3 bucket name
      --distro DISTRO       Debian distribution name
      --origin ORIGIN       Debian Origin name
      --arch ARCH           Debian architecture name
      --gpg-key-fp GPG_KEY_FP
                            GPG key fingerprint
      --show-commands       Show shell commands

When running with the `ci` or `upload` commands, the tool creates the
required directories and files on S3 to publish an archive suitable for
APT. It uploads any newly built package and then appends the package
description to the `Packages` file. It then generates a new `InRelease`
file and adds a GPG signature at the bottom of the file.

See
[Packages](https://ooni-internal-deb.s3.eu-central-1.amazonaws.com/dists/unstable/main/binary-amd64/Packages)
and
[InRelease](https://ooni-internal-deb.s3.eu-central-1.amazonaws.com/dists/unstable/InRelease)
as examples.

The current OONI package archives are:

- <https://ooni-internal-deb.s3.eu-central-1.amazonaws.com/> - for
  internal use

- <http://deb.ooni.org/> also available as <https://deb.ooni.org/> -
  for publicly available packages

Documentation on how to use the public archive:
<https://ooni.org/install/cli/ubuntu-debian>

The tool can also be used manually e.g. for debugging using actions
`scan`, `build` and `upload`.

Unlike other CI/CD tools, debops-ci is designed to be stateless in order
to run in ephemeral CI worker containers. Due to limitations around
transactional file uploads, a pair of lockfiles are used, named
`.debrepos3.lock` and `.debrepos3.nolock`

> **note**
> If the github actions CI workflow for package build is restarted
> manually (that is, without git-pushing a new commit) debops-ci will
> refuse to overwrite the .deb package already present on S3. This is
> expected.

#### Package versioning

The CI workflows builds Debian packages with the following versioning
scheme:

    <semver_version>~pr<pull_request_number>-<build_number>

For example:

    1.0.79~pr751-194

This format has the benefits of:

- Providing a user-configured [semantic versioning](https://semver.org/) part.

- Automatically inserting a pull request number. This prevents version
  conflicts in case the first component has not been updated when
  opening a new pull request.

- Automatically inserting an incremental build number. This allows
  incremental deployments of commits on testbeds.

Once a package at a given version is uploaded the CI tool will refuse to
overwrite it in future CI runs. This is meant to prevent changing the
contents of published packages.

It is recommended to update the `debian/changelog` file in the first
commit of each new pull request by adding a new semver number and a
short changelog. This helps keeping track of what changes are being
deployed on test, integration and production servers.

Sometimes multiple pull requests for the same package are open at the
same time and are rebased or merged in an order that is different from
the pull request number. In this case manually bumping up the semver
number after each rebase is beneficial to ensure that the rollout is
done incrementally.

For example:

- Pull request 751 builds a package versioned 1.0.79\~pr751-14. The
  package is deployed on the testbed.

- Pull request 752, opened later, is rebased on top of 751 and builds
  a package versioned 1.0.80\~pr752-51. The package is deployed on the
  testbed.

- The need to reorder the two PRs arises. PR 751 is now rebased on top
  of 752. The changelog file is manually updated to version 1.0.81 The
  CI now generates 1.0.81\~pr751-43 and the packa

See the subchapter on the [The deployer tool](#the-deployer-tool)&thinsp;🔧

### Code documentation generation

The configuration lives at:

    .github/workflows/docgen.yaml

The workflow runs `./build_docs.py` to generate documentation from the
Python files. It is a script that extracts MarkDown and AsciiDoc
docstrings from the codebase in the backend repository. It also supports
graphviz diagrams using kroki.io It generates a set of HTML files that
are published as GitHub pages as part of the CI workflow.

The outputs is lives at <https://ooni.github.io/backend/>

At the time of writing it is superseded by the present document.

### Mypy

The configuration lives at:

    .github/workflows/mypy.yml

It runs mypy to check Python typing and makes the CI run fail if errors
are detected.

### Fastpath test

The configuration lives at:

    .github/workflows/test_fastpath.yaml

Runs the following unit and functional tests against the fastpath:

    fastpath/tests/test_functional.py
    fastpath/tests/test_functional_nodb.py
    fastpath/tests/test_unit.py

These are not end-to-end tests for the backend e.g. the API is not being
tested.

The CI action creates a dedicated container and installs the required
dependencies as Debian packages. It provides a code coverage report in
HTML format.

### API end-to-end test

The configuration lives at:

    .github/workflows/test_new_api.yml

This CI action performs the most comprehensive test of the backed. In
sequence:

- Creates a dedicated container and installs the required dependencies
  as Debian packages.

- It starts a ClickHouse container

- Creates the required database tables, see
  <https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/tests/integ/clickhouse_1_schema.sql>

- Initializes the database tables with test data, see
  <https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/tests/integ/clickhouse_2_fixtures.sql>

- Runs the fastpath against data from a bucket on S3 in order to
  populate the `fastpath` table with real data. The measurements come
  from both:

  - A fixed time range in the past

  - Recent data

- It runs unit, functional and integration tests against the API.
  Integration tests require the API to run queries against multiple
  tables in ClickHouse.

> **important**
> the presence of recent data makes the content of the `fastpath` database
> table non deterministic between CI runs. This is necessary to perform
> integration tests against API entry points that need fresh data. To
> prevent flaky CI runs write integration tests with to handle variable
> data. E.g. use broad thresholds like asserting that the number of
> measurements collected in a day is more than 1.

> **note**
> prefer unit tests where possible

> **note**
> To implement precise functional tests, mock out the database.
