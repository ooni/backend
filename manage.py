from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
from subprocess import Popen

from flask_script import Manager

from measurements import app

config = app.config

manager = Manager(app)
@manager.option(
    '-d', '--debug', action='store_true',
    help="Start the web server in debug mode")
@manager.option(
  '-a', '--address', default=config.get("WEBSERVER_ADDRESS"),
  help="Specify the address to which to bind the web server")
@manager.option(
  '-p', '--port', default=config.get("WEBSERVER_PORT"),
  help="Specify the port on which to run the web server")
@manager.option(
  '-w', '--workers', default=config.get("WORKERS"),
  help="Set the number of gunicorn worker threads")
def runserver(debug, address, port):
    debug = debug or config.get("DEBUG")
    if debug:
        app.run(
            host='0.0.0.0',
            port=int(port),
            threaded=True,
            debug=True)
    else:
        cmd = (
            "gunicorn "
            "-w {workers} "
            "--timeout {timeout} "
            "-b {address}:{port} "
            "--limit-request-line 0 "
            "--limit-request-field_size 0 "
            "measurements:app").format(**locals())
        print("Starting server with command: " + cmd)
        Popen(cmd, shell=True).wait()

@manager.option(
  '-t', '--target', default='/data/ooni/public/sanitised/',
  help="Specify the target directory to list")
@manager.option(
  '-f', '--file', default=None,
  help="Specify a file containing a listing of files to read from")
def updatefiles(target, file):
    from measurements.models import ReportFile
    from sqlalchemy import exists

    def add_if_exists(filepath):
        if not filepath.endswith(".json"):
            return False
        report_file = ReportFile.from_filepath(filepath)
        ret = app.db_session.query(
            exists().where(ReportFile.filename == report_file.filename)
        ).scalar()
        if ret is True:
            return False

        app.db_session.add(report_file)
        app.db_session.commit()
        return True

    if file is not None:
        with open(file) as in_file:
            for idx, filepath in enumerate(in_file):
                filepath = filepath.strip()
                if not add_if_exists(filepath):
                    continue
                if idx % 100 == 0:
                    print("Inserted %s files" % idx)
    else:
        idx = 0
        for dirname, _, filenames in os.walk(target):
            for filename in filenames:
                filepath = os.path.join(dirname, filename)
                if not add_if_exists(filepath):
                    continue
                idx += 1
                if idx % 100 == 0:
                    print("Inserted %s files" % idx)

    print("Inserted %s files" % idx)

if __name__ == "__main__":
    manager.run()
