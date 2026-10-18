import json, sys, importlib.util
spec=importlib.util.spec_from_file_location('f', sys.argv[1]); f=importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
def I(n,state='open',total=0,done=0,blk=0):
    return {"number":n,"title":f"t{n}","state":state,"html_url":f"u{n}","assignees":[],"labels":[],"body":"",
            "issue_dependencies_summary":{"blocked_by":blk,"total_blocked_by":blk},"sub_issues_summary":{"total":total,"completed":done}}
data={"repos/o/r/issues/1/sub_issues":[I(2),I(3,total=2,done=1)],
      "repos/o/r/issues/3/sub_issues":[I(4,state='closed'),I(5)],
      "repos/o/r/issues/6/sub_issues":[I(7,state='closed')]}
def gh(args):
    if args[0]=='pr': return []
    if args[0]=='api':
        k=[a for a in args if a.startswith('repos/')][0]; return data.get(k,[])
f.gh=gh; f.blockers_of=lambda r,n: []
import io, contextlib
for argv in (['--repo','o/r','--parent','1','--json'],):
    sys.argv=['x']+argv; buf=io.StringIO()
    with contextlib.redirect_stdout(buf): f.main()
    r=json.loads(buf.getvalue())
    print({k:[n['number'] for n in r[k]] for k in ('ready','split','split_complete','done')}, 'deadlocked',r['deadlocked'])
data["repos/o/r/issues/1/sub_issues"].append(I(6,total=1,done=1))
sys.argv=['x','--repo','o/r','--parent','1','--json']; buf=io.StringIO()
with contextlib.redirect_stdout(buf): f.main()
r=json.loads(buf.getvalue()); print({k:[n['number'] for n in r[k]] for k in ('ready','split','split_complete','done')})
