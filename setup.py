#!/usr/bin/env python

import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
    readme = f.read()

setup(
    name='ctop',
    version='1.0.0',
    description='A lightweight top like monitor for linux CGroups',
    long_description=readme,
    author='Jean-Tiare Le Bigot',
    author_email='jt@yadutaf.fr',
    url='https://github.com/yadutaf/ctop',
    py_modules=['cgroup_top'],
    scripts=['bin/ctop'],
    license='MIT',
    platforms = 'any',
    classifiers=[
        'Environment :: Console',
        'Environment :: Console :: Curses',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Monitoring',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
)

