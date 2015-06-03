from __future__ import absolute_import, print_function, unicode_literals

from invoke.config import Config
from pipeline.app import App

config = Config(runtime_path="invoke.yaml")
app = App(config)


@app.route('/sync_reports')
def sync_reports():
    pass

if __name__ == "__main__":
    app.run()
