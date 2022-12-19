#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

NAME = "analysis"

setup(
    name=NAME,
    python_requires=">=3.7.0",
    py_modules=["rotation"],
    packages=["analysis"],
    entry_points={
        "console_scripts": [
            "analysis=analysis.analysis:main",
            "ooni-db-backup=ooni_db_backup:main",
            "rotation=rotation:main",
        ]
    },
    scripts=["analysis/clickhouse_feeder.py"],
    include_package_data=True,
    zip_safe=False,
    package_data={"analysis": ["views/*.tpl", "static/*"]},
)
