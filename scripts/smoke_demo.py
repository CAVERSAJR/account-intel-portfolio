"""One explicit, bounded live API check. Run only when a model test is intended."""
from pathlib import Path
import argparse, json, time, urllib.request, urllib.error

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--account',default='advent_international')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    data=json.loads((root/'workspace/data.json').read_text(encoding='utf-8'))
    account=next(a for a in data['accounts'] if a['id']==args.account)
    evidence=[{k:s[k] for k in ('id','text','date','kind')} for s in data['sources'] if s['accountId']==account['id']]
    payload={'account_id':account['id'],'as_of':data['asOf'],'evidence':evidence,'context':{k:account[k] for k in ('name','strategy','fundContext')}}
    payload['context']['product']='LP obligation tracking'
    request=urllib.request.Request('http://127.0.0.1:8767/api/plan',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=35) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        try:message=json.load(error).get('error','Request rejected')
        except ValueError:message='Request rejected'
        raise SystemExit(json.dumps({'success':False,'status':error.code,'error':message}))
    out={'success':True,'account_id':account['id'],'client_elapsed_ms':round((time.perf_counter()-started)*1000),'response':result,'evidence_ids':[s['id'] for s in evidence]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'success':True,'account_id':account['id'],'elapsed_ms':out['client_elapsed_ms'],'provider':result.get('provider'),'model':result.get('model'),'usage':result.get('usage'),'output':str(args.output)}))
