from __future__ import with_statement

import os
import sys
from oonib import __version__
from setuptools import setup, find_packages
from setuptools.command import install


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

usr_share_path = '/usr/share'
var_path = '/var'
etc_path = '/etc'
# If this is true then it means we are in a virtualenv
# therefore we should not place our data files inside /usr/share/ooni, but
# place them inside the virtual env system prefix.
if hasattr(sys, 'real_prefix'):
        usr_share_path = os.path.abspath(os.path.join(sys.prefix, 'share'))
        var_path = os.path.abspath(os.path.join(sys.prefix, 'var'))
        etc_path = os.path.abspath(os.path.join(sys.prefix, 'etc'))

data_dir = os.path.join(usr_share_path, 'ooni', 'backend')
spool_dir = os.path.join(var_path, 'spool', 'ooni', 'backend')
var_dir = os.path.join(var_path, 'spool', 'ooni', 'backend')

def install_config_file(self):
    print "Writing the default configuration file to %s" % etc_path
    if not os.path.isdir(etc_path):
        os.makedirs(etc_path)
    import yaml
    example_config = yaml.safe_load(open('oonib.conf.example'))
    example_config['main']['report_dir'] = os.path.join(spool_dir, 'reports')
    example_config['main']['archive_dir'] = os.path.join(spool_dir, 'archive')
    example_config['main']['deck_dir'] = os.path.join(data_dir, 'decks')
    example_config['main']['input_dir'] = os.path.join(data_dir, 'inputs')
    example_config['main']['policy_file'] = os.path.join(var_dir, 'policy.yaml')
    example_config['main']['bouncer_file'] = os.path.join(var_dir, 'bouncer.yaml')
    example_config['main']['tor_datadir'] = os.path.join(var_dir, 'tor')

    with open(os.path.join(etc_path, 'oonibackend.conf'), 'w+') as fw:
        yaml.dump(example_config, fw, default_flow_style=False)

install.install.sub_commands.append(('install_config_file', install_config_file))

data_files = [
    (data_dir, ['oonib.conf.example']),
    (os.path.join(data_dir, 'decks'), ['data/decks/README']),
    (os.path.join(data_dir, 'inputs'), ['data/inputs/Makefile']),
    (os.path.join(spool_dir, 'reports'), ['data/reports/.gitignore']),
    (os.path.join(spool_dir, 'archive'), ['data/archive/.gitignore']),
    (os.path.join(var_dir, 'tor'), ['data/tor/.gitignore']),
    (var_dir, ['data/bouncer.yaml', 'data/policy.yaml'])
]

with open('README.rst') as f:
    readme = f.read()

with open('ChangeLog.rst') as f:
    changelog = f.read()

install_requires, dependency_links = get_requirements()
setup(
    name="oonibackend",
    version=__version__,
    author="The Tor Project, Inc",
    author_email="ooni-dev@torproject.org",
    url="https://ooni.torproject.org",
    license="BSD 2 clause",
    description="Open Observatory of Network Interference Backend",
    long_description="ooni backend infrastructure",
    scripts=["bin/oonib", "bin/oonibadmin", "bin/archive_oonib_reports"],
    packages=find_packages(),
    data_files=data_files,
    install_requires=install_requires,
    dependency_links=dependency_links,
    classifiers=(
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Framework :: Twisted",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Telecommunications Industry",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2 :: Only",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: BSD",
        "Operating System :: POSIX :: BSD :: BSD/OS",
        "Operating System :: POSIX :: BSD :: FreeBSD",
        "Operating System :: POSIX :: BSD :: NetBSD",
        "Operating System :: POSIX :: BSD :: OpenBSD",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Unix",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Security",
        "Topic :: Security :: Cryptography",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Testing :: Traffic Generation",
        "Topic :: System :: Networking :: Monitoring",
    )
)
