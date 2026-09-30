"""Shared offline/replay preprocessing. No model score is fabricated here."""
import csv, math
from datetime import datetime
from pathlib import Path
FEATURES=['lat_smooth','lon_smooth','time_of_day','day_of_week','is_moving']
CONFIG={'schema':'causal-five-features-v1','sequence_length':10,'sample_seconds':60,
        'local_timezone':'Asia/Shanghai','max_speed_mps':8.0,'moving_speed_mps':1.0,
        'kalman_process_variance':1e-7,'kalman_observation_variance':1e-6}

def distance(a,b):
    p,q=map(math.radians,[a[0],b[0]])
    dp=q-p;dl=math.radians(b[1]-a[1])
    return 6371000*2*math.asin(min(1,math.sqrt(math.sin(dp/2)**2+math.cos(p)*math.cos(q)*math.sin(dl/2)**2)))

def read_csv(path):
    from zoneinfo import ZoneInfo
    tz=ZoneInfo(CONFIG['local_timezone']);rows=[]
    with open(path,encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'timestamp','lat','lon'} <= set(reader.fieldnames or []):
            raise ValueError('CSV requires timestamp,lat,lon')
        for line,r in enumerate(reader,2):
            t=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'))
            t=t.replace(tzinfo=tz) if t.tzinfo is None else t.astimezone(tz)
            lat,lon=float(r['lat']),float(r['lon'])
            if not (-90<=lat<=90 and -180<=lon<=180): raise ValueError(f'invalid coordinates at row {line}')
            if rows and t<=rows[-1][0]:raise ValueError(f'duplicate or unordered timestamp at row {line}')
            rows.append((t,lat,lon))
    return rows

def features(rows):
    """Reject unsupported cadence / speed; reset filter across quality breaks."""
    result=[];previous=None;mean=None;variance=None;rejected=0
    for t,lat,lon in rows:
        raw=(lat,lon);dt=(t-previous[0]).total_seconds() if previous else None
        invalid=previous and (dt!=CONFIG['sample_seconds'] or distance(previous[1:],raw)/dt>CONFIG['max_speed_mps'])
        if invalid:
            result.append(None);previous=(t,lat,lon);mean=variance=None;rejected+=1;continue
        if mean is None:
            mean=[lat,lon];variance=[CONFIG['kalman_observation_variance']]*2;speed=0
        else:
            old=mean[:]
            for j,z in enumerate(raw):
                pred=variance[j]+CONFIG['kalman_process_variance']
                gain=pred/(pred+CONFIG['kalman_observation_variance'])
                mean[j]+=gain*(z-mean[j]);variance[j]=(1-gain)*pred
            speed=distance(old,mean)/dt
        time=t.hour+t.minute/60+t.second/3600
        result.append([*mean,time,t.weekday(),int(speed>CONFIG['moving_speed_mps'])])
        previous=(t,lat,lon)
    return result,rejected

def windows(features_array,scaler):
    import numpy as np
    n=CONFIG['sequence_length'];out=[];endpoints=[]
    low=np.asarray(scaler['min']);span=np.asarray(scaler['span'])
    for i in range(n-1,len(features_array)):
        seq=features_array[i-n+1:i+1]
        if any(x is None for x in seq):continue
        out.append((np.asarray(seq)-low)/span);endpoints.append(i)
    return np.asarray(out,dtype='float32').reshape(-1,n,len(FEATURES)),endpoints

def fit_scaler(values):
    import numpy as np
    good=np.asarray([x for x in values if x is not None],dtype=float)
    if len(good)<CONFIG['sequence_length']:raise ValueError('insufficient clean data')
    low=good.min(axis=0);span=good.max(axis=0)-low;span[span==0]=1
    return {'features':FEATURES,'min':low.tolist(),'span':span.tolist()}
