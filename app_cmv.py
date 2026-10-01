import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="CMV | Única", page_icon="📊", layout="wide")

FATOR_CMV = 0.8426
MESES = {1:'Janeiro',2:'Fevereiro',3:'Março',4:'Abril',5:'Maio',6:'Junho',7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'}

st.markdown("""
<style>
.stApp {background: linear-gradient(180deg,#f7f9fc 0%,#eef3f8 100%);}
.block-container {max-width: 1250px; padding-top: 2rem; padding-bottom: 3rem;}
.hero {background:linear-gradient(135deg,#111827,#25364f); color:white; padding:28px 32px; border-radius:22px; margin-bottom:22px; box-shadow:0 14px 36px rgba(15,23,42,.12)}
.hero h1 {margin:0;font-size:2rem}.hero p{margin:8px 0 0;color:#dbe4ef}
.card {background:white;border:1px solid #e5eaf0;border-radius:18px;padding:20px;box-shadow:0 7px 22px rgba(15,23,42,.05)}
.label {font-size:.76rem;text-transform:uppercase;letter-spacing:.08em;color:#64748b;font-weight:700}
.value {font-size:1.65rem;font-weight:800;color:#0f172a;margin-top:5px}
.ok {padding:10px 14px;border-radius:12px;background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0;margin:7px 0}
.small {color:#64748b;font-size:.88rem}
div[data-testid="stFileUploader"] {background:white;border:1px dashed #cbd5e1;padding:12px;border-radius:16px}
textarea {font-family:ui-monospace,SFMono-Regular,Menlo,monospace!important}
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>CMV • Única Atacadista</h1><p>Consolidação automática das bases de vendas e transferências, com apuração mensal do CMV.</p></div>""", unsafe_allow_html=True)


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().upper().strip()
    return re.sub(r'\s+', ' ', s)


def brl(v):
    return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def find_header(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        n = norm(line)
        if ';' in line and 'DATA' in n and ('CUSTO' in n or 'TOT. CUSTO' in n):
            return i
    raise ValueError("Não encontrei uma linha de cabeçalho contendo DATA e CUSTO.")


def parse_num(series):
    def one(x):
        if pd.isna(x): return 0.0
        s = str(x).strip().replace('R$', '').replace(' ', '')
        if not s: return 0.0
        if ',' in s:
            s = s.replace('.', '').replace(',', '.')
        try: return float(s)
        except: return 0.0
    return series.map(one)


def read_report(uploaded):
    raw = uploaded.getvalue()
    text = None
    for enc in ('latin1','utf-8-sig','utf-8'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        raise ValueError("Não foi possível identificar a codificação do arquivo.")

    header = find_header(text)
    df = pd.read_csv(io.StringIO(text), sep=';', skiprows=header, dtype=str, engine='python', on_bad_lines='skip')
    df.columns = [str(c).strip() for c in df.columns]
    colmap = {norm(c): c for c in df.columns}

    date_col = next((orig for n, orig in colmap.items() if n == 'DATA'), None)
    # Prioridade: CUSTO; para relatório de transferências: TOT. CUSTO
    cost_col = next((orig for n, orig in colmap.items() if n == 'CUSTO'), None)
    if not cost_col:
        cost_col = next((orig for n, orig in colmap.items() if n in ('TOT. CUSTO','TOT CUSTO')), None)
    if not date_col or not cost_col:
        raise ValueError(f"Colunas necessárias não encontradas. Detectadas: {', '.join(df.columns)}")

    out = pd.DataFrame()
    out['data'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    out['custo'] = parse_num(df[cost_col])
    out = out[out['data'].notna()].copy()
    out = out[out['custo'].notna()].copy()
    out['arquivo'] = uploaded.name
    out['coluna_custo'] = cost_col
    return out, cost_col


# Manual / passo a passo
MANUAL_PDF = "Passo_a_Passo_Extracao_CMV_Autcom.pdf"

st.markdown("""
<div style="background:white;border:1px solid #e5eaf0;border-radius:16px;
padding:18px 20px;margin:0 0 22px 0;box-shadow:0 7px 22px rgba(15,23,42,.04)">
    <div style="font-weight:800;color:#0f172a;font-size:1.05rem">Precisa de ajuda para extrair as bases?</div>
    <div style="color:#64748b;font-size:.9rem;margin-top:4px">
        Consulte o passo a passo com os filtros e relatórios que devem ser extraídos do Autcom.
    </div>
</div>
""", unsafe_allow_html=True)

try:
    with open(MANUAL_PDF, "rb") as pdf_file:
        st.download_button(
            label="📘 Abrir / baixar passo a passo",
            data=pdf_file.read(),
            file_name=MANUAL_PDF,
            mime="application/pdf",
            use_container_width=True
        )
except FileNotFoundError:
    st.warning(
        f"Manual não encontrado. Coloque o arquivo '{MANUAL_PDF}' "
        "na mesma pasta do app_cmv.py."
    )

st.markdown("### 1. Anexe as três bases")
files = st.file_uploader(
    "Selecione os relatórios CSV exportados do sistema",
    type=['csv'], accept_multiple_files=True,
    help="Pode anexar as três bases de uma vez. O sistema identifica automaticamente DATA e CUSTO/TOT. CUSTO."
)

if not files:
    st.info("Aguardando os arquivos CSV para calcular o CMV.")
    st.markdown("<div class='small'>Regra aplicada: <b>CMV final = Custo × 84,26%</b>. Havendo mais de um mês, cada lançamento é alocado ao seu respectivo mês.</div>", unsafe_allow_html=True)
    st.stop()

frames, errors, mappings = [], [], []
for f in files:
    try:
        d, c = read_report(f)
        frames.append(d)
        mappings.append((f.name, c, len(d)))
    except Exception as e:
        errors.append((f.name, str(e)))

if errors:
    for name, err in errors:
        st.error(f"{name}: {err}")

if not frames:
    st.stop()

base = pd.concat(frames, ignore_index=True)
base['mes'] = base['data'].dt.to_period('M')
base['cmv'] = base['custo'] * FATOR_CMV

st.markdown("### 2. Validação das bases")
cols = st.columns(max(1, min(3, len(mappings))))
for i, (name, cost, rows) in enumerate(mappings):
    with cols[i % len(cols)]:
        st.markdown(f"<div class='card'><div class='label'>{name}</div><div style='font-weight:750;margin-top:7px'>✓ {rows:,} lançamentos</div><div class='small'>Custo: <b>{cost}</b></div></div>".replace(',', '.'), unsafe_allow_html=True)

monthly = base.groupby('mes', as_index=False).agg(Custo=('custo','sum'), CMV=('cmv','sum'), Lancamentos=('custo','size'))
monthly = monthly.sort_values('mes')
total_custo = monthly['Custo'].sum()
total_cmv = monthly['CMV'].sum()

st.markdown("### 3. Resultado")
a,b,c = st.columns(3)
with a: st.markdown(f"<div class='card'><div class='label'>Custo total</div><div class='value'>{brl(total_custo)}</div></div>", unsafe_allow_html=True)
with b: st.markdown(f"<div class='card'><div class='label'>Fator aplicado</div><div class='value'>{FATOR_CMV*100:.2f}%</div></div>".replace('.',','), unsafe_allow_html=True)
with c: st.markdown(f"<div class='card'><div class='label'>CMV final</div><div class='value'>{brl(total_cmv)}</div></div>", unsafe_allow_html=True)

show = monthly.copy()
show['Mês'] = show['mes'].map(lambda p: f"{MESES[p.month]}/{p.year}")
show['Custo'] = show['Custo'].map(brl)
show['CMV (84,26%)'] = show['CMV'].map(brl)
show['Lançamentos'] = show['Lancamentos'].map(lambda x: f"{x:,}".replace(',','.'))
st.dataframe(show[['Mês','Custo','CMV (84,26%)','Lançamentos']], use_container_width=True, hide_index=True)

lines = ["*CMV - ÚNICA ATACADISTA*", ""]
for _, r in monthly.iterrows():
    p = r['mes']
    lines += [f"*{MESES[p.month]}/{p.year}:* {brl(r['CMV'])}"]
if len(monthly) > 1:
    lines += ["", f"*CMV TOTAL:* {brl(total_cmv)}"]
texto = "\n".join(lines)

st.markdown("### 4. Texto pronto para WhatsApp")
st.text_area("Copie o texto abaixo", texto, height=max(190, 100 + len(monthly)*80))
st.code(texto, language=None)

with st.expander("Ver composição por arquivo"):
    detail = base.groupby(['arquivo','mes'], as_index=False).agg(Custo=('custo','sum'), CMV=('cmv','sum'))
    detail['Mês'] = detail['mes'].map(lambda p: f"{MESES[p.month]}/{p.year}")
    detail['Custo'] = detail['Custo'].map(brl)
    detail['CMV'] = detail['CMV'].map(brl)
    st.dataframe(detail[['arquivo','Mês','Custo','CMV']], use_container_width=True, hide_index=True)
