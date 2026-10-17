"""Credential-free, bounded trusted interpreter. Never executes proposal code."""
import json, os, resource, sys
from pathlib import Path

def guard(workspace):
    root=Path(workspace).resolve()
    def audit(event,args):
        if event.startswith(('socket.connect','socket.bind','subprocess.Popen','os.system','os.exec','os.spawn')):
            raise PermissionError('Research worker has no network or process tools')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve()
            if path.name.startswith('.env') or 'secrets' in path.parts or path.suffix in ('.db','.sqlite','.sqlite3','.pem','.key'):
                raise PermissionError('Protected storage unavailable to research worker')
            mode=args[1] or '';flags=args[2] or 0
            writing=any(c in str(mode) for c in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)
            if writing and not path.is_relative_to(root):raise PermissionError('Research writes restricted to disposable workspace')
    sys.addaudithook(audit)

def main():
    workspace=Path.cwd();guard(workspace)
    request=json.loads((workspace/'request.json').read_text());budget=request['budget']
    resource.setrlimit(resource.RLIMIT_CPU,(budget['cpu_seconds'],budget['cpu_seconds']+1))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    try:os.nice(10)
    except OSError:pass
    from threadpoolctl import threadpool_limits
    from backend.research.autonomous.numerics import run
    try:
        with threadpool_limits(limits=1):result={'status':'EVALUATED','result':run(request['spec'],request['snapshot'])}
    except Exception as exc:
        reasons={'insufficient_data','poor_calibration','No features meet training-only coverage requirements'}
        result={'status':'REJECTED','reason':str(exc) if str(exc) in reasons else 'invalid_or_insufficient_data','error_type':type(exc).__name__}
    (workspace/'result.json').write_text(json.dumps(result,allow_nan=False))

if __name__=='__main__':main()
