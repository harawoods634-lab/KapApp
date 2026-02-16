import streamlit as st
import pandas as pd
import re
from collections import Counter

# --- KONFIGURATION & CSS ---
st.set_page_config(page_title="Kapmaskinen Pro v35.9", layout="wide")

st.markdown("""
    <style>
    .metric-card {
        background-color: #262730; 
        border: 1px solid #464b5d;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-card b { color: #00ffcc; font-size: 1.1rem; }
    .metric-card h2 { color: #ffffff; margin: 5px 0; }
    .plank-box { display: flex; border: 2px solid #333; background: #fff; height: 40px; margin-bottom: 8px; border-radius: 4px; overflow: hidden; }
    .segment { display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; color: white; border-right: 1px solid #fff; }
    .trim { background-color: #ff4b4b; } 
    .target { background-color: #2e7d32; } 
    .extra { background-color: #1976d2; } 
    .waste { background-color: #757575; }
    </style>
    """, unsafe_allow_html=True)

# --- INITIALISERING ---
if "manual_storage" not in st.session_state: st.session_state.manual_storage = {}
if "target_lengths" not in st.session_state: st.session_state.target_lengths = {1060: 0, 1120: 0}
if "results" not in st.session_state: st.session_state.results = None

# --- SIDOPANEL ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    kerf = st.number_input("Sågblad (mm)", value=4)
    trim_f = st.number_input("Renskär Fram (mm)", value=10)
    trim_b = st.number_input("Renskär Bak (mm)", value=10)
    
    st.divider()
    st.subheader("🗜️ Begränsningar")
    # NYTT: Max antal bitar totalt per planka
    max_total_pieces = st.number_input("Max antal bitar totalt / planka", min_value=1, value=10)
    # Max unika längder (din tidigare inställning)
    max_unique = st.slider("Max unika mått / planka", 1, 5, 2)
    
    st.divider()
    use_ex = st.checkbox("Spara extra längd?", value=True)
    ex_l = st.number_input("Minsta sparlängd (mm)", value=1000, disabled=not use_ex)
    
    st.divider()
    st.subheader("➕ Manuellt Lager")
    m_l = st.number_input("Längd (mm)", value=5400, key="ml")
    m_q = st.number_input("Antal", value=100, key="mq")
    if st.button("Lägg till i lager"):
        st.session_state.manual_storage[m_l] = st.session_state.manual_storage.get(m_l, 0) + m_q

tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

# --- FLIK 1: OPTIMERING ---
with tab1:
    st.header("📂 Lager & Mått")
    file = st.file_uploader("Ladda upp Excel-fil (Kolumn D-R)", type=["xlsx"])
    lager = [l for l, q in st.session_state.manual_storage.items() for _ in range(q)]
    
    if file:
        df = pd.read_excel(file).iloc[:, 3:18]
        for col in df.columns:
            m = re.findall(r"[-+]?\d*\.\d+|\d+", str(col).replace(',', '.'))
            if m:
                v = float(m[0])
                mm = int(v * 1000) if v < 100 else int(v)
                q = int(pd.to_numeric(df[col], errors='coerce').sum() or 0)
                if q > 0: lager.extend([mm] * q)

    c1, c2, c3 = st.columns([2,2,1])
    n_l = c1.number_input("Ny mållängd (mm)", value=1090)
    n_p = c2.number_input("Mål %", value=0)
    if c3.button("➕ Lägg till"):
        st.session_state.target_lengths[n_l] = n_p
        st.rerun()

    targets = {}
    for l in sorted(st.session_state.target_lengths.keys(), reverse=True):
        col1, col2, col3 = st.columns([2,2,1])
        col1.write(f"**{l} mm**")
        targets[l] = col2.number_input(f"% {l}", 0, 100, st.session_state.target_lengths[l], key=f"p_{l}", label_visibility="collapsed")
        if col3.button("🗑️", key=f"r_{l}"):
            del st.session_state.target_lengths[l]; st.rerun()

    if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
        lager.sort(reverse=True)
        res, counts, total_bits, total_w, total_r = [], {l: 0 for l in targets}, 0, 0, sum(lager)
        is_pct = sum(targets.values()) > 0
        
        for r_len in lager:
            bits, uniq, rem = [], set(), r_len - trim_f - trim_b
            
            # Algoritmen tar nu hänsyn till max_total_pieces
            while rem >= (min(targets.keys()) if targets else 1e9) and len(bits) < max_total_pieces:
                best = None
                cands = sorted(targets.keys(), key=lambda x: (counts[x]/(total_bits or 1)) > (targets[x]/100)) if is_pct else sorted(targets.keys(), reverse=True)
                
                for l in cands:
                    # Kontrollera både unika mått och fysisk plats
                    if len(uniq) >= max_unique and l not in uniq: continue
                    if (l + (kerf if bits else 0)) <= rem:
                        best = l
                        break
                
                if best:
                    bits.append(best); uniq.add(best); counts[best] += 1; total_bits += 1; rem -= (best + kerf)
                else: break
            
            a_rem, h_ex = (rem + kerf if bits else rem), False
            # Kolla om vi får plats med en "extra" bit även inom max_total_pieces
            if use_ex and a_rem >= ex_l and len(bits) < max_total_pieces:
                bits.append(ex_l); h_ex = True; a_rem -= (ex_l + kerf)
            
            total_w += (a_rem + trim_f + trim_b)
            res.append({"r_l": r_len, "bits": bits, "rem": a_rem, "ex": h_ex})
        
        st.session_state.results = {"res": res, "waste": (total_w/total_r*100 if total_r else 0), "total_lpm": sum([sum(r['bits']) for r in res])/1000}

    # (Resultatvisning och kaplista behålls som i v35.8...)
    if st.session_state.results:
        r = st.session_state.results
        st.divider()
        st.subheader("🪵 1. Råvara att hämta")
        usage = Counter([x['r_l'] for x in r['res'] if x['bits']])
        raw_cols = st.columns(min(len(usage), 6))
        for i, (l, q) in enumerate(sorted(usage.items(), reverse=True)):
            with raw_cols[i % 6]:
                st.markdown(f"""<div class="metric-card"><b>{l} mm</b><br><h2>{q} st</h2></div>""", unsafe_allow_html=True)
        
        # Kaplistan visar nu det begränsade antalet bitar
        st.subheader("🪚 3. Kaplista")
        patterns = Counter([(row['r_l'], tuple(row['bits']), row['ex']) for row in r['res'] if row['bits']])
        for (rl, bits, ex), q in patterns.items():
            st.markdown(f"**{q} st** á **{rl} mm** -> `{list(bits)}`")
            html = f'<div class="plank-box"><div class="segment trim" style="width:{(trim_f/rl)*100}%"></div>'
            for i, b in enumerate(bits):
                t = "extra" if (use_ex and b==ex_l and i==len(bits)-1 and ex) else "target"
                html += f'<div class="segment {t}" style="width:{(b/rl)*100}%">{b}</div>'
                html += f'<div style="width:{(kerf/rl)*100}%; background:#000;"></div>'
            st.markdown(html + '</div>', unsafe_allow_html=True)
