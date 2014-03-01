import eventlet
from eventlet.green import socket
from statsdpy.daemonutils import Daemon, readconf
from logging.handlers import SysLogHandler
import logging
from sys import maxint
import optparse
import cPickle as pickle
import struct
import time
import sys
import os
import re


class StatsdServer(object):
    TRUE_VALUES = set(('true', '1', 'yes', 'on', 't', 'y'))

    def __init__(self, conf):
        self.logger = logging.getLogger('statsdpy')
        self.logger.setLevel(logging.INFO)
        self.syslog = SysLogHandler(address='/dev/log')
        self.formatter = logging.Formatter('%(name)s: %(message)s')
        self.syslog.setFormatter(self.formatter)
        self.logger.addHandler(self.syslog)
        self.conf = conf
        self.graphite_host = conf.get('graphite_host', '127.0.0.1')
        self.graphite_port = int(conf.get('graphite_port', '2003'))
        self.graphite_pport = int(conf.get('graphite_pickle_port', '2004'))
        self.graphite_timeout = int(conf.get('graphite_timeout', '5'))
        self.pickle_proto = conf.get('pickle_protocol') in self.TRUE_VALUES
        self.max_batch_size = int(conf.get('pickle_batch_size', '300'))
        self.listen_addr = conf.get('listen_addr', '127.0.0.1')
        self.listen_port = int(conf.get('listen_port', 8125))
        self.debug = conf.get('debug') in self.TRUE_VALUES
        self.flush_interval = int(conf.get('flush_interval', 10))
        self.pct_threshold = int(conf.get('percent_threshold', 90))
        self.threshold_numerator = float(self.pct_threshold / 100.0)
        if self.pickle_proto:
            self.graphite_addr = (self.graphite_host, self.graphite_pport)
        else:
            self.graphite_addr = (self.graphite_host, self.graphite_port)
        self.keycheck = re.compile(r'\s+|/|[^a-zA-Z_\-0-9\.]')
        self.ratecheck = re.compile('^@([\d\.]+)')
        self.counters = {}
        self.timers = {}
        self.gauges = {}
        self.stats_seen = 0
        self.processors = {
            'g': self.process_gauge,
            'c': self.process_counter,
            'ms': self.process_timer,
        }
        self._set_prefixes(conf)

    def _set_prefixes(self, conf):
        """Set the graphite key prefixes

        :param dict conf: The configuration data

        """
        if conf.get('legacy_namespace', 'y') in self.TRUE_VALUES:
            self.count_prefix = 'stats_counts'
            self.count_suffix = ''
            self.gauge_prefix = 'stats.gauges'
            self.timer_prefix = 'stats.timers'
            self.rate_prefix = 'stats'
            self.rate_suffix = ''
        else:
            global_prefix = conf.get('global_prefix', 'stats')
            self.count_prefix = '%s.%s' % (global_prefix,
                                           conf.get('prefix_counter',
                                                    'counters'))
            self.count_suffix = '.count'
            self.gauge_prefix = '%s.%s' % (global_prefix,
                                           conf.get('prefix_gauge', 'gauges'))
            self.timer_prefix = '%s.%s' % (global_prefix,
                                           conf.get('prefix_timer', 'timers'))
            self.rate_prefix = self.count_prefix
            self.rate_suffix = '.rate'

    def _get_batches(self, items):
        """given a list yield list at most self.max_batch_size in size"""
        for i in xrange(0, len(items), self.max_batch_size):
            yield items[i:i + self.max_batch_size]

    def report_stats(self, payload, is_retry=False):
        """
        Send data to graphite host

        :param payload: Data to send to graphite
        """
        if self.debug:
            if self.pickle_proto:
                print "reporting pickled stats"
            else:
                print "reporting stats -> {\n%s}" % payload
        try:
            graphite = socket.socket()
            with eventlet.Timeout(self.graphite_timeout, True):
                graphite.connect(self.graphite_addr)
                graphite.sendall(payload)
                graphite.close()
        except eventlet.timeout.Timeout:
            self.logger.critical("Timeout sending to graphite")
            if self.debug:
                print "Timeout talking to graphite"
            if not is_retry:
                self.logger.critical('Attempting 1 retry!')
                self.report_stats(payload, is_retry=True)
            else:
                self.logger.critical('Already retried once, giving up')
        except Exception as err:
            self.logger.critical("error connecting to graphite: %s" % err)
            if self.debug:
                print "error connecting to graphite: %s" % err
        finally:
            try:
                graphite.close()
            except Exception:
                pass

    def stats_flush(self):
        """
        Periodically flush stats to graphite
        """
        while True:
            try:
                eventlet.sleep(self.flush_interval)
                if self.debug:
                    print "seen %d stats so far." % self.stats_seen
                    print "current counters: %s" % self.counters
                if self.pickle_proto:
                    payload = self.pickle_payload()
                    if payload:
                        for batch in payload:
                            self.report_stats(batch)
                else:
                    payload = self.plain_payload()
                    if payload:
                        self.report_stats(payload)
            except: # safety net
                self.logger.critical('Encountered error in stats_flush loop')

    def pickle_payload(self):
        """obtain stats payload in batches of pickle format"""
        tstamp = int(time.time())
        payload = []

        for item in self.counters:
            payload.append(("%s.%s%s" % (self.rate_prefix, item,
                                         self.rate_suffix),
                            (tstamp,
                             self.counters[item] / self.flush_interval)))
            payload.append(("%s.%s%s" % (self.count_prefix, item,
                                         self.count_suffix),
                            (tstamp, self.counters[item])))
            self.counters[item] = 0

        for key in self.timers:
            if len(self.timers[key]) > 0:
                self.process_timer_key(key, tstamp, payload)
                self.timers[key] = []

        for key in self.gauges:
            payload.append(("%s.%s" % (self.gauge_prefix, key),
                            (tstamp, self.gauges[key])))
            self.gauges[key] = 0

        if payload:
            batched_payload = []
            for batch in self._get_batches(payload):
                if self.debug:
                    print "pickling batch: %r" % batch
                serialized_data = pickle.dumps(batch, protocol=-1)
                length_prefix = struct.pack("!L", len(serialized_data))
                batched_payload.append(length_prefix + serialized_data)
            return batched_payload
        return None

    def plain_payload(self):
        """obtain stats payload in plaintext format"""
        tstamp = int(time.time())
        payload = []
        for item in self.counters:
            payload.append('%s.%s%s %s %s\n' % (self.rate_prefix,
                                                item,
                                                self.rate_suffix,
                                                self.counters[item] /
                                                self.flush_interval,
                                                tstamp))
            payload.append('%s.%s%s %s %s\n' % (self.count_prefix,
                                                item,
                                                self.count_suffix,
                                                self.counters[item],
                                                tstamp))
            self.counters[item] = 0

        for key in self.timers:
            if len(self.timers[key]) > 0:
                self.process_timer_key(key, tstamp, payload)
                self.timers[key] = []

        for key in self.gauges:
            payload.append("%s.%s %d %d\n" % (self.gauge_prefix, key,
                                              self.gauges[key], tstamp))
            self.gauges[key] = 0

        if self.debug:
            print payload

        if payload:
            return "".join(payload)
        else:
            return None

    def process_gauge(self, key, fields):
        """
        Process a received gauge event

        :param key: Key of timer
        :param fields: Received fields
        """
        try:
            self.gauges[key] = float(fields[0])
            if self.stats_seen >= maxint:
                self.logger.info("hit maxint, reset seen counter")
                self.stats_seen = 0
            self.stats_seen += 1
        except Exception as err:
            self.logger.info("error decoding gauge event: %s" % err)
            if self.debug:
                print "error decoding gauge event: %s" % err

    def process_timer(self, key, fields):
        """
        Process a received timer event

        :param key: Key of timer
        :param fields: Received fields
        """
        try:
            if key not in self.timers:
                self.timers[key] = []
            self.timers[key].append(float(fields[0]))
            if self.stats_seen >= maxint:
                self.logger.info("hit maxint, reset seen counter")
                self.stats_seen = 0
            self.stats_seen += 1
        except Exception as err:
            self.logger.info("error decoding timer event: %s" % err)
            if self.debug:
                print "error decoding timer event: %s" % err

    def process_counter(self, key, fields):
        """
        Process a received counter event

        :param key: Key of counter
        :param fields: Received fields
        """
        sample_rate = 1.0
        try:
            if len(fields) is 3:
                if self.ratecheck.match(fields[2]):
                    sample_rate = float(fields[2].lstrip("@"))
                else:
                    raise Exception("bad sample rate.")
            counter_value = float(fields[0] or 1) * (1 / float(sample_rate))
            if key not in self.counters:
                self.counters[key] = 0
            self.counters[key] += counter_value
            if self.stats_seen >= maxint:
                self.logger.info("hit maxint, reset seen counter")
                self.stats_seen = 0
            self.stats_seen += 1
        except Exception as err:
            self.logger.info("error decoding counter event: %s" % err)
            if self.debug:
                print "error decoding counter event: %s" % err

    def process_timer_key(self, key, tstamp, stack, pickled=False):
        """Append the plain text graphite

        :param str key: The timer key to process
        :param int tstamp: The timestamp for the data point
        :param list stack: The stack of metrics to append the output to

        """
        self.timers[key].sort()
        values = {'count': len(self.timers[key]),
                  'low': min(self.timers[key]),
                  'high': max(self.timers[key]),
                  'total': sum(self.timers[key])}
        values['mean'] = values['low']
        nth_percentile = 'upper_%i' % self.pct_threshold
        values[nth_percentile] = values['high']

        if values['count']:
            threshold_idx = int(self.threshold_numerator * values['count']) - 1
            values[nth_percentile] = self.timers[key][threshold_idx]
            values['mean'] = float(values['total']) / float(values['count'])

        for metric in values:
            if pickled:
                stack.append(("%s.%s.%s" % (self.timer_prefix, key, metric),
                              (tstamp, values[metric])))
            else:
                stack.append("%s.%s.%s %s %s\n" % (self.timer_prefix,
                                                   key,
                                                   metric,
                                                   values[metric],
                                                   tstamp))

    def decode_recvd(self, data):
        """
        Decode and process the data from a received event.

        :param data: Data to decode and process.
        """
        bits = data.split(':')
        if len(bits) == 2:
            key = self.keycheck.sub('_', bits[0])
            fields = bits[1].split("|")
            field_count = len(fields)
            if field_count >= 2:
                processor = self.processors.get(fields[1])
                if processor:
                    if self.debug:
                        print "got key: %s %r" % (key, fields)
                    processor(key, fields)
                else:
                    print "error: unsupported stats type"
                    print "key -> %s\nfields ->%s" % (key, fields)
            else:
                print "error (%s): not enough fields received" % key
        else:
            print "error: invalid request [%s]" % data[:40]

    def run(self):
        eventlet.spawn_n(self.stats_flush)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        addr = (self.listen_addr, self.listen_port)
        sock.bind(addr)
        buf = 8192
        self.logger.info("Listening on %s:%d" % addr)
        if self.debug:
            print "Listening on %s:%d" % addr
        while 1:
            data, addr = sock.recvfrom(buf)
            if not data:
                break
            else:
                for metric in data.splitlines():
                    if metric:
                        try:
                            self.decode_recvd(metric)
                        except: # safety net
                            self.logger.critical("exception in decode_recvd")
                            pass


class Statsd(Daemon):

    def run(self, conf):
        server = StatsdServer(conf)
        server.run()


def run_server():
    usage = '''
    %prog start|stop|restart [--conf=/path/to/some.conf] [--foreground|-f]
    '''
    args = optparse.OptionParser(usage)
    args.add_option('--foreground', '-f', action="store_true",
                    help="Run in foreground")
    args.add_option('--conf', default="./statsd.conf",
                    help="path to config. default = ./statsd.conf")
    options, arguments = args.parse_args()

    if len(sys.argv) <= 1:
        args.print_help()
        sys.exit(1)

    if not os.path.isfile(options.conf):
        print "Couldn't find a config"
        args.print_help()
        sys.exit(1)

    if options.foreground:
        print "Running in foreground."
        conf = readconf(options.conf)
        statsd = StatsdServer(conf['main'])
        try:
            statsd.run()
        except KeyboardInterrupt:
            print ''  # in testing, you'll see "^C<prompt>" w/o this
        sys.exit(0)

    if len(sys.argv) >= 2:
        statsdaemon = Statsd('/tmp/statsd.pid')
        if 'start' == sys.argv[1]:
            conf = readconf(options.conf)
            statsdaemon.start(conf['main'])
        elif 'stop' == sys.argv[1]:
            statsdaemon.stop()
        elif 'restart' == sys.argv[1]:
            statsdaemon.restart()
        else:
            args.print_help()
            sys.exit(2)
        sys.exit(0)
    else:
        args.print_help()
        sys.exit(2)

if __name__ == '__main__':
    run_server()
