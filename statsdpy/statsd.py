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

    def __init__(self, conf):
        TRUE_VALUES = set(('true', '1', 'yes', 'on', 't', 'y'))
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
        self.pickle_proto = conf.get('pickle_protocol', 'no') in TRUE_VALUES
        self.max_batch_size = int(conf.get('pickle_batch_size', '300'))
        self.listen_addr = conf.get('listen_addr', '127.0.0.1')
        self.listen_port = int(conf.get('listen_port', 8125))
        self.debug = conf.get('debug', 'no') in TRUE_VALUES
        self.flush_interval = int(conf.get('flush_interval', 10))
        self.pct_threshold = int(conf.get('percent_threshold', 90))
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

    def _get_batches(self, items):
        """given a list yield list at most self.max_batch_size in size"""
        for i in xrange(0, len(items), self.max_batch_size):
            yield items[i:i + self.max_batch_size]

    def report_stats(self, payload):
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
            with eventlet.Timeout(5, True) as timeout:
                graphite = socket.socket()
                graphite.connect(self.graphite_addr)
                graphite.sendall(payload)
                graphite.close()
        except Exception as err:
            self.logger.critical("error connecting to graphite: %s" % err)
            if self.debug:
                print "error connecting to graphite: %s" % err

    def stats_flush(self):
        """
        Periodically flush stats to graphite
        """
        while True:
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

    def pickle_payload(self):
        """obtain stats payload in batches of pickle format"""
        tstamp = int(time.time())
        payload = []
        for item in self.counters:
            stats = (tstamp, self.counters[item] / self.flush_interval)
            payload.append(("stats.%s" % item, stats))
            stats = (tstamp, self.counters[item])
            payload.append(("stats_counts.%s" % item, stats))
            self.counters[item] = 0
        for key in self.timers:
            if len(self.timers[key]) > 0:
                self.timers[key].sort()
                count = len(self.timers[key])
                low = min(self.timers[key])
                high = max(self.timers[key])
                total = sum(self.timers[key])
                mean = low
                max_threshold = high
                tstamp = int(time.time())
                if count > 1:
                    threshold_index = \
                        int((self.pct_threshold / 100.0) * count)
                    max_threshold = self.timers[key][threshold_index - 1]
                    mean = total / count
                payload.append(("stats.timers.%s.mean" % key, (tstamp, mean)))
                payload.append(("stats.timers.%s.upper" % key, (tstamp, high)))
                payload.append(("stats.timers.%s.upper_%d" %
                               (key, self.pct_threshold),
                               (tstamp, max_threshold)))
                payload.append(("stats.timers.%s.lower" % key, (tstamp, low)))
                payload.append(("stats.timers.%s.count" % key, (tstamp,
                                                                count)))
                payload.append(("stats.timers.%s.mean" % key, (tstamp, total)))
                self.timers[key] = []
        for key in self.gauges:
            payload.append(("stats.gauges.%s" % key, (tstamp,
                                                      self.gauges[key])))
            self.gauges[key] = 0
        if payload:
            batched_payload = []
            for batch in self._get_batches(payload):
                if self.debug:
                    print "pickling batch: %s" % batch
                serialized_data = pickle.dumps(batch, protocol=-1)
                length_prefix = struct.pack("!L", len(serialized_data))
                batched_payload.append(length_prefix + serialized_data)
            return batched_payload
        else:
            return None

    def plain_payload(self):
        """obtain stats payload in plaintext format"""
        tstamp = int(time.time())
        payload = []
        for item in self.counters:
            stats = 'stats.%s %s %s\n' % \
                    (item, self.counters[item] / self.flush_interval,
                     tstamp)
            stats_counts = 'stats_counts.%s %s %s\n' % \
                           (item, self.counters[item], tstamp)
            payload.append(stats)
            payload.append(stats_counts)
            self.counters[item] = 0
        for key in self.timers:
            if len(self.timers[key]) > 0:
                self.timers[key].sort()
                count = len(self.timers[key])
                low = min(self.timers[key])
                high = max(self.timers[key])
                total = sum(self.timers[key])
                mean = low
                max_threshold = high
                tstamp = int(time.time())
                if count > 1:
                    threshold_index = int((self.pct_threshold / 100.0) * count)
                    max_threshold = self.timers[key][threshold_index - 1]
                    mean = total / count
                payload.append("stats.timers.%s.mean %d %d\n" %
                               (key, mean, tstamp))
                payload.append("stats.timers.%s.upper %d %d\n" %
                               (key, high, tstamp))
                payload.append("stats.timers.%s.upper_%d %d %d\n" %
                               (key, self.pct_threshold, max_threshold,
                                tstamp))
                payload.append("stats.timers.%s.lower %d %d\n" %
                               (key, low, tstamp))
                payload.append("stats.timers.%s.count %d %d\n" %
                               (key, count, tstamp))
                payload.append("stats.timers.%s.total %d %d\n" %
                               (key, total, tstamp))
                self.timers[key] = []
        for key in self.gauges:
            payload.append("stats.gauges.%s %d %d\n" %
                           (key, self.gauges[key], int(time.time())))
            self.gauges[key] = 0
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

    def decode_recvd(self, data):
        """
        Decode and process the data from a received event.

        :param data: Data to decode and process.
        """
        bits = data.split(':')
        if len(bits) == 2:
            key = self.keycheck.sub('_', bits[0])
            print "got key: %s" % key
            fields = bits[1].split("|")
            field_count = len(fields)
            if field_count >= 2:
                if fields[1] == "ms":
                    self.process_timer(key, fields)
                elif fields[1] == "c":
                    self.process_counter(key, fields)
                elif fields[1] == "g":
                    self.process_gauge(key, fields)
                else:
                    if self.debug:
                        print "error: unsupported stats type"
                        print "key -> %s\nfields ->%s" % (key, fields)
            else:
                if self.debug:
                    print "error: not enough fields received"
        else:
            if self.debug:
                print "error: invalid request"

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
                        self.decode_recvd(metric)


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
        statsd.run()
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
