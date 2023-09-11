#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

DESCRIPTION = ""

REQUIRED = []

    #entry_points={"console_scripts": ["oonistun:main",]},
setup(
    name="oonistun",
    python_requires=">=3.6.0",
    install_requires=REQUIRED,
    include_package_data=True,
    zip_safe=False,
)
