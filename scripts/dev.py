#!/usr/bin/env python3
"""Own the processes we launch, leave other services alone, preserve all secrets."""
import os
import socket
import subprocess
import sys
import time
import webbrowser
import hashlib
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def listening(port):
    with socket.socket() as s:
        s.settimeout(.25); return s.connect_ex(('127.0.0.1',port))==0

def main():
    os.chdir(ROOT); (ROOT/'data').mkdir(exist_ok=True)
    os.environ['NEXT_TELEMETRY_DISABLED']='1'
    python=ROOT/'.venv/bin/python'
    if not python.exists(): print('Create the Python 3.12 virtual environment and install requirements-app.txt. See README.');return 1
    if not (ROOT/'frontend/node_modules').is_dir():
        subprocess.run(['npm','ci','--prefix','frontend','--cache',str(ROOT/'data/npm-cache')],check=True)
    production='--production' in sys.argv
    if production and not listening(3000):
        frontend=ROOT/'frontend'
        files=sorted(p for p in frontend.rglob('*') if p.is_file() and not any(part in ('node_modules','.next','.next-acceptance','.next-selection-acceptance') for part in p.relative_to(frontend).parts) and p.suffix in ('.json','.mjs','.ts','.tsx','.css','.svg'))
        signature=hashlib.sha256(b''.join(str(p.relative_to(frontend)).encode()+p.read_bytes() for p in files)).hexdigest()
        stamp=ROOT/'data/frontend_build.sha256'
        if not (frontend/'.next/BUILD_ID').exists() or not stamp.exists() or stamp.read_text()!=signature:
            print('Preparing TraderX for launch. The first build may take a minute.',flush=True)
            subprocess.run(['npm','run','build'],cwd=frontend,check=True)
            stamp.write_text(signature)
    subprocess.run([str(python),'-m','alembic','upgrade','head'],check=True)
    redis=ROOT/'data/redis-stable/src/redis-server'
    processes=[]; logs=[]
    if redis.exists() and not listening(6379):
        stream=(ROOT/'data/redis.log').open('a');logs.append(stream)
        processes.append(subprocess.Popen([str(redis),'--bind','127.0.0.1','--port','6379','--protected-mode','yes','--locale-collate','C','--save','','--appendonly','no'],stdout=stream,stderr=stream,env={**os.environ,'LC_ALL':'C','LANG':'C'},start_new_session=True))
    for name,port,args,cwd in [('backend',8000,[str(python),'-m','uvicorn','backend.api.main:app','--host','127.0.0.1','--port','8000','--no-access-log'],ROOT),
                               ('frontend',3000,['npm','run','start' if production else 'dev'],ROOT/'frontend')]:
        if listening(port):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health',timeout=10) as response:
                    import json
                    health=json.load(response)
                    if health.get('execution') not in ('internal_paper_only','internal_and_alpaca_paper') or health.get('live_trading') is not False:raise ValueError()
            except Exception:raise RuntimeError(f'Port {port} is occupied by an unverified service; close it before launching TraderX.') from None
            print(f'{name}: port {port} already active; using existing local service.');continue
        stream=(ROOT/f'data/{name}.log').open('a');logs.append(stream)
        processes.append(subprocess.Popen(args,cwd=cwd,stdout=stream,stderr=stream,start_new_session=True))
    print('TraderX: http://localhost:3000\nBackend: http://localhost:8000\nAPI docs: http://localhost:8000/docs\nLive trading disabled. AI defaults to off. Logs: data/.\nKeep this window open. Ctrl-C stops services started here.')
    try:
        for _ in range(60):
            if listening(3000) and listening(8000):break
            if any(p.poll() is not None for p in processes):raise RuntimeError('Service exited; inspect data logs')
            time.sleep(1)
        else:raise RuntimeError('Startup timed out; inspect data/backend.log and data/frontend.log')
        if os.environ.get('TRADERX_NO_BROWSER') != '1':webbrowser.open('http://localhost:3000')
        while all(p.poll() is None for p in processes):time.sleep(2)
    except KeyboardInterrupt:pass
    finally:
        import signal
        for p in processes:
            if p.poll() is None:
                try: os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError: p.terminate()
        for f in logs:f.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
