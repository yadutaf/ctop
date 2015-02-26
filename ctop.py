#!/usr/bin/env python
'''
Iterate over all cgroup mountpoints and output global cgroup statistics
'''

import os
import time
import tabulate
import psutil

HIDE_EMPTY_CGROUP = True
UPDATE_INTERVAL = 1.0 # seconds
CGROUP_MOUNTPOINTS={}
CGROUPS_SUBSYS=[]

CGROUPS = {
    'prev': {},
    'cur': {},
}

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

CGROUP_DATA = {}

def cgroup_push_data(cgroup, key):
    if cgroup not in CGROUP_DATA:
        CGROUP_DATA[cgroup] = {}
    CGROUP_DATA[cgroup][key] = cgroup[key]

def sort_by(key):
    return sorted(CGROUP_DATA.iteritems(), key=lambda cgroup: int(cgroup[1].get(key, 0)))

# Collect memory statistics
if 'memory' in CGROUP_MOUNTPOINTS:
    system_memory = psutil.virtual_memory().total
    # list all "folders" under mountpoint
    for cgroup in cgroups(CGROUP_MOUNTPOINTS['memory']):
        if cgroup.name not in CGROUP_DATA:
            CGROUP_DATA[cgroup.name] = {}
        CGROUP_DATA[cgroup.name]['memory.usage_in_bytes'] = cgroup['memory.usage_in_bytes']
        CGROUP_DATA[cgroup.name]['memory.max_usage_in_bytes'] = cgroup['memory.usage_in_bytes']
        CGROUP_DATA[cgroup.name]['memory.limit_in_bytes'] = min(int(cgroup['memory.limit_in_bytes']), system_memory)

# Collect CPU statistics
if 'cpuacct' in CGROUP_MOUNTPOINTS:
    HZ = os.sysconf('SC_CLK_TCK')
    CPU_CNT = psutil. cpu_count()
    # list all "folders" under mountpoint
    for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
        if cgroup.name not in CGROUP_DATA:
            CGROUP_DATA[cgroup.name] = {}

        CGROUP_DATA[cgroup.name]['tasks'] = cgroup['tasks']
        CGROUP_DATA[cgroup.name]['cpuacct.stat'] = cgroup['cpuacct.stat']
        CGROUP_DATA[cgroup.name]['cpuacct.stat.diff'] = {}
        
        # Handle potentially vanishing tasks
        for key, value in CGROUP_DATA[cgroup.name]['cpuacct.stat'].iteritems():
            CGROUP_DATA[cgroup.name]['cpuacct.stat.diff'][key] = 0

    time.sleep(1.0)

    for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
        if cgroup.name not in CGROUP_DATA:
            CGROUP_DATA[cgroup.name] = {}
            prev = {'user':0, 'system':0}
        else:
            prev = CGROUP_DATA[cgroup.name]['cpuacct.stat']
 
        CGROUP_DATA[cgroup.name]['cpuacct.stat'] = cgroup['cpuacct.stat']
        for key, value in CGROUP_DATA[cgroup.name]['cpuacct.stat'].iteritems():
            CGROUP_DATA[cgroup.name]['cpuacct.stat.diff'][key] = value - prev[key]

# Display statistics: Find the biggest user
table = [['cgroup', 'processes', 'current memory', 'peak memory', 'system cpu', 'user cpu']]
for cgroup, data in sort_by('memory.usage_in_bytes'):
    cpu_usage = data.get('cpuacct.stat.diff', {})
    table.append([
        cgroup,
        len(data['tasks']),
        "%s/%s" % (to_human(data.get('memory.usage_in_bytes', -1)), to_human(data.get('memory.limit_in_bytes', system_memory))),
        to_human(data.get('memory.max_usage_in_bytes', -1)),
        cpu_usage.get('system', 0) * 100.0 / HZ / CPU_CNT,
        cpu_usage.get('user', 0) * 100.0 / HZ / CPU_CNT,
    ])

print tabulate.tabulate(table, headers="firstrow") 

