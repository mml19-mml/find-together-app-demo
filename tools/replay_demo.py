"""Generate an explicitly simulated output for framework demonstrations."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.domain import Monitor,SearchEvent
m=Monitor();t=datetime(2026,1,1,tzinfo=timezone.utc);records=[]
for i,loss in enumerate([.05,.15,10.5]+[.05]*31):
    records.append({'sample':i,'loss':loss,**m.observe((t+timedelta(minutes=i)).isoformat(),loss,.1)})
event=SearchEvent();actions=[]
for action in ['publish','escalate','report_clue','confirm_identity','confirm_pickup']:
    actions.append({'action':action,**event.act(action)})
result={'mode':'mock','model_loaded':False,'description':'Fixed synthetic scores for state-machine demonstration; not LSTM output.',
        'records':records,'event_actions':actions,'feedback':m.feedback('confirmed_normal')}
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('examples/demo_output.json')
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'MOCK output written to {out}; model_loaded=False')
