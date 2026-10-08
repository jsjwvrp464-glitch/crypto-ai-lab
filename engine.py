#!/usr/bin/env python3
"""Free Kraken public OHLC monitor. No brokerage, credentials or real orders."""
import json, math, os, statistics, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).parent
STATE=ROOT/'data'/'monitor.json'
PAIRS={'BTC/USD':'XBTUSD','ETH/USD':'ETHUSD','DOGE/USD':'DOGEUSD'}
FEE=0.002; SLIP=0.001

def fetch(pair):
    url='https://api.kraken.com/0/public/OHLC?pair='+pair+'&interval=60'
    req=urllib.request.Request(url, headers={'User-Agent':'CryptoAILabPaper/0.3'})
    with urllib.request.urlopen(req,timeout=25) as resp: data=json.load(resp)
    if data.get('error'): raise RuntimeError(str(data['error']))
    key=next(k for k in data['result'] if k!='last')
    # last candle is still forming: do not trade on it
    return [{'time':int(x[0])*1000,'close':float(x[4])} for x in data['result'][key][:-1] if float(x[4])>0]

def ema(values,n):
    out=[]; e=values[0]; alpha=2/(n+1)
    for v in values: e=alpha*v+(1-alpha)*e;out.append(e)
    return out

def sigmoid(x): return 1/(1+math.exp(-max(-30,min(30,x))))

def features(values,i):
    # use only observations through candle i, no lookahead
    return [(values[i]/values[i-6]-1)*30,(values[i]/values[i-24]-1)*12,
            (values[i]/sum(values[i-12:i+1])*13-1)*25]

def ml_signal(values):
    # Offline logistic regression trained on first 70% of historical observations,
    # evaluated on later observations; target is NEXT candle direction.
    if len(values)<100:return None
    cut=int(len(values)*0.7); X=[];y=[]
    for i in range(24,cut-1):
        X.append([1]+features(values,i));y.append(int(values[i+1]>values[i]))
    weights=[0.]*4
    for _ in range(100):
        grad=[0.]*4
        for x,t in zip(X,y):
            error=sigmoid(sum(a*b for a,b in zip(x,weights)))-t
            for j in range(4):grad[j]+=error*x[j]
        weights=[w-0.09*(g/len(X)+(.001*w if j else 0)) for j,(w,g) in enumerate(zip(weights,grad))]
    prob=sigmoid(sum(a*b for a,b in zip([1]+features(values,len(values)-1),weights)))
    return round(prob,4)

def load():
    if STATE.exists():
        try:
            obj=json.loads(STATE.read_text())
            if obj.get('version')==3:return obj
        except (ValueError,OSError): pass
    return {'version':3,'updatedAt':None,'startingCash':1000,'cash':1000.,'positions':{},'lastProcessed':{},'prices':{},'signals':{},'trades':[],'equity':[],'errors':{}}

def run():
    state=load();now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    for label,symbol in PAIRS.items():
        try:
            candles=fetch(symbol)
            if len(candles)<120:raise ValueError('Not enough data')
            values=[r['close'] for r in candles]
            prob=ml_signal(values); e12=ema(values,12);e36=ema(values,36)
            # ML alone does not trigger order; require trend confirmation
            signal='BUY' if prob is not None and prob>=0.55 and e12[-1]>e36[-1] else ('SELL' if prob is not None and (prob<=0.45 or e12[-1]<e36[-1]) else 'HOLD')
            last=candles[-1]; state['prices'][label]={'price':last['close'],'time':last['time']}
            state['signals'][label]={'signal':signal,'upProbability':prob,'ema12':round(e12[-1],6),'ema36':round(e36[-1],6)}
            state['errors'].pop(label,None)
            # Only one decision per closed candle. A signal at close executed at close is
            # optimistic; model explicitly labels this proxy execution limitation.
            if state['lastProcessed'].get(label)==last['time']:continue
            state['lastProcessed'][label]=last['time']
            # One allocation maximum 20% of account; fee/slippage applied both sides.
            holdings=state['positions'].get(label,0.)
            if signal=='BUY' and holdings<=1e-12:
                spend=min(state['cash'],200.)
                if spend>=10:
                    units=spend*(1-FEE)/(last['close']*(1+SLIP))
                    state['cash']-=spend;state['positions'][label]=units
                    state['trades'].append({'time':last['time'],'pair':label,'side':'BUY','amount':round(spend,6),'price':last['close'],'units':units})
            elif signal=='SELL' and holdings>1e-12:
                proceeds=holdings*last['close']*(1-SLIP)*(1-FEE)
                state['cash']+=proceeds;state['positions'][label]=0.
                state['trades'].append({'time':last['time'],'pair':label,'side':'SELL','amount':round(proceeds,6),'price':last['close'],'units':holdings})
        except Exception as e:
            state['errors'][label]=str(e)[:200]
    # Valuation: previous known prices retained, no market-price guarantee
    equity=state['cash']+sum(q*state['prices'].get(pair,{}).get('price',0) for pair,q in state['positions'].items())
    state['equity'].append({'time':now,'value':round(equity,6)})
    state['equity']=state['equity'][-1000:];state['trades']=state['trades'][-1000:]
    state['updatedAt']=now
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print('monitor',now,'equity',round(equity,2),'errors',state['errors'])

if __name__=='__main__':run()
