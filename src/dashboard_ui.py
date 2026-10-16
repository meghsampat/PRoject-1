"""Video-inspired local dashboard presentation."""
import html
import streamlit as st
import plotly.graph_objects as go

def shell():
    st.markdown("""<style>
.stApp{background:#f5f6fa;color:#182236}
.block-container{padding-top:1.5rem;max-width:1480px;padding-bottom:5rem}
[data-testid="stSidebar"]{background:#eef1f7}
[data-testid="stHeader"]{background:transparent}
.brand{background:#0e192c;color:white;padding:22px 28px;border-radius:16px 16px 0 0;display:flex;align-items:center;gap:14px}
.brand strong{font-size:25px}.brand span{font-size:14px;color:#c6cddd}
.brand small{margin-left:auto;color:#72d6bb}
[data-baseweb="tab-list"]{background:#0e192c;gap:24px;padding:0 26px;border-radius:0 0 16px 16px;margin-bottom:22px}
[data-baseweb="tab"]{color:#c6cddd;padding:18px 8px}
[data-baseweb="tab"][aria-selected="true"]{color:white}
[data-baseweb="tab-highlight"]{background:#585cff}
[data-testid="stMetric"]{background:white;border:1px solid #e8eaf0;border-radius:14px;padding:20px}
[data-testid="stMetricLabel"]{color:#737c8d}
[data-testid="stMetricValue"]{font-size:1.8rem}
.stButton>button,.stFormSubmitButton>button{border-radius:9px}
[data-testid="stChatMessage"]{background:white;border:1px solid #e8eaf0;border-radius:14px}
.insight{background:#f0efff;border-radius:12px;padding:18px;line-height:1.7;margin-bottom:18px}
.trace{border-bottom:1px solid #edf0f5;padding:13px 0;font-size:13px}
.trace span{display:block;color:#7d8594;font-size:11px;margin-bottom:5px}
@media(max-width:700px){.brand{padding:18px}.brand small{display:none}.block-container{padding-left:1rem;padding-right:1rem}[data-baseweb="tab-list"]{gap:10px;padding:0 10px}}
</style>""",unsafe_allow_html=True)
    st.markdown('<div class="brand"><strong>FMCG</strong><span>Product Intelligence</span><small>&#9679; Local data workspace</small></div>',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def weekly_revenue(signature,start,end,_data):
    return _data.loc[_data.WEEK_NO.between(start,end)].groupby("WEEK_NO").SALES_VALUE.sum()

def overview(weekly):
    chart,insight=st.columns([2.2,1])
    with chart,st.container(border=True):
        st.subheader("Weekly Revenue Trend")
        st.caption("Observed dataset weeks")
        fig=go.Figure(go.Scatter(x=weekly.index,y=weekly.values,mode="lines+markers",
            line=dict(color="#585cff",width=3),marker=dict(size=5),
            fill="tozeroy",fillcolor="rgba(88,92,255,0.06)",
            hovertemplate="Week %{x}<br>Revenue $%{y:,.2f}<extra></extra>"))
        fig.update_layout(height=310,margin=dict(l=10,r=10,t=15,b=15),
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Dataset week",yaxis_title="Revenue (USD)")
        fig.update_yaxes(gridcolor="#edf0f5")
        st.plotly_chart(fig,width="stretch",key="overview_revenue")
    with insight,st.container(border=True):
        st.subheader("Business Snapshot")
        peak=int(weekly.idxmax())
        st.markdown(f'<div class="insight">Highest observed revenue in this selection:<br><strong>Week {peak} &middot; ${weekly.loc[peak]:,.2f}</strong></div>',unsafe_allow_html=True)
        st.write("Explore product opportunities, customer groups and revenue forecasts in the workspace tabs.")
        st.caption("Edge weeks may be partial. Unusual records are retained.")
        st.markdown("**Try asking the assistant**")
        st.write("Which products should we promote next month?")

def transparency(turn):
    st.subheader("Transparency")
    rows=[("Supervisor","Waiting for your question"),("Specialist","Selected for each analysis"),("Tool","Validated local Python tools"),("Judge","Evidence checked before display")]
    if turn:
        rows=[("Supervisor",turn["decision"]["reason"]),("Specialist",turn["response"]["specialist"]),("Tool",turn["response"]["tool"]),("Judge",turn["judge"]["status"]),("Source",turn["response"]["evidence"]["source_table"])]
    for label,value in rows:
        st.markdown(f'<div class="trace"><span>{html.escape(label)}</span>{html.escape(str(value))}</div>',unsafe_allow_html=True)
    st.caption("Suggestions require review. Answers use your selected data scope.")
