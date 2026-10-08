import os
import sqlite3
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from engine import fetch, simulate, features

st.set_page_config(page_title='Crypto AI Lab Mobile',page_icon='📈',layout='centered')
st.markdown('''<style>.block-container{padding-top:1.1rem;padding-left:1rem;padding-right:1rem;max-width:780px}div[data-testid="stMetric"]{background:#f3f6fa;padding:12px;border-radius:12px}@media(max-width:600px){h1{font-size:1.8rem!important}.stButton button{min-height:48px;width:100%}}</style>''',unsafe_allow_html=True)
st.title('📈 Crypto AI Lab')
st.caption('スマホ対応 v0.2 | 研究・仮想運用専用 | 実注文なし')
st.warning('これはAI予測ではなくルールベース戦略です。利益は保証されません。クラウド無料枠では保存データが消える場合があります。')

DB=os.getenv('CRYPTO_LAB_DB','paper.sqlite3')
def conn():
    c=sqlite3.connect(DB,timeout=15)
    c.execute('CREATE TABLE IF NOT EXISTS accounts (coin TEXT PRIMARY KEY, cash REAL NOT NULL, units REAL NOT NULL, last_date TEXT, last_price REAL, started TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, coin TEXT, date TEXT, side TEXT, price REAL, notional REAL, cash_after REAL, units_after REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS snapshots (coin TEXT, date TEXT, equity REAL, price REAL, PRIMARY KEY(coin,date))')
    return c

def initialize(coin):
    with conn() as c:
        c.execute('INSERT OR IGNORE INTO accounts VALUES (?,?,?,?,?,?)',(coin,1000.0,0.0,None,None,datetime.now(timezone.utc).isoformat()))

def step_paper(coin, data, fee, slip, allocation):
    if len(data)<35: raise ValueError('35日以上のデータが必要です。')
    # Paper mode: only uses last completed UTC day, not the partial current bar.
    today=pd.Timestamp.now(tz='UTC').floor('D')
    d=features(data[data.date<today].copy().reset_index(drop=True))
    if len(d)<35: raise ValueError('確定した日次データが不足しています。')
    last=d.iloc[-1]
    date=last.date.isoformat()
    price=float(last.price)
    # A signal derived from the preceding completed day is acted on at the latest daily observation.
    desired=int(d.iloc[-2].signal)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        cash,units,old_date,_,_=c.execute('SELECT cash,units,last_date,last_price,started FROM accounts WHERE coin=?',(coin,)).fetchone()
        if old_date is not None and date<=old_date:
            return '最新の確定日次価格はすでに反映済みです。'
        side=None; notional=0
        if desired and units<=1e-12:
            notional=cash*allocation
            if notional>0:
                units=notional/(price*(1+slip)*(1+fee));cash-=notional;side='BUY'
        elif not desired and units>1e-12:
            notional=units*price*(1-slip)*(1-fee)
            cash+=notional;units=0;side='SELL'
        if side:
            c.execute('INSERT INTO orders (coin,date,side,price,notional,cash_after,units_after) VALUES (?,?,?,?,?,?,?)',(coin,date,side,price,notional,cash,units))
        equity=cash+units*price
        c.execute('UPDATE accounts SET cash=?,units=?,last_date=?,last_price=? WHERE coin=?',(cash,units,date,price,coin))
        c.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)',(coin,date,equity,price))
    return f'{date[:10]} の確定価格を反映しました。売買：{side or "なし"}。'

coin=st.selectbox('銘柄', ['BTC','ETH','DOGE'])
with st.expander('データ・取引コスト設定',expanded=False):
    days=st.selectbox('取得日数',[90,180,365],index=0)
    api_key=st.text_input('CoinGecko Demo APIキー（必要な場合）',type='password',help='入力内容は保存しません。')
    fee_pct=st.number_input('片道手数料（%）',0.,5.,0.1,0.05)
    slip_pct=st.number_input('片道スリッページ（%）',0.,5.,0.1,0.05)
    alloc_pct=st.slider('最大投資比率（%）',10,100,60,5)
fee,slip,allocation=fee_pct/100,slip_pct/100,alloc_pct/100
@st.cache_data(ttl=900,show_spinner=False)
def prices(symbol,days,key): return fetch(symbol,days,key)

tab1,tab2=st.tabs(['📊 バックテスト','🧪 ペーパートレード'])
with tab1:
    if st.button('バックテストを実行',type='primary'):
        try:
            data=prices(coin,days,api_key)
            if len(data)<35: st.error('日次データが不足しています。90日以上で再試行してください。')
            else:
                curve,trades,_=simulate(data,1000,fee,slip,allocation)
                final=float(curve.equity.iloc[-1]); dd=float(curve.drawdown.min())
                c1,c2=st.columns(2)
                c1.metric('仮想資産',f'¥{final:,.1f}',f'{(final/1000-1)*100:+.2f}%')
                c2.metric('最大DD',f'{dd*100:.2f}%')
                st.metric('買い持ち騰落率（参考）',f'{(data.price.iloc[-1]/data.price.iloc[0]-1)*100:+.2f}%')
                st.line_chart(curve.set_index('date')['equity'])
                st.dataframe(trades,use_container_width=True,hide_index=True)
                st.download_button('売買履歴CSV',trades.to_csv(index=False).encode('utf-8-sig'),'backtest_trades.csv','text/csv')
                st.caption('前日シグナルを翌観測価格で執行する近似検証。板・税金・最小注文額は未考慮。')
        except Exception as e: st.error(f'取得・検証エラー：{e}')
with tab2:
    initialize(coin)
    st.info('「最新日次価格を反映」を押した時だけ更新します。24時間自動更新ではありません。初回は最新日のシグナルから開始します。')
    if st.button('最新日次価格を反映',type='primary'):
        try:
            data=prices(coin,days,api_key)
            st.success(step_paper(coin,data,fee,slip,allocation))
        except Exception as e: st.error(f'更新エラー：{e}')
    with conn() as c:
        cash,units,last_date,last_price,started=c.execute('SELECT cash,units,last_date,last_price,started FROM accounts WHERE coin=?',(coin,)).fetchone()
        trades=pd.read_sql_query('SELECT date,side,price,notional FROM orders WHERE coin=? ORDER BY id DESC',c,params=(coin,))
        history=pd.read_sql_query('SELECT date,equity FROM snapshots WHERE coin=? ORDER BY date',c,params=(coin,))
    equity=cash+units*(last_price or 0)
    c1,c2=st.columns(2)
    c1.metric('仮想評価額',f'¥{equity:,.1f}',f'{(equity/1000-1)*100:+.2f}%')
    c2.metric('現金残高',f'¥{cash:,.1f}')
    st.caption(f'保有数量：{units:.8f} {coin} / 最終反映：{last_date[:10] if last_date else "未反映"}')
    if len(history): st.line_chart(history.set_index('date')['equity'])
    st.dataframe(trades,use_container_width=True,hide_index=True)
    st.download_button('ペーパー取引履歴CSV',trades.to_csv(index=False).encode('utf-8-sig'),'paper_trades.csv','text/csv')
    with st.expander('仮想口座のリセット'):
        st.caption('この銘柄の仮想残高・履歴を削除します。取り消せません。')
        if st.button('この銘柄をリセット'):
            with conn() as c:
                c.execute('DELETE FROM orders WHERE coin=?',(coin,))
                c.execute('DELETE FROM snapshots WHERE coin=?',(coin,))
                c.execute('DELETE FROM accounts WHERE coin=?',(coin,))
            st.rerun()
st.caption('データ提供：CoinGecko。無料APIの制限により取得できない場合があります。公開アプリでは仮想口座は利用者間で共有される設計のため、個人利用に限定してください。')
