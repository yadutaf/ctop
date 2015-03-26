#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Monitor local cgroups as used by Docker, LXC, SystemD, ...

Usage:
  ctop [--tree] [--refresh=<seconds>] [--columns=<columns>] [--sort-col=<sort-col>]
  ctop (-h | --help)

Options:
  --tree                 Show tree view by default.
  --refresh=<seconds>    Refresh display every <seconds> [default: 1].
  --columns=<columns>    List of optional columns to display. Always includes 'name'. [default: owner,processes,memory,cpu-sys,cpu-user,blkio,cpu-time].
  --sort-col=<sort-col>  Select column to sort by initially. Can be changed dynamically. [default: cpu-user]
  -h --help              Show this screen.

'''

import os
import sys
import stat
import pwd
import time
import psutil

from collections import defaultdict
from collections import namedtuple

from docopt import docopt

try:
    import curses, _curses
except ImportError:
    print >> sys.stderr, "Curse is not available on this system. Exiting."
    sys.exit(0)

HIDE_EMPTY_CGROUP = True
CGROUP_MOUNTPOINTS={}
CONFIGURATION = {
        'sort_by': 'cpu_total',
        'sort_asc': False,
        'tree': False,
        'pause_refresh': False,
        'refresh_interval': 1.0,
        'columns': [],
}

Column = namedtuple('Column', ['title', 'width', 'align', 'col_fmt', 'col_data', 'col_sort'])

COLUMNS = []
COLUMNS_MANDATORY = ['name']
COLUMNS_AVAILABLE = {
    'owner':     Column("OWNER",   10, '<', '{:%ss}',      'owner',           'owner'),
    'processes': Column("PROC",     4, '>', '{:%sd}',      'tasks',           'tasks'),
    'memory':    Column("MEMORY",  17, '^', '{:%ss}',      'memory_cur_str',  'memory_cur_bytes'),
    'cpu-sys':   Column("SYST",     5, '^', '{: >%s.1%%}', 'cpu_syst',        'cpu_total'),
    'cpu-user':  Column("USER",     5, '^', '{: >%s.1%%}', 'cpu_user',        'cpu_total'),
    'blkio':     Column("BLKIO",   10, '^', '{: >%s}',     'blkio_bw',        'blkio_bw_bytes'),
    'cpu-time':  Column("TIME+",   14, '^', '{: >%ss}',    'cpu_total_str',   'cpu_total_seconds'),
    'name':      Column("CGROUP",  '', '<', '{:%ss}',      'cgroup',          'cgroup'),
}

# TODO:
# - detect container technology
# - visual CPU/memory usage
# - auto-color
# - adapt name / commands to underlying container system
# - persist preferences
# - dynamic column width
# - handle small screens
# - test/fix python 2.6

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

        if name == 'tasks' or '\n' in content or ' ' in content:
            content = content.split('\n')

            if ' ' in content[0]:
                content = dict((l.split(' ', 1) for l in content))
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

    # Collect BlockIO statistics
    if 'blkio' in CGROUP_MOUNTPOINTS:
        # list all "folders" under mountpoint
        for cgroup in cgroups(CGROUP_MOUNTPOINTS['blkio']):
            # Collect BlockIO stats
            cur[cgroup.name]['blkio.throttle.io_service_bytes'] = cgroup['blkio.throttle.io_service_bytes']
            cur[cgroup.name]['blkio.throttle.io_service_bytes.diff'] = {'total':0}

            # Collect BlockIO increase on run > 1
            if cgroup.name in prev:
                cur_val = cur[cgroup.name]['blkio.throttle.io_service_bytes']['Total']
                prev_val = prev[cgroup.name]['blkio.throttle.io_service_bytes']['Total']
                cur[cgroup.name]['blkio.throttle.io_service_bytes.diff']['total'] = cur_val - prev_val

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
            'cpu_total_seconds': data.get('cpuacct.stat', {}).get('system', 0) + data.get('cpuacct.stat', {}).get('user', 0),
            'cpu_syst': cpu_usage.get('system', 0) / cpu_to_percent,
            'cpu_user': cpu_usage.get('user', 0) / cpu_to_percent,
            'blkio_bw_bytes': data.get('blkio.throttle.io_service_bytes.diff', {}).get('total', 0),
            'cgroup': cgroup,
        }
        line['cpu_total'] = line['cpu_syst'] + line['cpu_user'],
        line['cpu_total_str'] = to_human_time(line['cpu_total_seconds'])
        line['memory_cur_percent'] = line['memory_cur_bytes'] / line['memory_limit_bytes']
        line['memory_cur_str'] = "{: >7}/{: <7}".format(to_human(line['memory_cur_bytes']), to_human(line['memory_limit_bytes']))
        line['blkio_bw'] = to_human(line['blkio_bw_bytes'], 'B/s')
        results.append(line)

    return results

def render_tree(results, tree, level=0, level_done=0, node='/'):
    level += 1

    # Exit condition
    if node not in tree:
        return

    # Iteration
    for i, line in enumerate(tree[node]):
        cgroup = line['cgroup']

        # Build name
        _tree  = [' ', ' ', ' ']*level_done
        _tree += [curses.ACS_VLINE, ' ', ' ']*max(level-level_done-1, 0)
        if i == len(tree[node]) - 1:
            _tree.extend([curses.ACS_LLCORNER, curses.ACS_HLINE, ' '])
            level_done += 1
        else:
            _tree.extend([curses.ACS_LTEE, curses.ACS_HLINE, ' '])

        # Commit, recurse
        line['_tree'] = _tree
        results.append(line)
        render_tree(results, tree, level, level_done, cgroup)

def prepare_tree(results):
    # Build tree
    tree = {}
    rendered = []
    for line in results:
        cgroup = line['cgroup']
        parent = os.path.dirname(cgroup)

        # Root cgroup ?
        if parent == cgroup:
            rendered.append(line)
            continue

        # Insert in hierarchie as needed
        if parent not in tree:
            tree[parent] = []
        tree[parent].append(line)

    # Render tree, starting from root
    render_tree(rendered, tree)
    return rendered

def display(scr, results, conf):
    # Sort
    results = sorted(results, key=lambda line: line.get(conf['sort_by'], 0), reverse=not conf['sort_asc'])

    if CONFIGURATION['tree']:
        results = prepare_tree(results)

    # Display statistics
    curses.endwin()
    height, width = scr.getmaxyx()

    # Title line && templates
    x = 0
    line_tpl = []
    scr.addstr(0, 0, ' '*width, curses.color_pair(1))
 
    for col in COLUMNS:
        # Build templates
        title_fmt = '{:%s%ss}' % (col.align, col.width)
        line_tpl.append(col.col_fmt % (col.width))

        # Build title line
        color = 2 if col.col_sort == conf['sort_by'] else 1
        scr.addstr(0, x, title_fmt.format(col.title)+' ', curses.color_pair(color))
        if col.width:
            x += col.width + 1

    # Content
    lineno = 1
    for line in results:
        y = 0
        try:
            for col in COLUMNS:
                cell_tpl = col.col_fmt % (col.width if col.width else width - y)
                data_point = line.get(col.col_data, '')

                if col.title == 'CGROUP' and CONFIGURATION['tree']:
                    data_point = os.path.basename(data_point) or '[root]'

                    for c in line.get('_tree', []):
                        scr.addch(c, curses.color_pair(4))
                        y+=1

                scr.addstr(lineno, y, cell_tpl.format(data_point))
                if col.width:
                    scr.addch(' ')
                    y += col.width + 1
        except:
            break
        lineno += 1

    # status line
    try:
        color = curses.color_pair(2)
        scr.addstr(height-1, 0, ' '*(width-1), color)
        scr.addstr(height-1, 0, " CTOP ", color)
        scr.addch(curses.ACS_VLINE, color)
        scr.addstr(" [P]ause: "+('On ' if CONFIGURATION['pause_refresh'] else 'Off '), color)
        scr.addch(curses.ACS_VLINE, color)
        scr.addstr(" [F5] Toggle %s view "%('list' if CONFIGURATION['tree'] else 'tree'), color)
        scr.addch(curses.ACS_VLINE, color)
        scr.addstr(" [Q]uit", color)
    except:
        # be resize proof
        pass

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
    elif c == ord('p'):
        CONFIGURATION['pause_refresh'] = not CONFIGURATION['pause_refresh']
        return 2
    elif c == 269: # F5
        CONFIGURATION['tree'] = not CONFIGURATION['tree']
        return 2
    return 1

def on_mouse():
    '''Update selected line / sort'''
    _, x, y, z, bstate =  curses.getmouse()

    # Left button click ?
    if bstate & curses.BUTTON1_CLICKED:
        # Is it title line ?
        if y == 0:
            # Determine sort column based on offset / col width
            x_max = 0
            for col in COLUMNS:
                if not col.width:
                    set_sort_col(col.col_sort)
                elif x < x_max+col.width:
                    set_sort_col(col.col_sort)
                else:
                    x_max += col.width + 1
                    continue
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
        else:
            return on_keyboard(c)
    except _curses.error:
        return 0

def rebuild_columns():
    del COLUMNS[:]
    for col in CONFIGURATION['columns']+COLUMNS_MANDATORY:
        COLUMNS.append(COLUMNS_AVAILABLE[col])

def main():
    # Parse arguments
    arguments = docopt(__doc__)

    CONFIGURATION['tree'] = arguments['--tree']
    CONFIGURATION['refresh_interval'] = float(arguments['--refresh'])
    CONFIGURATION['columns'] = []

    for col in arguments['--columns'].split(','):
        col = col.strip()
        if col in COLUMNS_MANDATORY:
            continue
        if not col in COLUMNS_AVAILABLE:
            print >>sys.stderr, "Invalid column name", col
            print __doc__
            sys.exit(1)
        CONFIGURATION['columns'].append(col)
    rebuild_columns()

    if arguments['--sort-col'] not in COLUMNS_AVAILABLE:
        print >>sys.stderr, "Invalid sort column name", arguments['--sort-col']
        print __doc__
        sys.exit(1)
    CONFIGURATION['sort_by'] = COLUMNS_AVAILABLE[arguments['--sort-col']].col_sort

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
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN) # header
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)  # focused header / line
        curses.init_pair(3, curses.COLOR_WHITE, -1)  # regular
        curses.init_pair(4, curses.COLOR_CYAN,  -1)  # tree

        # Main loop
        while True:
            collect(measures)
            results = built_statistics(measures, CONFIGURATION)
            display(stdscr, results, CONFIGURATION)
            sleep_start = time.time()
            while CONFIGURATION['pause_refresh'] or time.time() < sleep_start + CONFIGURATION['refresh_interval']:
                if CONFIGURATION['pause_refresh']:
                    to_sleep = -1
                else:
                    to_sleep = int((sleep_start + CONFIGURATION['refresh_interval'] - time.time())*1000)
                ret = event_listener(stdscr, to_sleep)
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

