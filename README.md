# statsdpy #

Simple event based [statsd](http://github.com/etsy/statsd) implementation written in python using [eventlet](http://eventlet.net) with support for reporting to graphite using the pickle protocol.

### Configuration ###

statsdpy sample config with default options:

    [main]
    #graphite host and port to connect too
    graphite_host = 127.0.0.1
    graphite_port = 2003
    graphite_pickle_port = 2004

    #address and port we should listen for udp packets on
    listen_addr = 127.0.0.1
    listen_port = 8125

    #If you track a large number of metrics you can use the pickle protocol
    pickle_protocol = no
    #max number of metrics to report in one go when using the pickle protocol
    pickle_batch_size = 300

    #enabling debug mode and running in the foreground (with -f) is a great way
    #to debug an app generating new metrics
    debug = no

    #How often to flush stats to graphite
    flush_interval = 10
    #calculate the XXth percentile
    percent_threshold = 90

    # Override the key prefixes and suffixes - see https://github.com/etsy/statsd/blob/master/docs/namespacing.md
    legacy_namespace = False
    global_prefix = stats
    prefix_counter = counters
    prefix_timer = timers
    prefix_gauge = gauges

 - Edit the config file appropriately for your environment
 - Start the service: `statsdpy-server start --conf=/path/to/your.conf`
 - Fire some udp counter, timer, or gauge events at statsdpy
 - Check syslog for any errors starting up or processing events
 - Profit!

### Reporting using the pickle protocol ###

If you track a decent # of metrics you wanna switch to report to graphite using the [pickle protocol](http://graphite.readthedocs.org/en/latest/feeding-carbon.html#the-pickle-protocol). The pickle protocol is more efficient than the the plaintext protocol, and supports sending batches of metrics to carbon in one go. To enable it just set  ``pickle_protocol`` to "yes" in your statsdpy.conf. Optionally, you can also adjust the max number of items per batch that is reported by adjusting the ``pickle_batch_size`` conf option.

### Event Types ###

As with the original statsd implementation from [etsy](https://github.com/etsy/statsd) the following event types are supported:

#### Counter ####

    sitelogins:1|c

Simple counters. Add 1 to the "sitelogins" event bucket. It stays in memory until flushed to graphite as specified by the flush_interval.

    500errors:7|c

Another counter, this time add "7" to the "500errors" event bucket.

#### Timer ####

    pageload:320|ms

The "pageload" event took 320ms to complete this time. statsdpy computes the XXth percentile (as specified in the config), average (mean), lower and upper bounds for the configured flush interval.

#### Gauge (simple arbitrary values)####

    snakes_on_this_mother_farking_plane:12|g

### Combined Events ###

The etsy statsd implementation now supports combined events via seperation by newline. Statsdpy supports this method now as well:

    pageload:320|ms\nfailedlogin:5|c

### Sampling ###

    statusupdate:107|c|@0.1

This counter is being sent sampled every 1/10th of the time.

    404error:3|c|@0.5

This counter is being sampled at a 50% rate.

### Requirements ###

- eventlet

### Building .deb packages ###

Clone the repo  and build the package with [stdeb](https://github.com/astraw/stdeb "stdeb") (sudo apt-get install python-stdeb):

    git clone git@github.com:pandemicsyn/statsdpy.git
    cd statsdpy
    python setup.py --command-packages=stdeb.command bdist_deb
    dpkg -i deb_dist/python-statsdpy_0.0.X-1_all.deb

### Installation via setup.py ###

- ``git clone git@github.com:pandemicsyn/statsdpy.git``
- ``cd statsdpy``
- ``python setup.py install``
- Copy the sample config to /etc/statsdpy/statsdpy.conf
- Edit /etc/statsdpy/statsdpy.conf as required for your environment
- Start statsdpy ``/usr/bin/statsdpy-server --conf=/etc/statsdpy/statsdpy.conf start``
- Optionally, a basic init script is provided as etc/statsdpy/statsdpy.init
