CTOP
====

A lightweight top like monitor for linux CGroups

.. image:: screenshots/screenshot.png

Introduction
------------

Linux Control Groups aka CGroups is a lighweight Linux mechanism to control
resources, typically cpu and memory for a logical group of processes.

Where traditional use of computers usualy involved managing resources on a
per-user basis, cgroups allows to constrints resources at a much thiner
granularity. For example, it possible to bound Firefox memory usage and
run a Blender rendering job at a lower priority without involving multiple
users neither tracking manually a bunch of PIDs.

This mechanism is at the heart of Docker, LXC and Systemd isiolation layers to
name only a few.

While is common and easy to monitor resources at a task level and system, there
were no tools widely available to monitor theses resources at a logical,
intermediary level, namely CGroups

CTOP is the tool that is solving this specific issue.

It is completely agnostic of the underlying containerization technique used.
Your cgroups could be managed by docker, cgmanager, system or manually, it has
been deigned to adapt to any scenario. The only requirement is to have at least
one active cgroup hierarchie.

Installation
------------

ctop is a monitoring tool. As such, we expect that ops needing it will
potentially be in a hurry or in a constrained production environment. This is
why ctop deliberately supports various installation method and is designed to
rely on no external dependency beyon Python >= 2.6 (Debian >= Squeeze).

This said, the recommended installation method is currently via pip

.. code:: bash

  pip install ctop
  ctop

Alternatively, you may directly clone the git repository or get the latests
release tarball from github:

.. code:: bash

  git clone https://github.com/yadutaf/ctop.git
  cd ctop
  ./cgroup_top.py

And, obviously, the docker monitoring tool supports transactional installation
via docker itself. Note that is still experimental.

.. code:: bash

  docker pull yadutaf/ctop
  docker run --volume=/sys/fs/cgroup:/sys/fs/cgroup:ro -it --rm yadutaf/ctop
  # Optionally, to resolve uids to usernames, add '--volume /etc/passwd:/etc/passwd:ro'

Requirements
------------

* python >=2.6

Licence
-------

MIT

