from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import json
import pathlib
import traceback

import werkzeug
from flask import Response, current_app, render_template

from connexion import ProblemException, FlaskApi, Resolver, problem

from measurements.api import api_private_blueprint
from measurements.pages import pages_blueprint, api_docs_blueprint

HERE = os.path.abspath(os.path.dirname(__file__))

def render_problem_exception(exception):
    response = exception.to_problem()
    return FlaskApi.get_response(response)

def render_generic_exception(exception):
    if not isinstance(exception, werkzeug.exceptions.HTTPException):
        exc_name = "{}.{}".format(type(exception).__module__,
                                  type(exception).__name__)
        exc_desc = str(exception)
        if hasattr(exception, '__traceback__'):
            current_app.logger.error(''.join(traceback.format_tb(exception.__traceback__)))
        current_app.logger.error('Unhandled error occurred, {}: {}'.format(exc_name, exc_desc))
        exception = werkzeug.exceptions.InternalServerError(
            description='An unhandled application error occurred: {}'.format(exc_name)
        )

    response = problem(title=exception.name, detail=exception.description,
                       status=exception.code)
    return FlaskApi.get_response(response)

def page_not_found(e):
    return render_template('404.html'), 404

def bad_request(e):
    return render_template('400.html', exception=e), 400

def register(app):
    from measurements import api
    connexion_resolver = Resolver()
    connexion_api = FlaskApi(
        specification=pathlib.Path(os.path.join(HERE, 'openapi/measurements.yml')),
        resolver=connexion_resolver,
        arguments=dict(),
        swagger_json=True,
        swagger_ui=False,
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

    app.register_error_handler(ProblemException, render_problem_exception)
    app.register_error_handler(Exception, render_generic_exception)

    app.errorhandler(404)(page_not_found)
    app.errorhandler(400)(bad_request)
