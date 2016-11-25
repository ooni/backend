from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from measurements.blueprints.api import api_blueprint, api_docs_blueprint
from measurements.blueprints.api import api_private_blueprint
from measurements.blueprints.pages import pages_blueprint

def register(app):
    app.register_blueprint(api_docs_blueprint, url_prefix='/api')
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')
    app.register_blueprint(api_private_blueprint, url_prefix='/api/_')
    app.register_blueprint(pages_blueprint, url_prefix='')
