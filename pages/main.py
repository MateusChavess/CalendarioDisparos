# =================== Calendários: Gastos (topo) + Disparos (abaixo) ===================

import os
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
import altair as alt

# ---------- GUARD ----------
if not st.session_state.get("logged_in", False) or st.session_state.get("auth_token") != "ok":
    try:
        st.switch_page("app.py")
    except Exception:
        st.markdown("<meta http-equiv='refresh' content='0; url=/' />", unsafe_allow_html=True)
    st.stop()

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
st.set_page_config(page_title="Calendários – Gastos & Disparos", layout="wide")
st.markdown("<h1 style='margin:0'>📅 Calendários – Gastos & Disparos</h1>", unsafe_allow_html=True)

PROJECT_ID = "leads-ts"
DATASET    = "Unnichat"

# 👉 Ajuste aqui se suas tabelas tiverem sufixos diferentes (_s, etc.)
TABLE_GASTOS    = f"{PROJECT_ID}.{DATASET}.gasto_por_dia"
TABLE_DISPAROS  = f"{PROJECT_ID}.{DATASET}.disparos_unnichat"

# ---------- AUTH BIGQUERY ----------
try:
    if "gcp_service_account" in st.secrets:
        PROJECT_ID = st.secrets.get("gcp_project_id", PROJECT_ID)
        creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        bq = bigquery.Client(project=PROJECT_ID, credentials=creds)
        auth_mode = "secrets"
    else:
        SA_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", r"C:\path\to\service_account.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_PATH
        bq = bigquery.Client(project=PROJECT_ID)
        auth_mode = "arquivo local"
except Exception as e:
    st.error("Falha ao autenticar no BigQuery.")
    st.exception(e)
    st.stop()

# ---------- HELPERS ----------
MESES_PT = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
DOW_MAP = {0:"Domingo",1:"Segunda",2:"Terça",3:"Quarta",4:"Quinta",5:"Sexta",6:"Sábado"}
ORDER_DOW = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"]

def metric_usd(v: float) -> str:
    return f"$ {float(v):,.2f}"

def render_calendar(df_in: pd.DataFrame, date_col: str, value_col: str, titulo: str):
    st.subheader(titulo)

    ts = df_in[date_col].dropna()
    hoje = pd.Timestamp.today()

    c1, c2 = st.columns(2)
    anos = sorted(ts.dt.year.unique().tolist()) or [hoje.year]
    ano_idx = (anos.index(hoje.year) if hoje.year in anos else len(anos)-1)
    mes_idx = hoje.month - 1 if (ano_idx == len(anos)-1) else 0

    mes_nome = c1.selectbox("Mês", MESES_PT, index=mes_idx, key=f"mes_{titulo}")
    mes = MESES_PT.index(mes_nome) + 1
    ano = c2.selectbox("Ano", anos, index=ano_idx, key=f"ano_{titulo}")

    start = pd.Timestamp(year=ano, month=mes, day=1)
    end   = start + pd.offsets.MonthEnd(1)

    sel = df_in[(df_in[date_col].dt.year == ano) & (df_in[date_col].dt.month == mes)].copy()
    sel["date"] = sel[date_col].dt.normalize()
    agg = (
        sel.groupby("date", as_index=False)[value_col]
           .sum()
           .rename(columns={value_col: "valor"})
    )

    cal = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    cal = cal.merge(agg, on="date", how="left").fillna({"valor": 0})

    cal["dia"] = cal["date"].dt.day
    sunday_offset = (start.weekday() + 1) % 7
    week0 = start - pd.Timedelta(days=sunday_offset)
    cal["week"] = ((cal["date"] - week0).dt.days // 7) + 1
    cal["dow"]  = (cal["date"].dt.weekday + 1) % 7
    cal["dow_label"] = cal["dow"].map(DOW_MAP)

    n_weeks = int(cal["week"].max()) if not cal.empty else 5
    CELL_H  = 82 if n_weeks == 5 else 74
    CHART_H = CELL_H * n_weeks

    max_v = float(cal["valor"].max()); max_v = max(1.0, max_v)
    DARK_TEALS = ["#0B1227", "#0C2F2B", "#0E4B44", "#106F65", "#0B5F57"]

    # labels centralizados (moeda se for float)
    if cal["valor"].dtype.kind in ("i", "u"):
        cal["center_label"] = cal["valor"].map(lambda v: f"{int(v):,}".replace(",", "."))
        fmt_tooltip = ",d"
        legend_title = "Total"
    else:
        cal["center_label"] = cal["valor"].map(lambda v: f"$ {float(v):,.2f}")
        fmt_tooltip = ",.2f"
        legend_title = "Valor ($)"

    base = alt.Chart(cal).properties(width="container", height=int(CHART_H))

    heat = base.mark_rect(stroke="#2F3B55", strokeWidth=1, cornerRadius=10).encode(
        x=alt.X("dow_label:N", sort=ORDER_DOW, axis=alt.Axis(title=None, labelAngle=0, labelPadding=6, ticks=False)),
        y=alt.Y("week:O", axis=alt.Axis(title=None, ticks=False)),
        color=alt.Color("valor:Q",
                        legend=alt.Legend(title=legend_title, labelColor="#E5E7EB", titleColor="#E5E7EB"),
                        scale=alt.Scale(domain=[0, max_v], range=DARK_TEALS)),
        tooltip=[alt.Tooltip("date:T", title="Dia"), alt.Tooltip("valor:Q", title=legend_title, format=fmt_tooltip)]
    )

    text_val = base.mark_text(baseline="middle", fontSize=14, fontWeight=700, color="#E5E7EB").encode(
        x=alt.X("dow_label:N", sort=ORDER_DOW),
        y=alt.Y("week:O"),
        text=alt.Text("center_label:N")
    )

    day_corner = base.mark_text(align="right", baseline="top", dx=-8, dy=6, fontSize=12, fontWeight=800, color="#FFFFFF").encode(
        x=alt.X("dow_label:N", sort=ORDER_DOW, bandPosition=1),
        y=alt.Y("week:O", bandPosition=0),
        text=alt.Text("dia:Q")
    )

    st.altair_chart(heat + text_val + day_corner, use_container_width=True)
    st.divider()

def render_month_bar(df_in: pd.DataFrame, date_col: str, value_col: str, titulo: str, is_money: bool):
    st.subheader(titulo)
    dfm = df_in.copy()
    dfm["ym"] = dfm[date_col].dt.to_period("M")
    bar_data = dfm.groupby("ym", as_index=False)[value_col].sum().sort_values("ym")
    bar_data["mes_label"] = bar_data["ym"].apply(lambda p: pd.Period(p, freq="M").strftime("%b/%Y").capitalize())
    if is_money:
        bar_data["label"] = bar_data[value_col].map(lambda v: f"$ {float(v):,.2f}")
        tooltip_fmt = ",.2f"
    else:
        bar_data["label"] = bar_data[value_col].map(lambda v: f"{int(v):,}".replace(",", "."))
        tooltip_fmt = ",d"

    bar = alt.Chart(bar_data).mark_bar(size=26, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        x=alt.X("mes_label:N", sort=list(bar_data["mes_label"]), axis=alt.Axis(title=None, labelAngle=0, labelPadding=8)),
        y=alt.Y(f"{value_col}:Q", axis=alt.Axis(title=None)),
        tooltip=[alt.Tooltip("mes_label:N", title="Mês"),
                 alt.Tooltip(f"{value_col}:Q", title="Total", format=tooltip_fmt)],
        color=alt.value("#0B5F57")
    ).properties(width="container", height=340)

    labels = alt.Chart(bar_data).mark_text(align="center", baseline="bottom", dy=-4, color="#E5E7EB", fontWeight=700).encode(
        x=alt.X("mes_label:N", sort=list(bar_data["mes_label"])),
        y=alt.Y(f"{value_col}:Q"),
        text="label:N"
    )

    st.altair_chart(bar + labels, use_container_width=True)
    st.divider()

# ---------- QUERIES (cache) ----------
@st.cache_data(show_spinner=False)
def load_gastos():
    sql = f"""
    SELECT
      DATE(data) AS dt,
      CAST(valor_gasto_dia AS NUMERIC) AS custo
    FROM `{TABLE_GASTOS}`
    WHERE data IS NOT NULL
    """
    return bq.query(sql).result().to_dataframe(create_bqstorage_client=False)

@st.cache_data(show_spinner=False)
def load_disparos():
    sql = f"""
    SELECT
      DATE(data_do_disparo)                          AS dt,
      CAST(lider            AS STRING)              AS lider,
      CAST(acao             AS STRING)              AS acao,
      CAST(demanda          AS STRING)              AS demanda,
      CAST(modelo_template  AS STRING)              AS modelo_template,
      CAST(quantidade_disparada AS INT64)           AS qtd
    FROM `{TABLE_DISPAROS}`
    WHERE data_do_disparo IS NOT NULL
    """
    return bq.query(sql).result().to_dataframe(create_bqstorage_client=False)

# ===== Botão de atualização =====
c1, c2 = st.columns([1,1])
with c2:
    if st.button("🔄 Atualizar dados", use_container_width=True):
        load_gastos.clear(); load_disparos.clear(); st.rerun()

# ===================== BLOCO 1 – GASTOS (TOPO) =====================
with st.spinner("🔍 Carregando Gastos…"):
    df_gastos = load_gastos()

if df_gastos.empty:
    st.warning("Nenhum dado encontrado na tabela de gastos.")
    st.stop()

df_gastos["dt"] = pd.to_datetime(df_gastos["dt"], errors="coerce")
df_gastos["custo"] = pd.to_numeric(df_gastos["custo"], errors="coerce").fillna(0.0)

# Métricas Gastos
total_gasto = float(df_gastos["custo"].sum())
dfw = df_gastos.copy(); dfw["semana"] = dfw["dt"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date())
media_semanal = float(dfw.groupby("semana", as_index=False)["custo"].sum()["custo"].mean() or 0.0)
dfm = df_gastos.copy(); dfm["ym"] = dfm["dt"].dt.to_period("M")
top_row = dfm.groupby("ym", as_index=False)["custo"].sum().sort_values("custo", ascending=False).head(1)
if not top_row.empty:
    mes_top = pd.Period(top_row.iloc[0]["ym"], freq="M").strftime("%B/%Y").capitalize()
    valor_top = float(top_row.iloc[0]["custo"])
else:
    mes_top, valor_top = "—", 0.0

m1, m2, m3 = st.columns(3)
m1.metric("💵 Total gasto", metric_usd(total_gasto))
m2.metric("📆 Média semanal", metric_usd(media_semanal))
m3.metric("🏆 Mês com maior gasto", f"{mes_top} — {metric_usd(valor_top)}")

render_calendar(df_gastos, "dt", "custo", "📅 Calendário de Gastos")
render_month_bar(df_gastos, "dt", "custo", "📊 Total gasto por mês", is_money=True)

# ===================== BLOCO 2 – DISPAROS (ABAIXO) =====================
st.markdown("<h2 style='margin-top:8px'>📨 Disparos</h2>", unsafe_allow_html=True)

with st.spinner("🔍 Carregando Disparos…"):
    df_d = load_disparos()

if df_d.empty:
    st.warning("Nenhum dado encontrado na tabela de disparos.")
    st.stop()

df_d["dt"] = pd.to_datetime(df_d["dt"], errors="coerce")
for c in ["lider","acao","demanda","modelo_template"]:
    df_d[c] = df_d[c].fillna("—")

# Filtros Disparos
fc1, fc2, fc3, fc4 = st.columns(4)
opts_lider  = sorted([x for x in df_d["lider"].dropna().unique().tolist() if x != ""])
opts_modelo = sorted([x for x in df_d["modelo_template"].dropna().unique().tolist() if x != ""])
opts_acao   = sorted([x for x in df_d["acao"].dropna().unique().tolist() if x != ""])
opts_dem    = sorted([x for x in df_d["demanda"].dropna().unique().tolist() if x != ""])

sel_lider   = fc1.multiselect("Líder",           options=opts_lider,  default=[], placeholder="Escolha o Líder")
sel_modelo  = fc2.multiselect("Modelo Template", options=opts_modelo, default=[], placeholder="Escolha o Modelo")
sel_acao    = fc3.multiselect("Ação",            options=opts_acao,   default=[], placeholder="Escolha a Ação")
sel_dem     = fc4.multiselect("Demanda",         options=opts_dem,    default=[], placeholder="Escolha a Demanda")

mask = pd.Series(True, index=df_d.index)
if sel_lider:  mask &= df_d["lider"].isin(sel_lider)
if sel_modelo: mask &= df_d["modelo_template"].isin(sel_modelo)
if sel_acao:   mask &= df_d["acao"].isin(sel_acao)
if sel_dem:    mask &= df_d["demanda"].isin(sel_dem)

df_d_f = df_d[mask].copy()
if df_d_f.empty:
    st.info("Nenhum disparo após aplicar os filtros.")
    st.stop()

# Métricas Disparos (quantidade)
total_qtd = int(df_d_f["qtd"].sum())
dfdw = df_d_f.copy(); dfdw["semana"] = dfdw["dt"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date())
media_sem_qtd = float(dfdw.groupby("semana", as_index=False)["qtd"].sum()["qtd"].mean() or 0.0)
dfdm = df_d_f.copy(); dfdm["ym"] = dfdm["dt"].dt.to_period("M")
top_d = dfdm.groupby("ym", as_index=False)["qtd"].sum().sort_values("qtd", ascending=False).head(1)
if not top_d.empty:
    mes_top_d = pd.Period(top_d.iloc[0]["ym"], freq="M").strftime("%B/%Y").capitalize()
    valor_top_d = int(top_d.iloc[0]["qtd"])
else:
    mes_top_d, valor_top_d = "—", 0

dm1, dm2, dm3 = st.columns(3)
dm1.metric("✉️ Disparos (total)", f"{total_qtd:,}".replace(",", "."))
dm2.metric("📆 Média semanal (qtd.)", f"{int(round(media_sem_qtd)):,}".replace(",", "."))
dm3.metric("🏆 Mês com mais disparos", f"{mes_top_d} — {valor_top_d:,}".replace(",", "."))

render_calendar(df_d_f, "dt", "qtd", "📅 Calendário de Disparos")
render_month_bar(df_d_f, "dt", "qtd", "📊 Disparos por mês", is_money=False)

st.markdown(
    f"<div style='margin-top:10px;color:#9CA3AF'>🔐 Modo de autenticação: <b>{auth_mode}</b></div>",
    unsafe_allow_html=True
)
