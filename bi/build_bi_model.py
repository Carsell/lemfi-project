#!/usr/bin/env python3
"""Rebuild the BI star schema and the reference dashboard layout from data/clean/."""
import pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BI = os.path.join(BASE, 'bi')

t = pd.read_csv(f'{BASE}/data/clean/transactions.csv', parse_dates=['occurred_at','occurred_on'])
u = pd.read_csv(f'{BASE}/data/clean/users.csv', parse_dates=['signup_date'])
raw = pd.read_csv(f'{BASE}/data/raw/transactions.csv')

fact = t[['transaction_id','user_id','occurred_on','send_country','receive_country',
          'send_currency','receive_currency','amount_gbp','transaction_type','device',
          'account_age_days','is_flagged','fx_reconciles']].copy()
fact['occurred_on'] = fact['occurred_on'].dt.date
fact.to_csv(f'{BI}/fact_transactions.csv', index=False)

dim_u = u.copy(); dim_u['signup_date'] = dim_u['signup_date'].dt.date
dim_u.to_csv(f'{BI}/dim_user.csv', index=False)

d = pd.date_range(t['occurred_on'].min(), t['occurred_on'].max(), freq='D')
pd.DataFrame({'date':d.date,'year':d.year,'month_no':d.month,'month_name':d.strftime('%b'),
    'year_month':d.strftime('%Y-%m'),'day_name':d.strftime('%a'),
    'week_start':(d-pd.to_timedelta(d.dayofweek,'D')).date,'is_weekend':d.dayofweek>=5}
    ).to_csv(f'{BI}/dim_date.csv', index=False)

n_raw, n_clean = len(raw), len(t)
n_quar = int((~t['fx_reconciles']).sum())
pd.DataFrame([
 ('Rows in source extract','',n_raw),
 ('Rows after cleaning','',n_clean),
 ('Rows removed by cleaning','',n_raw-n_clean),
 ('Transactions failing FX reconciliation','quarantined from value totals, still counted',n_quar),
 ('Transactions flagged as suspicious','',int(t['is_flagged'].sum())),
 ('Distinct users','',t['user_id'].nunique()),
], columns=['measure','note','value']).to_csv(f'{BI}/data_quality_log.csv', index=False)

# ---- reference layout
f = fact.copy(); f['occurred_on'] = pd.to_datetime(f['occurred_on'])
BG,INK,ACC,MUT,WARN = '#ffffff','#1a1a1a','#1f4e79','#9aa5b1','#b03a2e'
fig = plt.figure(figsize=(16,9), facecolor=BG)
fig.suptitle('Remittance Operations — Volume & Data Quality', fontsize=17, color=INK, x=0.05, ha='left', y=0.965, weight='bold')
fig.text(0.05,0.928,f'Jan–Jun 2025 · {n_clean:,} transactions · value figures exclude {n_quar} rows quarantined at FX reconciliation',
         fontsize=9.5, color=MUT, ha='left')
kpis=[('Transactions',f'{n_clean:,}'),('Value sent','£%.1fm'%(f[f.fx_reconciles].amount_gbp.sum()/1e6)),
      ('Active users',f'{f.user_id.nunique():,}'),('Flagged','%.1f%%'%(100*f.is_flagged.mean())),
      ('Rows rejected',f'{n_raw-n_clean:,}')]
for i,(k,v) in enumerate(kpis):
    x=0.05+i*0.185
    fig.text(x,0.848,v,fontsize=24,color=ACC,ha='left',weight='bold')
    fig.text(x,0.812,k.upper(),fontsize=8.5,color=MUT,ha='left')
gs=fig.add_gridspec(2,3,left=0.115,right=0.965,top=0.745,bottom=0.075,hspace=0.5,wspace=0.42)
def style(a,ti):
    a.set_title(ti,fontsize=11,color=INK,loc='left',pad=9,weight='bold'); a.set_facecolor(BG)
    for s in ('top','right'): a.spines[s].set_visible(False)
    for s in ('left','bottom'): a.spines[s].set_color(MUT)
    a.tick_params(colors=MUT,labelsize=8.5)
a=fig.add_subplot(gs[0,:2]); style(a,'Daily value sent (£000)')
s=f.groupby('occurred_on').amount_gbp.sum()/1000
a.plot(s.index,s.values,color=ACC,lw=1.4); a.fill_between(s.index,s.values,alpha=.12,color=ACC)
a=fig.add_subplot(gs[0,2]); style(a,'Top corridors by volume')
c=(f.send_country+' → '+f.receive_country).value_counts().head(6)[::-1]
a.barh(c.index,c.values/1000,color=ACC,height=.65); a.set_xlabel('000 transactions',fontsize=8,color=MUT)
a=fig.add_subplot(gs[1,0]); style(a,'Value by transaction type (£m)')
v=f.groupby('transaction_type').amount_gbp.sum().sort_values()
a.barh(v.index,v.values/1e6,color=ACC,height=.6)
a=fig.add_subplot(gs[1,1]); style(a,'Flag rate by corridor (%)')
g=(f.groupby(f.send_country+'→'+f.receive_country).is_flagged.mean()*100).sort_values().tail(6)
a.barh(g.index,g.values,color=[WARN if x>5 else ACC for x in g.values],height=.6)
a=fig.add_subplot(gs[1,2]); style(a,'Source extract → reported')
val=[n_raw,n_clean,n_clean-n_quar]
a.bar(['In source','Cleaned','Reported'],val,color=[MUT,ACC,ACC],width=.5)
a.set_ylim(min(val)-1200,max(val)+600)
for i,v_ in enumerate(val): a.text(i,v_+150,f'{v_:,}',ha='center',fontsize=8.5,color=INK)
fig.savefig(f'{BI}/dashboard_page1_operations.png',dpi=145,facecolor=BG)
print('BI model and reference layout rebuilt')
