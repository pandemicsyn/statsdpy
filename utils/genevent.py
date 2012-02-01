from eventlet.green import socket
from eventlet import sleep
from datetime import datetime

tosend = 10000

def send_event(payload):
    addr = ('127.0.0.1', 8125)
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.sendto(payload, addr)

combined_events = ["testitem:1|c#test2:4|c", "timertest1:200|ms#testitem1:1|c|@0.5"]
transform_test = 'te$t_key !fix{\)\/?@#%th\'is^&*be"ok'
good_events = ['testitem:1|c', 'testitem:1|c|@0.5','timertest:300|ms', 'timertest:400|ms', 'timertest:500|ms']
crap_events = ['.', ' ', ':', ' : |c', 'baditem:1|k', 'baditem:1|c|@',
    'baditem:1|c|@wtf', 'baditem:1|c|@05f.6', 'badtimer:5.0f|ms']

def bench(payload, limit):
    for i in xrange(1, limit):
        send_event(payload) 

print "--> %s" % datetime.now()
for event in combined_events:
    print "Sending [%s]" % event
    send_event(event)
    sleep(.5)
sleep(2)
print "--> %s" % datetime.now()
for event in good_events:
    print "Sending [%s]" % event
    send_event(event)
    sleep(.5)
for event in crap_events:
    print "Sending crap [%s]" % event
    send_event(event)
    sleep(.5)
print "Sending transform [%s]" % transform_test
send_event(transform_test)

print "--> starting benchmark in 5 seconds"
sleep(5)
print "--> starting counter benchmark %s" % datetime.now()
bench(good_events[1], tosend)
print "sent %d packets" % tosend
print "-- counter benchmark complete %s" % datetime.now()
print "--> starting timer benchmark %s" % datetime.now()
bench(good_events[2], tosend)
print "sent %d packets" % tosend
print "-- timer benchmark complete %s" % datetime.now()
