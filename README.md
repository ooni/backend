# ooni-pipeline-ng

The next generation OONI data pipeline.

![ooni-pipeline-ng architecture diagram](https://raw.githubusercontent.com/TheTorProject/ooni-pipeline-ng/master/docs/ooni-pipeline-ng-architecture.png)

## Setup

Edit `invoke.yaml` based on `invoke.yaml.example` to contain all the relevant
tokens.

Install also all the python requirements in `requirements.txt`.

## How to run the pipeline tasks

To run on the AWS cloud do:

```
invoke start_computer
```

If you would like to run on the current machine the task that adds things to the
postgres database you should run (after having installed the requirements in
`requirements-computer.txt`)

```
invoke add_headers_to_db
```

### More sauce

There is more, but the source is your friend, luke :)

Relevant information can be found inside of:

* `invoke.yaml` - configuration file for invoke

* `tasks.py` - all the tasks run by [invoke](http://www.pyinvoke.org/)

* `playbook.yaml` - the ansible playbook used by invoke

There is more to explore, but for the moment this is all folks.
