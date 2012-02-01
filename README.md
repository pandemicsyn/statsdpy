# statsdpy #

Simple event based [statsd](http://github.com/etsy/statsd) implementation written in python using [eventlet](http://eventlet.net). 
Its a work in progress but the basics are there.

### Configuration ###

statsdpy sample config:

    [main]
    #graphite host and port to connect too.
    #graphite_host = 127.0.0.1
    #graphite_port = 2003
    #address and port we should listen for udp packets on
    #listen_addr = 127.0.0.1
    #listen_port = 8125
    #Debug mode is enabled by default!
    #debug = true
    #How often to flush stats to graphite 
    #flush_interval = 10
    #calculate XXth percentile
    #percent_threshold = 90
    #accept multiple events per packet
    #combined_events = no

 - Edit the config file to adjust your to your environment.
 - Start the service: `statsdpy-server start --conf=/path/to/your.conf`
 - Fire some udp counter or timer events at statsdpy
 - Check syslog for any errors starting up or processing events
 - Profit!

Its important to note that statsdpy runs in debug mode by default (at least for now). So if you wont be running it in the foreground with the `-f|--foreground` flag you might wanna set `debug = false` in your config. However, running with debug enabled and in the foreground makes it very handy for debuging new statsd clients/events (just dont point it at a valid graphite host).

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

### Combined Events ###

Unlike the original implementation this version can also process multiple events per packet. If the config option "combined_events" is enabled multiple metrics can be combined in a single udp packet. Event's need to be separated by a single #:

    pageload:320|ms#failedlogin:5|c

### Sampling ###

    statusupdate:107|c|@0.1

This counter is being sent sampled every 1/10th of the time.

    404error:3|c|@0.5

This counter is being sampled at a 50% rate.

### Building packages ###

Clone the version you want and build the package with [stdeb](https://github.com/astraw/stdeb "stdeb") (sudo apt-get install stdeb):
    
    git clone git@github.com:pandemicsyn/statsdpy.git statsdpy-0.0.3
    cd statsdlog-0.0.3
    git checkout 0.0.3
    python setup.py --command-packages=stdeb.command bdist_deb
    dpkg -i deb_dist/python-statsdpy_0.0.3-1_all.deb
