from __future__ import with_statement
from __future__ import absolute_import

import setuptools

import versioneer
versioneer.versionfile_source = 'oonib/_version.py'
versioneer.versionfile_build = 'oonib/_version.py'
# tag format must be v1.2.3
versioneer.tag_prefix = 'v'
# build unpacks into 'oonib-1.2.3'
versioneer.parentdir_prefix = 'oonib'


def get_requirements():
    with open('requirements.txt', 'r') as f:
        requirements = f.read().splitlines()

    # For urls such as https://hg.secdev.org/scapy/archive/tip.zip#egg=scapy in
    # requirements.txt we need to add the package name to install_requires and
    # the entire url to dependency_links. That way setuptools will be able to
    # satisfy the dependency using that url (as long as it is in standard sdist
    # format, a single .py file or an egg).
    pypi_packages = []
    dependency_links = []
    for package_desc in requirements:
        if package_desc.startswith("#") or package_desc.startswith("-i"):
            continue
        if '#egg=' in package_desc:
            dependency_links.append(package_desc)
            pypi_packages.append(package_desc.split('#egg=')[-1])
        else:
            pypi_packages.append(package_desc)

    return pypi_packages, dependency_links

install_requires, dependency_links = get_requirements()

setuptools.setup(
    name="oonib",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="The Tor Project, Inc",
    url="https://ooni.torproject.org",
    license="BSD",
    description="""\
Backend network test helper and report collector for the OONI \
censorship-detection framework""",
    scripts=["bin/oonib"],
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    dependency_links=dependency_links,
)
