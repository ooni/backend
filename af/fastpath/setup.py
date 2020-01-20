#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

NAME = "fastpath"
DESCRIPTION = ""

REQUIRED = []

setup(
    name=NAME,
    python_requires=">=3.6.0",
    packages=["fastpath", "fastpath.tests"],
    entry_points={"console_scripts": [
        "fastpath=fastpath.core:main",
        "domain_input_updater=fastpath.domain_input:main",
    ]},
    install_requires=REQUIRED,
    include_package_data=True,
    zip_safe=False,
    package_data={'fastpath': ['views/*.tpl', 'static/*']},
)
