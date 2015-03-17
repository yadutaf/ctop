#!/usr/bin/env python
'''
Iterate over all cgroup mountpoints and output global cgroup statistics
'''

import os
import sys
import stat
import pwd
import time
import psutil

from collections import defaultdict

try:
    import curses, _curses
except ImportError:
    print >> sys.stderr, "Curse is not available on this system. Exiting."
    sys.exit(0)

HIDE_EMPTY_CGROUP = True
UPDATE_INTERVAL = 1.0 # seconds
CGROUP_MOUNTPOINTS={}
CONFIGURATION = {
        'sort_by': 'cpu_total',
        'sort_asc': False,
}

# TODO:
# - select display colums
# - select refresh rate
# - detect container technology
# - visual CPU/memory usage
# - block-io
# - auto-color
# - adapt name / commands to underlying container system
# - hiereachical view
# - persist preferences
# - dynamic column width
# - only show residual cpu time / memory (without children cgroups) ?

## Utils

def to_human(num, suffix='B'):
    num = int(num)
    for unit in [' ','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "{:.1f}{}{}".format(num, unit, suffix)
        num /= 1024.0
    return "{:5.1d}{}{}" % (num, 'Y', suffix)

def div(num, by):
    res = num / by
    mod = num % by
    return res, mod

def to_human_time(seconds):
    minutes, seconds = div(seconds, 60)
    hours, minutes = div(minutes, 60)
    days, hours = div(hours, 24)
    if days:
        return '%3dd %02d:%02d.%02d' % (days, hours, minutes, seconds)
    else:
        return '%02d:%02d.%02d' % (hours, minutes, seconds)

class Cgroup(object):
    def __init__(self, path, base_path):
        self.path = path
        self.base_path = base_path

    @property
    def name(self):
        return self.path[len(self.base_path):] or '/'

    @property
    def owner(self):
        path = os.path.join(self.base_path, self.path, 'tasks')
        uid = os.stat(path).st_uid
        try:
            return pwd.getpwuid(uid).pw_name
        except:
            return uid

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

def init():
    # Get all cgroup subsystems avalaible on this system
    with open("/proc/cgroups") as f:
        cgroups = f.read().strip()

    subsystems = []
    for cgroup in cgroups.split('\n'):
        if cgroup[0] == '#': continue
        subsystems.append(cgroup.split()[0])

    # Match cgroup mountpoints to susbsytems. Always take the first matching
    with open("/proc/mounts") as f:
        mounts = f.read().strip()

    for mount in mounts.split('\n'):
        mount = mount.split(' ')

        if mount[2] != "cgroup":
            continue

        for arg in mount[3].split(','):
            if arg in subsystems and arg not in CGROUP_MOUNTPOINTS:
                CGROUP_MOUNTPOINTS[arg] = mount[1]

def collect(measures):
    cur = defaultdict(dict)
    prev = measures['data']

    # Collect global data
    if 'cpuacct' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
            # Collect tasks
            cur[cgroup.name]['tasks'] = cgroup['tasks']

            # Collect user
            cur[cgroup.name]['owner'] = cgroup.owner

    # Collect memory statistics
    if 'memory' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['memory']):
            cur[cgroup.name]['memory.usage_in_bytes'] = cgroup['memory.usage_in_bytes']
            cur[cgroup.name]['memory.max_usage_in_bytes'] = cgroup['memory.usage_in_bytes']
            cur[cgroup.name]['memory.limit_in_bytes'] = min(int(cgroup['memory.limit_in_bytes']), measures['global']['total_memory'])

    # Collect CPU statistics
    if 'cpuacct' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['cpuacct']):
            # Collect CPU stats
            cur[cgroup.name]['cpuacct.stat'] = cgroup['cpuacct.stat']
            cur[cgroup.name]['cpuacct.stat.diff'] = {'user':0, 'system':0}

            # Collect CPU increase on run > 1
            if cgroup.name in prev:
                for key, value in cur[cgroup.name]['cpuacct.stat'].iteritems():
                    cur[cgroup.name]['cpuacct.stat.diff'][key] = value - prev[cgroup.name]['cpuacct.stat'][key]

    # Apply
    measures['data'] = cur

def built_statistics(measures, conf):
    # Time
    prev_time = measures['global'].get('time', -1)
    cur_time = time.time()
    time_delta = cur_time - prev_time
    measures['global']['time'] = cur_time
    cpu_to_percent = measures['global']['scheduler_frequency'] * measures['global']['total_cpu'] * time_delta

    # Build data lines
    results = []
    for cgroup, data in measures['data'].iteritems():
        cpu_usage = data.get('cpuacct.stat.diff', {})
        line = {
            'owner': data.get('owner', 'nobody'),
            'tasks': len(data['tasks']),
            'memory_cur_bytes': data.get('memory.usage_in_bytes', 0),
            'memory_limit_bytes': data.get('memory.limit_in_bytes', measures['global']['total_memory']),
            'memory_peak_bytes': data.get('memory.max_usage_in_bytes', 0),
            'cpu_total_seconds': data.get('cpuacct.stat', {}).get('system', 0) + data.get('cpuacct.stat', {}).get('user', 0),
            'cpu_syst': cpu_usage.get('system', 0) / cpu_to_percent,
            'cpu_user': cpu_usage.get('user', 0) / cpu_to_percent,
            'cgroup': cgroup,
        }
        line['cpu_total'] = line['cpu_syst'] + line['cpu_user'],
        line['cpu_total_str'] = to_human_time(line['cpu_total_seconds'])
        line['memory_cur_percent'] = line['memory_cur_bytes'] / line['memory_limit_bytes']
        line['memory_cur_str'] = "{: >7}/{: <7}".format(to_human(line['memory_cur_bytes']), to_human(line['memory_limit_bytes']))
        line['memory_peak_str'] = to_human(line['memory_peak_bytes'])
        results.append(line)

    return results

def display(scr, results, conf):
    # Sort
    results = sorted(results, key=lambda line: line.get(conf['sort_by'], 0), reverse=not conf['sort_asc'])

    # Display statistics
    curses.endwin()
    height, width = scr.getmaxyx()
    LINE_TMPL = "{:"+str(width)+"s}"
    scr.addstr(0, 0, LINE_TMPL.format('OWNER      PROC      CURRENT        PEAK  SYSTEM USER       TIME+    CGROUP'), curses.color_pair(1))
    RES_TMPL = "{owner:10s} {tasks:4d} {memory_cur_str:16s} {memory_peak_str:>8s} {cpu_syst: >5.1%} {cpu_user: >5.1%} {cpu_total_str: >14s} {cgroup}"

    lineno = 1
    for line in results:
        try:
            line = RES_TMPL.format(**line)
            scr.addstr(lineno, 0, LINE_TMPL.format(line))
        except:
            break
        lineno += 1

    scr.refresh()

def set_sort_col(sort_by):
    if CONFIGURATION['sort_by'] == sort_by:
        CONFIGURATION['sort_asc'] = not CONFIGURATION['sort_asc']
    else:
        CONFIGURATION['sort_by'] = sort_by

def on_keyboard(c):
    '''Handle keyborad shortcuts'''
    if c == ord('q'):
        raise KeyboardInterrupt()
    return 1

def on_mouse():
    '''Update selected line / sort'''
    _, x, y, z, bstate =  curses.getmouse()

    # Left button click ?
    if bstate & curses.BUTTON1_CLICKED:
        # Is it title line ?
        if y == 0:
            # "Guess" sort colum based on X
            # TODO: make it "discoverable"
            RES_TMPL = "{owner:10s} {tasks:4d} {memory_cur:15s} {memory_peak:>7s} {cpu_syst: >5.1%} {cpu_user: >5.1%} {cgroup}"
            if   x < 11: set_sort_col('owner')
            elif x < 16: set_sort_col('tasks')
            elif x < 33: set_sort_col('memory_cur_bytes')
            elif x < 42: set_sort_col('memory_peak_bytes')
            elif x < 53: set_sort_col('cpu_total')
            elif x < 70: set_sort_col('cpu_total_seconds')
            else:        set_sort_col('cgroup')
            return 2
    return 1

def on_resize():
    '''Redraw screen, do not refresh'''
    return 1

def event_listener(scr, timeout):
    '''
    Wait for curses events on screen ``scr`` at mot ``timeout`` ms

    return
     - 1 OK
     - 2 redraw
     - 0 error
    '''
    try:
        scr.timeout(timeout)
        c = scr.getch()
        if c == -1:
            return 1
        elif c == curses.KEY_MOUSE:
            return on_mouse()
        elif c == curses.KEY_RESIZE:
            return on_resize()
        elif c < 256:
            return on_keyboard(c)
    except _curses.error:
        return 0

def main():
    # Initialization, global system data
    measures = {
        'data': defaultdict(dict),
        'global': {
            'total_cpu': psutil.cpu_count(),
            'total_memory': psutil.virtual_memory().total,
            'scheduler_frequency': os.sysconf('SC_CLK_TCK'),
        }
    }

    init()

    try:
        # Curse initialization
        stdscr = curses.initscr()
        curses.start_color() # load colors
        curses.use_default_colors()
        curses.noecho()      # do not echo text
        curses.cbreak()      # do not wait for "enter"
        curses.curs_set(0)   # hide cursor
        stdscr.keypad(1)     # parse keypad controll sequences
        curses.mousemask(curses.ALL_MOUSE_EVENTS)

        # Curses colors
        curses.init_pair(1, -1, curses.COLOR_GREEN)

        # Main loop
        while True:
            collect(measures)
            results = built_statistics(measures, CONFIGURATION)
            display(stdscr, results, CONFIGURATION)
            sleep_start = time.time()
            while time.time() < sleep_start + UPDATE_INTERVAL:
                to_sleep = sleep_start + UPDATE_INTERVAL - time.time()
                ret = event_listener(stdscr, int(to_sleep*1000))
                if ret == 2:
                    display(stdscr, results, CONFIGURATION)

    except KeyboardInterrupt:
        pass
    finally:
        curses.nocbreak()
        stdscr.keypad(0)
        curses.echo()
        curses.endwin()

if __name__ == "__main__":
    main()

