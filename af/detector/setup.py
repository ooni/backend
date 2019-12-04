#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

NAME = "detector"
DESCRIPTION = ""

REQUIRED = []

setup(
    name=NAME,
    python_requires=">=3.6.0",
    packages=["detector", "detector.tests"],
    entry_points={"console_scripts": ["detector=detector.detector:main",]},
    install_requires=REQUIRED,
    include_package_data=True,
    zip_safe=False,
    package_data={"detector": ["views/*.tpl", "static/*", "data/country-list.json"]},
)
