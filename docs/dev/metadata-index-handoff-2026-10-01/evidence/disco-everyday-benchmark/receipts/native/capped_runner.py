import runpy,signal,sys

def cap(signum,frame):
    signal.alarm(0)
    raise TimeoutError('Experiment exceeded the 480 second run budget; preserve partial receipt and stop owned database')

signal.signal(signal.SIGALRM,cap)
signal.alarm(480)
script=sys.argv.pop(1)
runpy.run_path(script,run_name='__main__')
