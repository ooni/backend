import os
import click
from flask import current_app
from flask.cli import FlaskGroup, with_appcontext

from sqlalchemy import exists, select

from measurements.app import create_app
from measurements.models import ReportFile
from measurements.filestore import list_files

cli = FlaskGroup(create_app=create_app)

def add_to_db(app, filepath, index, no_check=False):
    if not filepath.endswith(".json"):
        return False
    report_file = ReportFile.from_filepath(filepath, index)

    if no_check is False:
        ret = app.db_session.query(
            exists().where(ReportFile.filename == report_file.filename)
        ).scalar()
        if ret is True:
            return False

    app.db_session.add(report_file)
    return True


@cli.command()
@click.option('--file', help="Read filenames from file listing")
@click.option('--target', help="Get from directory listing")
@click.option('--no-check', is_flag=True,
              help="Don't check if the file is in the DB already")
@with_appcontext
def updatefiles(file=None, target=None, no_check=False):
    if no_check == True:
        click.echo("Skipping check")

    if target is None:
        target = current_app.config['REPORTS_DIR']

    most_recent_index = 0
    most_recent = current_app.db_session.query(ReportFile)\
                            .order_by(ReportFile.idx.desc())\
                            .first()
    if most_recent is not None:
        most_recent_index = most_recent.index
    if file is not None:
        with open(file) as in_file:
            for idx, filepath in enumerate(in_file):
                filepath = filepath.strip()
                index = most_recent_index + idx
                if not add_to_db(current_app, filepath, index, no_check):
                    continue
                if idx % 100 == 0:
                    click.echo("Inserted %s files" % idx)
                    current_app.db_session.commit()
    elif target is not None:
        idx = 0
        for filepath in list_files(current_app, target):
            index = most_recent_index + idx
            if not add_to_db(current_app, filepath, index, no_check):
                continue
            idx += 1
            if idx % 100 == 0:
                click.echo("Inserted %s files" % idx)
                current_app.db_session.commit()
    else:
        raise click.UsageError("Must specify either --file or --target")

    current_app.db_session.commit()

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
