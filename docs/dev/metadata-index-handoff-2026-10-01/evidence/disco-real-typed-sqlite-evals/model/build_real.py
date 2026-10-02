from pathlib import Path
import json, os, resource, signal, threading, time
from typed_real import build
ROOT=Path('/private/tmp/disco-real-typed-sqlite-20261001/model')
LIMIT=512*1024*1024
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120 second build cap')))
signal.alarm(120)
def watch():
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > LIMIT:
            os._exit(91)
        time.sleep(.2)
threading.Thread(target=watch,daemon=True).start()
receipt=build('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite', ROOT/'real-typed.sqlite')
receipt['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
receipt['caps']={'process_seconds':120,'process_rss_bytes':LIMIT}
(ROOT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({key:receipt[key] for key in ('build_and_verify_seconds','original_bytes','indexed_bytes','added_bytes','peak_rss_bytes','core_safe','wide_numeric_fields')}),flush=True)
