#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

NAME = "analysis"
DESCRIPTION = ""

REQUIRED = []

setup(
    name=NAME,
    python_requires=">=3.7.0",
    packages=["analysis"],
    entry_points={
        "console_scripts": [
            "analysis=analysis.analysis:main",
            "rotation=rotation:main",
        ]
    },
    install_requires=REQUIRED,
    include_package_data=True,
    zip_safe=False,
    package_data={"analysis": ["views/*.tpl", "static/*"]},
)
