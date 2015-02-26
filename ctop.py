#!/usr/bin/env python
'''
Iterate over all cgroup mountpoints and output global cgroup statistics
'''

import os
import time
import tabulate
import psutil

from collections import defaultdict

HIDE_EMPTY_CGROUP = True
UPDATE_INTERVAL = 1.0 # seconds
CGROUP_MOUNTPOINTS={}
CGROUPS_SUBSYS=[]

CGROUPS = {
    'prev': {},
    'cur': {},
}

# TODO:
# - curse list
# - select refresh rate
# - select sort column
# - visual CPU/memory usage
# - block-io
# - auto-color
# - adapt name / commands to underlying container system
# - exact timing in CPU derivation
# - hiereachical view

## Utils

def to_human(num, suffix='B'):
    num = int(num)
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)

## Grab system facts

# Get all cgroup subsystems avalaible on this system
with open("/proc/cgroups") as f:
    cgroups = f.read().strip()

for cgroup in cgroups.split('\n'):
    if cgroup[0] == '#': continue
    CGROUPS_SUBSYS.append(cgroup.split()[0])

# Match cgroup mountpoints to susbsytems. Always take the first matching
with open("/proc/mounts") as f:
    mounts = f.read().strip()

for mount in mounts.split('\n'):
    mount = mount.split(' ')

    if mount[2] != "cgroup":
        continue

    for arg in mount[3].split(','):
        if arg in CGROUPS_SUBSYS and arg not in CGROUP_MOUNTPOINTS:
            CGROUP_MOUNTPOINTS[arg] = mount[1]

## Tools

class Cgroup(object):
    def __init__(self, path, base_path):
        self.path = path
        self.base_path = base_path

    @property
    def name(self):
        return self.path[len(self.base_path):] or '/'

    def _coerce(self, value):
        try:
            return int(value)
        except: 
            pass

        try:
            return float(value)
        except:
            pass

        return value

    def __getitem__(self, name):
        path = os.path.join(self.base_path, self.path, name)
        
        with open(path) as f:
            content = f.read().strip()

        if name == 'tasks' or '\n' in content:
            content = content.split('\n')

            if ' ' in content[0]:
                content = dict((l.split(' ') for l in content))
                for k, v in content.iteritems():
                    content[k] = self._coerce(v)
            else:
                content = [self._coerce(v) for v in content]

        else:
            content = self._coerce(content)

        return content

def cgroups(base_path):
    '''
    Generator of cgroups under path ``name``
    '''
    for cgroup_path, dirs, files in os.walk(base_path):
        yield Cgroup(cgroup_path, base_path)

## Grab cgroup data

def collect(measures):
    # Collect global data
    if 'cpuacct' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
            measures['data'][cgroup.name]['tasks'] = cgroup['tasks']

    # Collect memory statistics
    if 'memory' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['memory']):
            measures['data'][cgroup.name]['memory.usage_in_bytes'] = cgroup['memory.usage_in_bytes']
            measures['data'][cgroup.name]['memory.max_usage_in_bytes'] = cgroup['memory.usage_in_bytes']
            measures['data'][cgroup.name]['memory.limit_in_bytes'] = min(int(cgroup['memory.limit_in_bytes']), measures['global']['total_memory'])

    # Collect CPU statistics
    if 'cpuacct' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
            # Collect CPU stats
            measures['data'][cgroup.name]['cpuacct.stat'] = cgroup['cpuacct.stat']

            # Collect CPU increase on run > 1
            if 'cpuacct.stat.diff' not in measures['data'][cgroup.name]:
                measures['data'][cgroup.name]['cpuacct.stat.diff'] = {'user':0, 'system':0}
            else:
                prev = measures['data'][cgroup.name]['cpuacct.stat']
                for key, value in measures['data'][cgroup.name]['cpuacct.stat'].iteritems():
                    measures['data'][cgroup.name]['cpuacct.stat.diff'][key] = value - prev[key]

def display(measures, sort_key):
    # sort
    results = sorted(measures['data'].iteritems(), key=lambda cgroup: int(cgroup[1].get(sort_key, 0)))

    # Display statistics: Find the biggest user
    table = [['cgroup', 'processes', 'current memory', 'peak memory', 'system cpu', 'user cpu']]
    cpu_to_percent = 100.0 / measures['global']['scheduler_frequency'] / measures['global']['total_cpu']
    print cpu_to_percent
    for cgroup, data in results:
        cpu_usage = data.get('cpuacct.stat.diff', {})
        table.append([
            cgroup,
            len(data['tasks']),
            "%s/%s" % (to_human(data.get('memory.usage_in_bytes', 0)), to_human(data.get('memory.limit_in_bytes', measures['global']['total_memory']))),
            to_human(data.get('memory.max_usage_in_bytes', 0)),
            cpu_usage.get('system', 0) * cpu_to_percent,
            cpu_usage.get('user', 0) * cpu_to_percent,
        ])

    print tabulate.tabulate(table, headers="firstrow")

if __name__ == "__main__":
    # Initialization, global system data
    measures = {
        'data': defaultdict(dict),
        'global': {
            'total_cpu': psutil.cpu_count(),
            'total_memory': psutil.virtual_memory().total,
            'scheduler_frequency': os.sysconf('SC_CLK_TCK'),
        }
    }

    try:
        while True:
            collect(measures)
            display(measures, 'memory.usage_in_bytes')
            time.sleep(1.0)
    except KeyboardInterrupt:
        print "Bye !"

