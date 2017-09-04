from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import pathlib

import connexion

from measurements.api import api_private_blueprint
from measurements.pages import pages_blueprint, api_docs_blueprint

HERE = os.path.abspath(os.path.dirname(__file__))

def register(app):
    from measurements import api
    connexion_resolver = connexion.resolver.Resolver()
    connexion_api = connexion.Api(
        specification=pathlib.Path(os.path.join(HERE, 'openapi/measurements.yml')),
        resolver=connexion_resolver,
        arguments=dict(),
        swagger_json=True,
        swagger_ui=True,
        swagger_path=None,
        swagger_url=None,
        resolver_error_handler=None,
        validate_responses=False,
        strict_validation=True,
        auth_all_paths=False,
        debug=True,
        validator_map=None
    )

    app.register_blueprint(api_docs_blueprint, url_prefix='/api')
    app.register_blueprint(connexion_api.blueprint)
    app.register_blueprint(api_private_blueprint, url_prefix='/api/_')
    app.register_blueprint(pages_blueprint, url_prefix='')
