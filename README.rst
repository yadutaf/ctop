CTOP
====

A lightweight top like monitor for linux CGroups

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
Your cgroups could be managed by cgmanager, system and by hand, it is flexible
enough to adapt to any scenario. The only requirement is to have at least one
active cgroup hierarchie.

Installation
------------

.. code:: bash

  pip install ctop
  ctop

OR

.. code:: bash

  git clone https://github.com/yadutaf/ctop.git
  cd ctop
  pip install -r requirements.txt
  ./ctop.py

Requirements
------------

* python 2.7.x
* pip
* at least one cgroup hierarchie mounted

Licence
-------

MIT

