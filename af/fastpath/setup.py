#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

# Package meta-data.
NAME = 'fastpath'
DESCRIPTION = ''

# What packages are required for this module to be executed?
REQUIRED = [
]

setup(
    name=NAME,
    python_requires='>=3.6.0',
    packages=["fastpath", "fastpath.tests"],
    entry_points={
        'console_scripts': ['fastpath=fastpath.core:main'],
    },
    install_requires=REQUIRED,
    include_package_data=True,
    zip_safe=False
)
