"""Supervised single-process compute with a clean environment and disposable input."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
def clean_environment(workspace):
    return {'PATH':os.defpath,'HOME':str(workspace),'TMPDIR':str(workspace),'LANG':'en_US.UTF-8',
            'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}

def execute(spec,snapshot,budget,root,paused=lambda:False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='run-',dir=root));started=time.monotonic();peak=0;process=None
    try:
        request=json.dumps({'spec':spec,'snapshot':snapshot,'budget':budget},allow_nan=False)
        if len(request.encode())>16*1024**2:return {'status':'REJECTED','reason':'input_storage_budget'}
        (work/'request.json').write_text(request)
        bootstrap='import sys; sys.path.insert(0,'+repr(str(ROOT))+'); from backend.research.autonomous.worker import main; main()'
        process=subprocess.Popen([sys.executable,'-I','-B','-c',bootstrap],cwd=work,env=clean_environment(work),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        reason=None
        while process.poll() is None:
            if paused():reason='paused_by_owner'
            elif time.monotonic()-started>budget['wall_seconds']:reason='wall_time_budget'
            else:
                try:
                    rss=int(subprocess.check_output(['/bin/ps','-o','rss=','-p',str(process.pid)],timeout=2).strip() or 0)*1024
                    peak=max(peak,rss)
                    if rss>budget['memory_mb']*1024**2:reason='memory_budget'
                except (subprocess.SubprocessError,ValueError):
                    if process.poll() is None:reason='resource_monitor_unavailable'
            if reason:process.kill();process.wait();break
            time.sleep(.2)
        path=work/'result.json'
        if reason:result={'status':'REJECTED','reason':reason}
        elif process.returncode or not path.exists():result={'status':'REJECTED','reason':'worker_or_cpu_limit'}
        elif path.stat().st_size>2*1024**2:result={'status':'REJECTED','reason':'output_storage_budget'}
        else:result=json.loads(path.read_text())
        return {**result,'resources':{'wall_seconds':round(time.monotonic()-started,3),'peak_rss_bytes':peak,'worker_exit_code':process.returncode,'cpu_limit_seconds':budget['cpu_seconds'],'credential_environment':False,'temporary_files_retained':False}}
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait()
        shutil.rmtree(work)

def clean_abandoned(root,older_than=300):
    root=Path(root);removed=0
    if root.exists():
        for path in root.glob('run-*'):
            if not path.is_symlink() and path.is_dir() and time.time()-path.stat().st_mtime>older_than:
                shutil.rmtree(path);removed+=1
    return removed
