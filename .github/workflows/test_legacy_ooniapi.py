name: Test Legacy API
on:
  push:
  workflow_dispatch:
    inputs:
      debug_enabled:
        description: 'Run the build with tmate debugging enabled'
        required: false
        default: false

jobs:
  mypy:
    runs-on: ubuntu-latest
    container: debian:11
    steps:
      - name: Check out repository code
        uses: actions/checkout@v2

      - name: Setup APT
        run: |
          apt-get update
          apt-get install --no-install-recommends -y ca-certificates gnupg
          echo "deb http://deb-ci.ooni.org unstable main" >> /etc/apt/sources.list
          apt-key adv --verbose --keyserver hkp://keyserver.ubuntu.com --recv-keys "B5A08F01796E7F521861B449372D1FF271F2DD50"

      - name: Install dependencies
        run: |
          apt-get update
          apt-get install --no-install-recommends -qy mypy

      - name: Run tests
        # see the mypy.ini file
        run: cd api && mypy **/*.py

  integration_test:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository code
        uses: actions/checkout@v2

      - name: Setup tmate session
        uses: mxschmitt/action-tmate@v3
        if: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.debug_enabled }}
        with:
          limit-access-to-actor: true

      - name: Build docker image
        run: cd api && make build

      - name: Check apispec.json
        run: cd api && tools/check_apispec_changes

      - name: Setup database fixtures and run fastpath to populate the DB
        run: cd api && make initdb

      - name: Run all tests
        run: cd api && T="--show-capture=no -s -vv" make tests
        #run: T="--show-capture=no -s -vv --junitxml=pytest.xml" make tests

      #- name: debug docker
      #  if: always()
      #  run: docker ps -a

      # - run: find / -name pytest.xml 2> /dev/null
      #   if: success() || failure() # run even if previous step failed

      # - name: Test report
      #   uses: dorny/test-reporter@v1
      #   if: success() || failure() # run even if previous step failed
      #   with:
      #     name: Test report
      #     path: '/home/runner/work/api/api/newapi/pytest.xml'
      #     reporter: java-junit     # compatible with pytest --junitxml
