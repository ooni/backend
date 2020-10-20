from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import traceback

from flask import Response, current_app, render_template
from flask import make_response
from flask.json import jsonify

from ooniapi.private import api_private_blueprint
from ooniapi.measurements import api_msm_blueprint
from ooniapi.pages import pages_blueprint, api_docs_blueprint
from ooniapi.probe_services import probe_services_blueprint
from ooniapi.prio import prio_bp

HERE = os.path.abspath(os.path.dirname(__file__))


#def render_problem_exception(exception):
#    response = exception.to_problem()
#    return FlaskApi.get_response(response)


# def render_generic_exception(exception):
#    if not isinstance(exception, werkzeug.exceptions.HTTPException):
#        exc_name = "{}.{}".format(type(exception).__module__, type(exception).__name__)
#        exc_desc = str(exception)
#        if hasattr(exception, "__traceback__"):
#            current_app.logger.error(
#                "".join(traceback.format_tb(exception.__traceback__))
#            )
#        current_app.logger.error(
#            "Unhandled error occurred, {}: {}".format(exc_name, exc_desc)
#        )
#        exception = werkzeug.exceptions.InternalServerError(
#            description="An unhandled application error occurred: {}".format(exc_name)
#        )
#
#    response = problem(
#        title=exception.name, detail=exception.description, status=exception.code
#    )
#    return FlaskApi.get_response(response)

def render_generic_exception(exception):
    """Log a traceback and return code 500 with a simple JSON
    The CORS header is set as usual. Without this, an error could lead to browsers
    caching a response without the correct CORS header.
    """
    # TODO: render_template 500.html instead?
    current_app.logger.error(f"Exception: {exception}")
    current_app.logger.error(
        "".join(traceback.format_tb(exception.__traceback__))
    )
    try:
        return make_response(jsonify(error=str(exception)), 500)
    except:
        return make_response("unhandled error", 500)


def page_not_found(e):
    return render_template("404.html"), 404


def bad_request(e):
    return render_template("400.html", exception=e), 400

def register(app):

    #app.register_blueprint(api_docs_blueprint, url_prefix="/api")

    # Measurements API:
    app.register_blueprint(api_msm_blueprint, url_prefix="/api")
    #app.register_blueprint(connexion_api.blueprint)

    # Private API
    app.register_blueprint(api_private_blueprint, url_prefix="/api/_")

    # The index is here:
    app.register_blueprint(pages_blueprint, url_prefix="")

    # Probe services
    app.register_blueprint(probe_services_blueprint, url_prefix="")
    app.register_blueprint(prio_bp, url_prefix="")


    if "PYTEST_CURRENT_TEST" not in os.environ:

        app.register_error_handler(Exception, render_generic_exception)
        app.errorhandler(404)(page_not_found)
        app.errorhandler(400)(bad_request)
