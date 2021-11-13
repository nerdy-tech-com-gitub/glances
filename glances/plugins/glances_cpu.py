# -*- coding: utf-8 -*-
#
# This file is part of Glances.
#
# Copyright (C) 2021 Nicolargo <nicolas@nicolargo.com>
#
# Glances is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Glances is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""CPU plugin."""

from glances.logger import logger
from glances.timer import getTimeSinceLastUpdate
from glances.compat import iterkeys
from glances.cpu_percent import cpu_percent
from glances.globals import LINUX
from glances.plugins.glances_core import Plugin as CorePlugin
from glances.plugins.glances_plugin import GlancesPlugin

import psutil

# Fields description
# description: human readable description
# short_name: shortname to use un UI
# unit: unit type
# rate: is it a rate ? If yes, // by time_since_update when displayed,
# min_symbol: Auto unit should be used if value > than 1 'X' (K, M, G)...
fields_description = {
    'total': {'description': 'Sum of all CPU percentages (except idle).',
              'unit': 'percent'},
    'system': {'description': 'percent time spent in kernel space. System CPU time is the \
time spent running code in the Operating System kernel.',
               'unit': 'percent'},
    'user': {'description': 'CPU percent time spent in user space. \
User CPU time is the time spent on the processor running your program\'s code (or code in libraries).',
             'unit': 'percent'},
    'iowait': {'description': '*(Linux)*: percent time spent by the CPU waiting for I/O \
operations to complete.',
               'unit': 'percent'},
    'idle': {'description': 'percent of CPU used by any program. Every program or task \
that runs on a computer system occupies a certain amount of processing \
time on the CPU. If the CPU has completed all tasks it is idle.',
             'unit': 'percent'},
    'irq': {'description': '*(Linux and BSD)*: percent time spent servicing/handling \
hardware/software interrupts. Time servicing interrupts (hardware + \
software).',
            'unit': 'percent'},
    'nice': {'description': '*(Unix)*: percent time occupied by user level processes with \
a positive nice value. The time the CPU has spent running users\' \
processes that have been *niced*.',
             'unit': 'percent'},
    'steal': {'description': '*(Linux)*: percentage of time a virtual CPU waits for a real \
CPU while the hypervisor is servicing another virtual processor.',
              'unit': 'percent'},
    'ctx_switches': {'description': 'number of context switches (voluntary + involuntary) per \
second. A context switch is a procedure that a computer\'s CPU (central \
processing unit) follows to change from one task (or process) to \
another while ensuring that the tasks do not conflict.',
                     'unit': 'number',
                     'rate': True,
                     'min_symbol': 'K',
                     'short_name': 'ctx_sw'},
    'interrupts': {'description': 'number of interrupts per second.',
                   'unit': 'number',
                   'rate': True,
                   'min_symbol': 'K',
                   'short_name': 'inter'},
    'soft_interrupts': {'description': 'number of software interrupts per second. Always set to \
0 on Windows and SunOS.',
                        'unit': 'number',
                        'rate': True,
                        'min_symbol': 'K',
                        'short_name': 'sw_int'},
    'cpucore': {'description': 'Total number of CPU core.',
                'unit': 'number'},
    'time_since_update': {'description': 'Number of seconds since last update.',
                          'unit': 'seconds'},
}

# SNMP OID
# percentage of user CPU time: .1.3.6.1.4.1.2021.11.9.0
# percentages of system CPU time: .1.3.6.1.4.1.2021.11.10.0
# percentages of idle CPU time: .1.3.6.1.4.1.2021.11.11.0
snmp_oid = {'default': {'user': '1.3.6.1.4.1.2021.11.9.0',
                        'system': '1.3.6.1.4.1.2021.11.10.0',
                        'idle': '1.3.6.1.4.1.2021.11.11.0'},
            'windows': {'percent': '1.3.6.1.2.1.25.3.3.1.2'},
            'esxi': {'percent': '1.3.6.1.2.1.25.3.3.1.2'},
            'netapp': {'system': '1.3.6.1.4.1.789.1.2.1.3.0',
                       'idle': '1.3.6.1.4.1.789.1.2.1.5.0',
                       'cpucore': '1.3.6.1.4.1.789.1.2.1.6.0'}}

# Define the history items list
# - 'name' define the stat identifier
# - 'y_unit' define the Y label
items_history_list = [{'name': 'user',
                       'description': 'User CPU usage',
                       'y_unit': '%'},
                      {'name': 'system',
                       'description': 'System CPU usage',
                       'y_unit': '%'}]


class Plugin(GlancesPlugin):
    """Glances CPU plugin.

    'stats' is a dictionary that contains the system-wide CPU utilization as a
    percentage.
    """

    def __init__(self, args=None, config=None):
        """Init the CPU plugin."""
        super(Plugin, self).__init__(args=args,
                                     config=config,
                                     items_history_list=items_history_list,
                                     fields_description=fields_description)

        # We want to display the stat in the curse interface
        self.display_curse = True

        # Call CorePlugin in order to display the core number
        try:
            self.nb_log_core = CorePlugin(args=self.args).update()["log"]
        except Exception:
            self.nb_log_core = 1

    @GlancesPlugin._check_decorator
    @GlancesPlugin._log_result_decorator
    def update(self):
        """Update CPU stats using the input method."""
        # Grab stats into self.stats
        if self.input_method == 'local':
            stats = self.update_local()
        elif self.input_method == 'snmp':
            stats = self.update_snmp()
        else:
            stats = self.get_init_value()

        # Update the stats
        self.stats = stats

        return self.stats

    def update_local(self):
        """Update CPU stats using psutil."""
        # Grab CPU stats using psutil's cpu_percent and cpu_times_percent
        # Get all possible values for CPU stats: user, system, idle,
        # nice (UNIX), iowait (Linux), irq (Linux, FreeBSD), steal (Linux 2.6.11+)
        # The following stats are returned by the API but not displayed in the UI:
        # softirq (Linux), guest (Linux 2.6.24+), guest_nice (Linux 3.2.0+)

        # Init new stats
        stats = self.get_init_value()

        stats['total'] = cpu_percent.get()
        # Grab: 'user', 'system', 'idle', 'nice', 'iowait',
        #       'irq', 'softirq', 'steal', 'guest', 'guest_nice'
        cpu_times_percent = psutil.cpu_times_percent(interval=0.0)
        for stat in cpu_times_percent._fields:
            stats[stat] = getattr(cpu_times_percent, stat)

        # Additional CPU stats (number of events not as a %; psutil>=4.1.0)
        # - ctx_switches: number of context switches (voluntary + involuntary) since boot.
        # - interrupts: number of interrupts since boot.
        # - soft_interrupts: number of software interrupts since boot. Always set to 0 on Windows and SunOS.
        # - syscalls: number of system calls since boot. Always set to 0 on Linux.
        cpu_stats = psutil.cpu_stats()

        # By storing time data we enable Rx/s and Tx/s calculations in the
        # XML/RPC API, which would otherwise be overly difficult work
        # for users of the API
        stats['time_since_update'] = getTimeSinceLastUpdate('cpu')

        # Core number is needed to compute the CTX switch limit
        stats['cpucore'] = self.nb_log_core

        # Previous CPU stats are stored in the cpu_stats_old variable
        if not hasattr(self, 'cpu_stats_old'):
            # Init the stats (needed to have the key name for export)
            for stat in cpu_stats._fields:
                # @TODO: better to set it to None but should refactor views and UI...
                stats[stat] = 0
        else:
            # Others calls...
            for stat in cpu_stats._fields:
                if getattr(cpu_stats, stat) is not None:
                    stats[stat] = getattr(cpu_stats, stat) - getattr(self.cpu_stats_old, stat)

        # Save stats to compute next step
        self.cpu_stats_old = cpu_stats

        return stats

    def update_snmp(self):
        """Update CPU stats using SNMP."""

        # Init new stats
        stats = self.get_init_value()

        # Update stats using SNMP
        if self.short_system_name in ('windows', 'esxi'):
            # Windows or VMWare ESXi
            # You can find the CPU utilization of windows system by querying the oid
            # Give also the number of core (number of element in the table)
            try:
                cpu_stats = self.get_stats_snmp(snmp_oid=snmp_oid[self.short_system_name],
                                                bulk=True)
            except KeyError:
                self.reset()

            # Iter through CPU and compute the idle CPU stats
            stats['nb_log_core'] = 0
            stats['idle'] = 0
            for c in cpu_stats:
                if c.startswith('percent'):
                    stats['idle'] += float(cpu_stats['percent.3'])
                    stats['nb_log_core'] += 1
            if stats['nb_log_core'] > 0:
                stats['idle'] = stats['idle'] / stats['nb_log_core']
            stats['idle'] = 100 - stats['idle']
            stats['total'] = 100 - stats['idle']

        else:
            # Default behavor
            try:
                stats = self.get_stats_snmp(
                    snmp_oid=snmp_oid[self.short_system_name])
            except KeyError:
                stats = self.get_stats_snmp(
                    snmp_oid=snmp_oid['default'])

            if stats['idle'] == '':
                self.reset()
                return self.stats

            # Convert SNMP stats to float
            for key in iterkeys(stats):
                stats[key] = float(stats[key])
            stats['total'] = 100 - stats['idle']

        return stats

    def update_views(self):
        """Update stats views."""
        # Call the father's method
        super(Plugin, self).update_views()

        # Add specifics informations
        # Alert and log
        for key in ['user', 'system', 'iowait', 'total']:
            if key in self.stats:
                self.views[key]['decoration'] = self.get_alert_log(self.stats[key], header=key)
        # Alert only
        for key in ['steal']:
            if key in self.stats:
                self.views[key]['decoration'] = self.get_alert(self.stats[key], header=key)
        # Alert only but depend on Core number
        for key in ['ctx_switches']:
            if key in self.stats:
                self.views[key]['decoration'] = self.get_alert(self.stats[key], maximum=100 * self.stats['cpucore'], header=key)
        # Optional
        for key in ['nice', 'irq', 'idle', 'steal', 'ctx_switches', 'interrupts', 'soft_interrupts', 'syscalls']:
            if key in self.stats:
                self.views[key]['optional'] = True

    def msg_curse(self, args=None, max_width=None):
        """Return the list to display in the UI."""
        # Init the return message
        ret = []

        # Only process if stats exist and plugin not disable
        if not self.stats or self.args.percpu or self.is_disabled():
            return ret

        # If user stat is not here, display only idle / total CPU usage (for
        # exemple on Windows OS)
        idle_tag = 'user' not in self.stats

        # First line
        # Total + (idle) + ctx_sw
        msg = '{}'.format('CPU')
        ret.append(self.curse_add_line(msg, "TITLE"))
        trend_user = self.get_trend('user')
        trend_system = self.get_trend('system')
        if trend_user is None or trend_user is None:
            trend_cpu = None
        else:
            trend_cpu = trend_user + trend_system
        msg = ' {:4}'.format(self.trend_msg(trend_cpu))
        ret.append(self.curse_add_line(msg))
        # Total CPU usage
        msg = '{:5.1f}%'.format(self.stats['total'])
        ret.append(self.curse_add_line(
            msg, self.get_views(key='total', option='decoration')))
        # Idle CPU
        if 'idle' in self.stats and not idle_tag:
            msg = '  {:8}'.format('idle:')
            ret.append(self.curse_add_line(msg, optional=self.get_views(key='idle',
                                                                        option='optional')))
            msg = '{:5.1f}%'.format(self.stats['idle'])
            ret.append(self.curse_add_line(msg, optional=self.get_views(key='idle',
                                                                        option='optional')))
        # ctx_switches
        ret.extend(self.curse_add_stat('ctx_switches', width=15, header='  '))

        # Second line
        # user|idle + irq + interrupts
        ret.append(self.curse_new_line())
        # User CPU
        if not idle_tag:
            ret.extend(self.curse_add_stat('user', width=15))
        elif 'idle' in self.stats:
            ret.extend(self.curse_add_stat('idle', width=15))
        # IRQ CPU
        ret.extend(self.curse_add_stat('irq', width=15, header='  '))
        # interrupts
        ret.extend(self.curse_add_stat('interrupts', width=15, header='  '))

        # Third line
        # system|core + nice + sw_int
        ret.append(self.curse_new_line())
        # System CPU
        if not idle_tag:
            ret.extend(self.curse_add_stat('system', width=15))
        else:
            ret.extend(self.curse_add_stat('core', width=15))
        # Nice CPU
        ret.extend(self.curse_add_stat('nice', width=15, header='  '))
        # soft_interrupts
        ret.extend(self.curse_add_stat('soft_interrupts', width=15, header='  '))

        # Fourth line
        # iowat + steal + syscalls
        ret.append(self.curse_new_line())
        # IOWait CPU
        ret.extend(self.curse_add_stat('iowait', width=15))
        # Steal CPU usage
        ret.extend(self.curse_add_stat('steal', width=15, header='  '))
        # syscalls: number of system calls since boot. Always set to 0 on Linux. (do not display)
        if not LINUX:
            ret.extend(self.curse_add_stat('syscalls', width=15, header='  '))

        # Return the message with decoration
        return ret
