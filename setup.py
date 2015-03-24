#!/usr/bin/env python

import sys
import os
from setuptools import setup

if sys.version_info < (2,7):
    raise NotImplementedError("Sorry, you need at least Python 2.7 to use ctop.")

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
    readme = f.read()

setup(
    name='ctop',
    version='0.2.0',
    description='A lightweight top like monitor for linux CGroups',
    long_description=readme,
    author='Jean-Tiare Le Bigot',
    author_email='jt@yadutaf.fr',
    url='https://github.com/yadutaf/ctop',
    py_modules=['cgroup_top'],
    scripts=['bin/ctop'],
    install_requires=['psutil==2.2.1'],
    license='MIT',
    platforms = 'any',
    classifiers=[
        'Environment :: Console',
        'Environment :: Console :: Curses',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Monitoring',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
    ],
)

