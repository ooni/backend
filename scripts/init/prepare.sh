#!/bin/sh

# Warning
# We advise installing virtualenv-1.9 or greater. Prior to version 1.9, the pip
# included in virtualenv did not not download from PyPI over SSL.
# Solution, use virtualenv-1.9
# XXX: where is a signed release for any of virtualenv?

# XXX
# Retrieved from http://www.virtualenv.org/en/1.9.X/news.html Mar 6 2013
# Warning
# Python bugfix releases 2.6.8, 2.7.3, 3.1.5 and 3.2.3 include a change that will
# cause “import random” to fail with “cannot import name urandom” on any
# virtualenv created on a Unix host with an earlier release of Python
# 2.6/2.7/3.1/3.2, if the underlying system Python is upgraded. This is due to
# the fact that a virtualenv uses the system Python’s standard library but
# contains its own copy of the Python interpreter, so an upgrade to the system
# Python results in a mismatch between the version of the Python interpreter and
# the version of the standard library. It can be fixed by removing
# $ENV/bin/python and re-running virtualenv on the same target directory with the
# upgraded Python.

# In the wild:
# http://stackoverflow.com/questions/10366821/python-importerror-cannot-import-urandom-since-ubuntu-12-04-upgrade

# Solution: Redeploy oonib after upgrading python 2.6.6 to 2.6.8

OONIB_GIT_REPO=ooni-backend
OONIB_GIT_URL="https://github.com/aagbsn/$OONIB_GIT_REPO.git"
OONIB_GIT_TAG=master
#OONIB_GIT_REPO=oonib
#OONIB_GIT_URL="https://github.com/TheTorProject/$OONIB_GIT_REPO.git"
#OONIB_GIT_TAG=0.0.10

VIRTUALENV_GIT_REPO=virtualenv
VIRTUALENV_GIT_URL="https://github.com/pypa/$VIRTUALENV_GIT_REPO.git"
VIRTUALENV_GIT_TAG=1.9rc2

echo Installing build tools
sudo yum groupinstall -y Development\ Tools

echo Installing openssl-devel
sudo yum install -y openssl-devel

echo Installing glibc-static
sudo yum install -y glibc-static

SLICE_NAME=mlab_ooni
# Run relative to where the script was called
SCRIPT_ROOT=`pwd`
# Run relative to our slice path
#SCRIPT_ROOT=/home/$SLICE_NAME

echo Downloading $OONIB_GIT_REPO $OONIB_GIT_TAG
OONIB_PATH=$SCRIPT_ROOT/$OONIB_GIT_REPO
# does the repository already exist? If not, fetch it
if [ ! -e $OONIB_PATH ] ; then
  echo Fetching the $OONIB_GIT_REPO repository
  git clone $OONIB_GIT_URL $OONIB_PATH
fi
cd $OONIB_PATH
git fetch origin
git checkout $OONIB_GIT_TAG
#XXX: git-verify-tag $OONIB_GIT_TAG

# Get a copy of virtualenv
echo Downloading $VIRTUALENV_GIT_REPO $VIRTUALENV_GIT_TAG
VIRTUALENV_PATH=$SCRIPT_ROOT/$VIRTUALENV_GIT_REPO
if [ ! -e $VIRTUALENV_PATH ] ; then
  git clone $VIRTUALENV_GIT_URL $VIRTUALENV_PATH
fi
cd $VIRTUALENV_PATH
git fetch origin
git checkout $VIRTUALENV_GIT_TAG
#XXX: git verify-tag $VIRTUALENV_GIT_TAG
  
# See warning. Remove python and redeploy virtualenv with current python
PYTHON_EXE=$SCRIPT_ROOT/bin/python
if [ -e $PYTHON_EXE ] ; then
  rm $PYTHON_EXE
fi
python $VIRTUALENV_PATH/virtualenv.py --no-site-packages $SCRIPT_ROOT
if [ ! -e $PYTHON_EXE ] ; then
  exit 1
fi

# run setup.py and fetch dependencies
cd $OONIB_PATH
$PYTHON_EXE setup.py install

#XXX: either create a bdist with compiled bytecode
# or just tar up the entire cwd and call it done, son.
