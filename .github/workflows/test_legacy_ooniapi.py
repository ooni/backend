name: Test API
on:
  pull_request:
  workflow_dispatch:
    inputs:
      debug_enabled:
        description: 'Run the build with tmate debugging enabled'
        required: false
        default: false

jobs:
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

      - name: Notify success
        if: ${{ success() }}
        run: curl -s -d "CI API OK 😄" https://ntfy.sh/ooni-7aGhaS

      - name: Notify failure
        if: ${{ failure() }}
        run: curl -d "CI API FAIL 😞" https://ntfy.sh/ooni-7aGhaS

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
