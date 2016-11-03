import os
import click
from flask import current_app
from flask.cli import FlaskGroup, with_appcontext

from measurements.app import create_app

cli = FlaskGroup(create_app=create_app)


from measurements.models import ReportFile
from sqlalchemy import exists


def add_if_exists(app, filepath):
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



@cli.command()
@click.option('--file', help="Read filenames from file listing")
@click.option('--target', help="Get from directory listing")
@with_appcontext
def updatefiles(file=None, target=None):
    if file is not None:
        with open(file) as in_file:
            for idx, filepath in enumerate(in_file):
                filepath = filepath.strip()
                if not add_if_exists(filepath):
                    continue
                if idx % 100 == 0:
                    click.echo("Inserted %s files" % idx)
    elif target is not None:
        idx = 0
        for dirname, _, filenames in os.walk(target):
            for filename in filenames:
                filepath = os.path.join(dirname, filename)
                if not add_if_exists(filepath):
                    continue
                idx += 1
                if idx % 100 == 0:
                    click.echo("Inserted %s files" % idx)
    else:
        raise click.UsageError("Must specify either --file or --target")

@cli.command()
@with_appcontext
def initdb(test=False):
    from measurements.database import create_tables
    current_app.db.drop_all()
    create_tables(current_app)


@cli.command()
@with_appcontext
def shell():
    """Run a Python shell in the app context."""

    try:
        import IPython
    except ImportError:
        IPython = None

    if IPython is not None:
        IPython.embed(banner1='', user_ns=current_app.make_shell_context())
    else:
        import code

        code.interact(banner='', local=current_app.make_shell_context())


if __name__ == '__main__':
    cli()
