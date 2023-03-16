import os
from flask import current_app
from flask.cli import FlaskGroup, with_appcontext

from sqlalchemy import exists, select

from ooniapi.app import create_app

cli = FlaskGroup(create_app=create_app)


@cli.command()
@with_appcontext
def shell():
    """Run a Python shell in the app context."""

    try:
        import IPython
    except ImportError:
        IPython = None

    if IPython is not None:
        IPython.embed(banner1="", user_ns=current_app.make_shell_context())
    else:
        import code

        code.interact(banner="", local=current_app.make_shell_context())


@cli.command()
@with_appcontext
def create_tables():
    from ooniapi.database import Base
    from ooniapi import models

    Base.metadata.create_all(bind=current_app.db_engine)


if __name__ == "__main__":
    cli()
