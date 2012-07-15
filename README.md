# statsdpy #

Simple event based [statsd](http://github.com/etsy/statsd) implementation written in python using [eventlet](http://eventlet.net). 
Its a work in progress but the basics are there.

### Configuration ###

statsdpy sample config:

    [main]
    #graphite_host = 127.0.0.1
    #graphite_port = 2003
    #graphite_pickle_port = 2004
    #listen_addr = 127.0.0.1
    #listen_port = 8125
    #If you track a large number of metrics you should you should report using
    #graphites pickle protocol. In that case switch this to yes to enable it.
    #pickle_protocol = no
    #max number of metrics to report in one go when using the pickle protocol.
    #pickle_batch_size = 300
    #debug = no
    #flush_interval = 10
    #percent_threshold = 90

 - Edit the config file to adjust your to your environment.
 - Start the service: `statsdpy-server start --conf=/path/to/your.conf`
 - Fire some udp counter, timer, or gauge events at statsdpy
 - Check syslog for any errors starting up or processing events
 - Profit!

Its important to note that statsdpy runs in debug mode by default (at least for now). So if you wont be running it in the foreground with the `-f|--foreground` flag you might wanna set `debug = false` in your config. However, running with debug enabled and in the foreground makes it very handy for debuging new statsd clients/events (just dont point it at a valid graphite host).

### Reporting using the pickle protocol ###

If you track a decent # of metrics you may wish to switch to reporting using Graphites [pickle protocol](http://graphite.readthedocs.org/en/latest/feeding-carbon.html#the-pickle-protocol). The pickle protocol is a much more efficient take on the plaintext protocol, and supports sending batches of metrics to Carbon in one go. To enable it just set  ``pickle_protocol`` to "yes" in your statsdpy.conf. Optionally, you can also adjust the max number of items per batch that is reported by adjusting the ``pickle_batch_size`` conf option.

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

### Building packages ###

Clone the version you want and build the package with [stdeb](https://github.com/astraw/stdeb "stdeb") (sudo apt-get install stdeb):

    git clone git@github.com:pandemicsyn/statsdpy.git statsdpy-0.0.6
    cd statsdpy-0.0.6
    git checkout 0.0.6
    python setup.py --command-packages=stdeb.command bdist_deb
    dpkg -i deb_dist/python-statsdpy_0.0.6-1_all.deb

### Installation via setup.py ###

- ``git clone git@github.com:pandemicsyn/statsdpy.git``
- ``cd statsdpy``
- ``python setup.py install``
- Copy the sample config to /etc/statsdpy/statsdpy.conf
- Edit /etc/statsdpy/statsdpy.conf as required for your environment
- Start statsdpy ``/usr/bin/statsdpy-server --conf=/etc/statsdpy/statsdpy.conf start``
- Optionally, a basic init script is provided as etc/statsdpy/statsdpy.init
