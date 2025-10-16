# =================== Calendário de Gastos (Altair – com filtros vazios + métricas + barras mensais) ===================

import os
import pandas as pd
import numpy as np
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
import altair as alt

# ---------- GUARD: exige login SEMPRE ----------
if not st.session_state.get("logged_in", False) or st.session_state.get("auth_token") != "ok":
    # tenta mandar pra tela de login
    try:
        st.switch_page("app.py")
    except Exception:
        # fallback (ex.: se mudar o nome do link manually, etc.)
        st.markdown("<meta http-equiv='refresh' content='0; url=/' />", unsafe_allow_html=True)
    st.stop()

# (Opcional) botão de logout no canto direito do header
logout_col = st.columns([1,1,1,1,1,1,1,1,1,1])[9]
with logout_col:
    if st.button("Sair", use_container_width=True):
        for k in ["logged_in", "user_name", "auth_token"]:
            st.session_state.pop(k, None)
        try:
            st.switch_page("app.py")
        except Exception:
            st.markdown("<meta http-equiv='refresh' content='0; url=/' />", unsafe_allow_html=True)
        st.stop()

# ---------- CONFIG ----------
st.set_page_config(page_title="Calendário de Gastos", layout="wide")
st.markdown("<h1 style='margin:0'>📅 Calendário de Gastos</h1>", unsafe_allow_html=True)

PROJECT_ID = "leads-ts"
DATASET = "Unnichat"
TABLE = f"{PROJECT_ID}.{DATASET}.disparos_s"

# ---------- AUTH BIGQUERY ----------
try:
    if "gcp_service_account" in st.secrets:
        PROJECT_ID = st.secrets.get("gcp_project_id", PROJECT_ID)
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        bq = bigquery.Client(project=PROJECT_ID, credentials=creds)
        auth_mode = "secrets"
    else:
        SA_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", r"C:\\path\\to\\service_account.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_PATH
        bq = bigquery.Client(project=PROJECT_ID)
        auth_mode = "arquivo local"
except Exception as e:
    st.error("Falha ao autenticar no BigQuery.")
    st.exception(e)
    st.stop()

# ---------- QUERY (cache) ----------
@st.cache_data(show_spinner=False)
def load_rows():
    sql = f"""
    SELECT
      DATE(data) AS dt,
      CAST(custo_estimado AS NUMERIC) AS custo,
      CAST(lider AS STRING) AS lider,
      CAST(acao  AS STRING) AS acao
    FROM {TABLE}
    WHERE data IS NOT NULL
    """
    return bq.query(sql).result().to_dataframe(create_bqstorage_client=False)

# ===== Botão de atualização =====
# Limpa o cache da função 'load_rows' e recarrega a app para buscar dados atuais do BigQuery
ctrl1, ctrl2 = st.columns([1,1])
with ctrl2:
    if st.button("🔄 Atualizar dados", use_container_width=True, help="Recarrega dados mais recentes do BigQuery"):
        load_rows.clear()    # limpa o cache desta função
        st.rerun()           # reroda a app (vai consultar novamente)

with st.spinner("🔍 Consultando BigQuery…"):
    df_raw = load_rows()

if df_raw.empty:
    st.warning("Nenhum dado encontrado na tabela.")
    st.stop()

# ---------- PREP ----------
df_raw["dt"] = pd.to_datetime(df_raw["dt"], errors="coerce")
df_raw["custo"] = pd.to_numeric(df_raw["custo"], errors="coerce").fillna(0.0)
df_raw["lider"] = df_raw["lider"].fillna("—")
df_raw["acao"]  = df_raw["acao"].fillna("—")

def fmt_usd(v: float) -> str:
    return f"$ {float(v):,.2f}"

# ---------- FILTROS (vazios = mostram tudo) ----------
st.subheader("🔎 Filtros")
f1, f2 = st.columns(2)

leaders = sorted([x for x in df_raw["lider"].dropna().unique().tolist() if x != ""])
actions = sorted([x for x in df_raw["acao"].dropna().unique().tolist() if x != ""])

sel_leaders = f1.multiselect("Líder", options=leaders, default=[], placeholder="(Escolha o Líder)")
sel_actions = f2.multiselect("Ação",  options=actions, default=[],  placeholder="(Escolha a Ação)")

mask = pd.Series(True, index=df_raw.index)
if len(sel_leaders) > 0:
    mask &= df_raw["lider"].isin(sel_leaders)
if len(sel_actions) > 0:
    mask &= df_raw["acao"].isin(sel_actions)

df_filt = df_raw[mask].copy()

if df_filt.empty:
    st.info("Nenhum dado após aplicar os filtros.")
    st.stop()

# ---------- MÉTRICAS ----------
total_gasto = float(df_filt["custo"].sum())

df_week = df_filt.copy()
df_week["semana"] = df_week["dt"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date())
media_semanal = float(df_week.groupby("semana", as_index=False)["custo"].sum()["custo"].mean() or 0.0)

df_month = df_filt.copy()
df_month["ym"] = df_month["dt"].dt.to_period("M")
top_row = (
    df_month.groupby("ym", as_index=False)["custo"].sum()
            .sort_values("custo", ascending=False)
            .head(1)
)
if not top_row.empty:
    ym = top_row.iloc[0]["ym"]
    mes_top = pd.Period(ym, freq="M").strftime("%B/%Y").capitalize()
    valor_top = float(top_row.iloc[0]["custo"])
else:
    mes_top, valor_top = "—", 0.0

m1, m2, m3 = st.columns(3)
m1.metric("💵 Total gasto", fmt_usd(total_gasto))
m2.metric("📆 Média semanal",        fmt_usd(media_semanal))
m3.metric("🏆 Mês com maior gasto",  f"{mes_top} — {fmt_usd(valor_top)}")

st.divider()

# ====== CALENDÁRIO (Altair) ======
st.subheader("📅 Entradas por dia (Gastos)")

ts = df_filt["dt"].dropna()
hoje = pd.Timestamp.today()

c1, c2 = st.columns(2)
MESES_PT = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

anos_disp = sorted(ts.dt.year.unique().tolist()) or [hoje.year]
ano_default_idx = (anos_disp.index(hoje.year) if hoje.year in anos_disp else len(anos_disp)-1)
mes_default_idx = hoje.month - 1 if (ano_default_idx == len(anos_disp)-1) else 0

mes_nome = c1.selectbox("Mês", MESES_PT, index=mes_default_idx, key="cal_mes")
mes = MESES_PT.index(mes_nome) + 1
ano = c2.selectbox("Ano", anos_disp, index=ano_default_idx, key="cal_ano")

start = pd.Timestamp(year=ano, month=mes, day=1)
end   = start + pd.offsets.MonthEnd(1)

sel = df_filt[(df_filt["dt"].dt.year == ano) & (df_filt["dt"].dt.month == mes)].copy()
sel["date"] = sel["dt"].dt.normalize()
agg = (
    sel.groupby("date", as_index=False)["custo"]
       .sum()
       .rename(columns={"custo": "valor"})
)

cal = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
cal = cal.merge(agg, on="date", how="left").fillna({"valor": 0.0})

cal["dia"] = cal["date"].dt.day
sunday_offset = (start.weekday() + 1) % 7
week0 = start - pd.Timedelta(days=sunday_offset)
cal["week"] = ((cal["date"] - week0).dt.days // 7) + 1
cal["dow"]  = (cal["date"].dt.weekday + 1) % 7

DOW_MAP = {0:"Domingo",1:"Segunda",2:"Terça",3:"Quarta",4:"Quinta",5:"Sexta",6:"Sábado"}
order_cols = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"]
cal["dow_label"] = cal["dow"].map(DOW_MAP)

n_weeks = int(cal["week"].max()) if not cal.empty else 5
CELL_H  = 82 if n_weeks == 5 else 74
CHART_H = CELL_H * n_weeks

max_v = float(cal["valor"].max()); max_v = max(1.0, max_v)
DARK_TEALS = ["#0B1227", "#0C2F2B", "#0E4B44", "#106F65", "#0B5F57"]

cal["usd_center"] = cal["valor"].map(lambda v: f"$ {v:,.2f}")

base = alt.Chart(cal).properties(width="container", height=int(CHART_H))

heat = base.mark_rect(
    stroke="#2F3B55", strokeWidth=1, cornerRadius=10
).encode(
    x=alt.X("dow_label:N", sort=order_cols,
            axis=alt.Axis(title=None, labelAngle=0, labelPadding=6, ticks=False)),
    y=alt.Y("week:O", axis=alt.Axis(title=None, ticks=False)),
    color=alt.Color(
        "valor:Q",
        legend=alt.Legend(title="Gasto ($)", labelColor="#E5E7EB", titleColor="#E5E7EB"),
        scale=alt.Scale(domain=[0, max_v], range=DARK_TEALS),
    ),
    tooltip=[
        alt.Tooltip("date:T",  title="Dia"),
        alt.Tooltip("valor:Q", title="Gasto ($)", format=",.2f")
    ]
)

text_val = base.mark_text(
    baseline="middle", fontSize=14, fontWeight=700, color="#E5E7EB"
).encode(
    x=alt.X("dow_label:N", sort=order_cols),
    y=alt.Y("week:O"),
    text=alt.Text("usd_center:N")
)

day_corner = base.mark_text(
    align="right", baseline="top", dx=-8, dy=6, fontSize=12, fontWeight=800, color="#FFFFFF"
).encode(
    x=alt.X("dow_label:N", sort=order_cols, bandPosition=1),
    y=alt.Y("week:O", bandPosition=0),
    text=alt.Text("dia:Q")
)

st.altair_chart(heat + text_val + day_corner, use_container_width=True)

st.divider()

# ---------- BARRAS MENSAIS ----------
st.subheader("📊 Total gasto por mês")

df_month_all = df_filt.copy()
df_month_all["ym"] = df_month_all["dt"].dt.to_period("M")
bar_data = (
    df_month_all.groupby("ym", as_index=False)["custo"].sum()
                .sort_values("ym")
)
bar_data["mes_label"] = bar_data["ym"].apply(lambda p: pd.Period(p, freq="M").strftime("%b/%Y").capitalize())
bar_data["usd_label"] = bar_data["custo"].map(lambda v: f"$ {v:,.2f}")

bar = alt.Chart(bar_data).mark_bar(size=26, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
    x=alt.X("mes_label:N", sort=list(bar_data["mes_label"]),
            axis=alt.Axis(title=None, labelAngle=0, labelPadding=8)),
    y=alt.Y("custo:Q", axis=alt.Axis(title=None)),
    tooltip=[alt.Tooltip("mes_label:N", title="Mês"), alt.Tooltip("custo:Q", title="Total ($)", format=",.2f")],
    color=alt.value("#0B5F57")
).properties(width="container", height=340)

labels = alt.Chart(bar_data).mark_text(
    align="center", baseline="bottom", dy=-4, color="#E5E7EB", fontWeight=700
).encode(
    x=alt.X("mes_label:N", sort=list(bar_data["mes_label"])),
    y=alt.Y("custo:Q"),
    text="usd_label:N"
)

st.altair_chart(bar + labels, use_container_width=True)

st.markdown(
    f"<div style='margin-top:10px;color:#9CA3AF'>🔐 Modo de autenticação: <b>{auth_mode}</b></div>",
    unsafe_allow_html=True
)
