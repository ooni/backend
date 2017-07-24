import os
from flask import Blueprint, render_template, current_app, request

from measurements.config import BASE_DIR

# prefix: /api
api_docs_blueprint = Blueprint('api_docs', 'measurements')

@api_docs_blueprint.route('/', methods=["GET"])
def api_docs():
    with open(os.path.join(BASE_DIR, 'markdown', 'api_docs.md')) as in_file:
        docs_text = in_file.read()
    return render_template('api.html', docs_text=docs_text)
