#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    entry_points={"console_scripts": ["prio=prio:main",]},
    include_package_data=True,
    install_requires=[],
    name="prio",
    py_modules=["prio"],
    python_requires=">=3.7.0",
    zip_safe=False,
)
