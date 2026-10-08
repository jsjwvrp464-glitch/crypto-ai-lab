import numpy as np
import pandas as pd
import requests

SYMBOLS={'BTC':'bitcoin','ETH':'ethereum','DOGE':'dogecoin'}

def fetch(coin='BTC', days=90, api_key=''):
    headers={'accept':'application/json'}
    if api_key: headers['x-cg-demo-api-key']=api_key
    r=requests.get(f'https://api.coingecko.com/api/v3/coins/{SYMBOLS[coin]}/market_chart',params={'vs_currency':'jpy','days':days},headers=headers,timeout=20)
    r.raise_for_status()
    payload=r.json()
    if 'prices' not in payload: raise ValueError('価格データがありません。API制限を確認してください。')
    df=pd.DataFrame(payload['prices'],columns=['timestamp','price'])
    df['date']=pd.to_datetime(df.timestamp,unit='ms',utc=True).dt.floor('D')
    return df.groupby('date',as_index=False).last()[['date','price']].sort_values('date').reset_index(drop=True)

def features(df):
    d=df.copy()
    d['ret']=d.price.pct_change()
    d['ma_fast']=d.price.rolling(10).mean()
    d['ma_slow']=d.price.rolling(30).mean()
    d['momentum']=d.price.pct_change(7)
    d['volatility']=d.ret.rolling(14).std()
    d['signal']=((d.ma_fast>d.ma_slow)&(d.momentum>0)&(d.volatility<0.12)).astype(int)
    return d

def simulate(df, initial=1000., fee=0.001, slippage=0.001, max_allocation=.6):
    d=features(df)
    cash=float(initial); units=0.; trades=[]; equity=[]; last_signal=0
    for i,row in d.iterrows():
        price=float(row.price)
        # Prior completed bar signal is executed at next observation, avoiding same-bar lookahead.
        desired=int(d.iloc[i-1].signal) if i else 0
        if desired and not units and i>0:
            spend=cash*max_allocation
            units=spend/(price*(1+slippage)*(1+fee));cash-=spend
            trades.append({'date':row.date,'side':'BUY','price':price,'notional_jpy':spend})
        elif not desired and units:
            proceeds=units*price*(1-slippage)*(1-fee)
            cash+=proceeds;trades.append({'date':row.date,'side':'SELL','price':price,'notional_jpy':proceeds});units=0
        equity.append({'date':row.date,'equity':cash+units*price,'price':price})
    curve=pd.DataFrame(equity)
    curve['drawdown']=curve.equity/curve.equity.cummax()-1
    return curve,pd.DataFrame(trades),d
