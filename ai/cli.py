"""Reference train/detect/retrain commands. TensorFlow is optional until invoked."""
import argparse,json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
from .pipeline import CONFIG,FEATURES,read_csv,features,fit_scaler,windows

def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def train(csv_path,out,epochs):
    import numpy as np
    import tensorflow as tf
    rows=read_csv(csv_path)
    if len(rows)<100:raise ValueError('need at least 100 rows for train/calibration/test partitions')
    # Split raw timeline before fitting scaler or building overlapping windows.
    a=int(len(rows)*.6);b=int(len(rows)*.8)
    parts=[rows[:a],rows[a:b],rows[b:]]
    values=[features(x) for x in parts]
    scaler=fit_scaler(values[0][0]);sets=[windows(x[0],scaler)[0] for x in values]
    if any(len(x)<2 for x in sets):raise ValueError('not enough clean windows in one partition')
    tf.keras.utils.set_random_seed(42)
    inp=tf.keras.Input((CONFIG['sequence_length'],len(FEATURES)))
    x=tf.keras.layers.LSTM(32,activation='relu')(inp)
    x=tf.keras.layers.RepeatVector(CONFIG['sequence_length'])(x)
    x=tf.keras.layers.LSTM(32,activation='relu',return_sequences=True)(x)
    out_layer=tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(len(FEATURES)))(x)
    model=tf.keras.Model(inp,out_layer);model.compile(optimizer='adam',loss='mae')
    history=model.fit(sets[0],sets[0],epochs=epochs,batch_size=32,shuffle=False,verbose=1)
    cal=np.mean(abs(model.predict(sets[1],verbose=0)-sets[1]),axis=(1,2))
    threshold=float(np.quantile(cal,.99))
    if not np.isfinite(threshold) or threshold<=0:raise ValueError('invalid learned threshold')
    test=np.mean(abs(model.predict(sets[2],verbose=0)-sets[2]),axis=(1,2))
    target=Path(out)
    if target.exists() and any(target.iterdir()):raise ValueError('use a new empty model version directory')
    target.mkdir(parents=True,exist_ok=True);model.save(target/'model.keras');dump(target/'scaler.json',scaler)
    report={'status':'trained_candidate_not_deployed','source_sha256':sha(csv_path),'created_at':datetime.now(timezone.utc).isoformat(),
            'partition_rows':[len(x) for x in parts],'partition_windows':[len(x) for x in sets],
            'quality_rejected_rows':[x[1] for x in values],'normal_test_alarm_fraction':float(np.mean(test>threshold)),
            'limitation':'Normal-only data cannot measure anomaly recall or prove missing-person detection accuracy.',
            'train_loss':[float(x) for x in history.history['loss']]}
    dump(target/'training_report.json',report)
    dump(target/'manifest.json',{'version':target.name,'framework_version':tf.__version__,'config':CONFIG,'threshold':threshold,
          'features':FEATURES,'files':{'model.keras':sha(target/'model.keras'),'scaler.json':sha(target/'scaler.json')}})
    print(json.dumps({'artifact_dir':str(target),'threshold':threshold,'status':report['status']},indent=2))

def detect(csv_path,bundle,output):
    import numpy as np
    import tensorflow as tf
    from backend.domain import Monitor
    bundle=Path(bundle);manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    if manifest['config']!=CONFIG or manifest['features']!=FEATURES:raise ValueError('preprocessing version mismatch')
    for file,expected in manifest['files'].items():
        if sha(bundle/file)!=expected:raise ValueError('model bundle checksum mismatch')
    rows=read_csv(csv_path);vals,rejected=features(rows);scaler=json.loads((bundle/'scaler.json').read_text())
    seq,indices=windows(vals,scaler)
    if not len(seq):raise ValueError('no complete clean windows')
    model=tf.keras.models.load_model(bundle/'model.keras',compile=False)
    if tuple(model.input_shape[1:])!=(10,5):raise ValueError('model input shape mismatch')
    losses=np.mean(abs(model.predict(seq,verbose=0)-seq),axis=(1,2));monitor=Monitor();result=[];last=-1
    for idx,loss in zip(indices,losses):
        if last>=0 and idx!=last+1:monitor.normal_count=0;monitor.feedback_ready=False
        t=rows[idx][0].isoformat();status=monitor.observe(t,float(loss),manifest['threshold'])
        result.append({'timestamp':t,'loss':float(loss),'threshold':manifest['threshold'],'model_version':manifest['version'],**status});last=idx
    dump(Path(output),{'mode':'model_replay','quality_rejected_rows':rejected,'results':result})
    print(f'Saved {len(result)} detected windows to {output}')

def retrain(original,reviewed,out,epochs):
    import csv,tempfile
    rows=read_csv(original)
    with open(reviewed,encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        required={'timestamp','lat','lon','label','approved_by','approved_for_training'}
        if not required<=set(reader.fieldnames or []):raise ValueError('reviewed data requires labels and approval fields')
        additions=list(reader)
    if not additions or any(x['label']!='confirmed_normal' or not x['approved_by'].strip() or x['approved_for_training'].lower()!='true' for x in additions):
        raise ValueError('only explicitly approved normal data can enter retraining')
    with tempfile.TemporaryDirectory() as temp:
        clean=Path(temp)/'reviewed.csv'
        with clean.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['timestamp','lat','lon']);w.writerows((x['timestamp'],x['lat'],x['lon']) for x in additions)
        new=read_csv(clean);merged={r[0]:r for r in rows}
        for r in new:
            if r[0] in merged and r[1:]!=merged[r[0]][1:]:raise ValueError('conflicting coordinates at the same timestamp')
            merged[r[0]]=r
        with clean.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['timestamp','lat','lon']);w.writerows((t.isoformat(),lat,lon) for t,lat,lon in sorted(merged.values()))
        train(clean,out,epochs)
    dump(Path(out)/'lineage.json',{'original_sha256':sha(original),'reviewed_sha256':sha(reviewed),'activation':'manual review required; not automatically deployed'})

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    for name in ['train','detect','retrain']:
        q=sub.add_parser(name);q.add_argument('--csv',required=True);q.add_argument('--out',required=True)
        if name=='detect':q.add_argument('--bundle',required=True)
        else:q.add_argument('--epochs',type=int,default=30)
        if name=='retrain':q.add_argument('--reviewed',required=True)
    a=p.parse_args()
    if a.cmd=='train':train(a.csv,a.out,a.epochs)
    elif a.cmd=='detect':detect(a.csv,a.bundle,a.out)
    else:retrain(a.csv,a.reviewed,a.out,a.epochs)
if __name__=='__main__':main()
