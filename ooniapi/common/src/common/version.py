from importlib.metadata import version as importlib_version
from importlib.resources import files as importlib_files
from typing import Optional

pkg_name = "oonidataapi"


def get_pkg_version(pkg_name) -> Optional[str]:
    try:
        return importlib_version(pkg_name)
    except:
        # This happens when we are not installed, for example in development
        return None


def get_build_label(pkg_name) -> Optional[str]:
    try:
        with importlib_files(pkg_name).joinpath("BUILD_LABEL").open("r") as in_file:
            return in_file.read().strip()
    except:
        return None
