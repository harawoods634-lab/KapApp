import streamlit as st
import pandas as pd
import re
from collections import Counter

st.set_page_config(page_title="Kapmaskinen Pro v35.5", layout="wide")

st.markdown("""
    <style>
    .plank-box { display: flex; border: 2px solid #333; background: #fff; height: 40px; margin-bottom: 8px; border-radius: 4px; overflow: hidden; }
    .segment { display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; color: white; border-right: 1px solid #fff; }
    .trim { background-color: #ff4b4b; } .target { background-color: #2e7d32; } 
    .extra { background-color: #1976d2; } .waste { background-color: #757575; }
    </style>
    """, unsafe_allow_html=True)

if "manual_storage" not in st.session_state: st.session_state.manual_storage = {}
if "target_lengths" not in st.session_state: st.session_state.target_lengths = {1060: 0, 1120: 0}

with st.sidebar:
    st.title("⚙️ Inställningar")
    kerf = st.number_input("Sågblad (mm)", value=4)
    trim_f = st.number_input("Renskär Fram (mm)", value=10)
    trim_b = st.number_input("Renskär Bak (mm)", value=10)
    max_u = st.slider("Max unika mått/planka", 1, 5, 2)
    st.divider()
    use_ex = st.checkbox("Spara spill?", value=True)
    ex_l = st.number_input("Minsta sparlängd (mm)", value=1000, disabled=not use_ex)
    st.divider()
    st.subheader("➕ Manuellt Lager")
    m_l = st.number_input("Längd (mm)", value=5400, key="ml")
    m_q = st.number_input("Antal", value=100, key="mq")
    if st.button("Lägg till i lager"):
        st.session_state.manual_storage[m_l] = st.session_state.manual_storage.get(m_l, 0) + m_q

tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Kalkyl"])

with tab1:
    st.header("📂 1. Lager & Mått")
    file = st.file_uploader("Excel-fil (Kolumn D-R)", type=["xlsx"])
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
        st.success(f"Lager laddat: {len(lager)} st")

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
            del st.session_state.target_lengths[l]
            st.rerun()
    st.session_state.target_lengths = targets

    if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
        lager.sort(reverse=True)
        res, counts, total_bits, total_w, total_r = [], {l: 0 for l in targets}, 0, 0, sum(lager)
        is_pct = sum(targets.values()) > 0

        for r_len in lager:
            bits, uniq, rem = [], set(), r_len - trim_f - trim_b
            while rem >= min(targets.keys()):
                best = None
                cands = sorted(targets.keys(), key=lambda x: (counts[x]/(total_bits or 1)) > (targets[x]/100)) if is_pct else sorted(targets.keys(), reverse=True)
                for l in cands:
                    if len(uniq) >= max_u and l not in uniq: continue
                    if (l + (kerf if bits else 0)) <= rem:
                        best = l
                        break
                if best:
                    bits.append(best); uniq.add(best); counts[best] += 1; total_bits += 1; rem -= (best + kerf)
                else: break
            
            a_rem, has_ex = (rem + kerf if bits else rem), False
            if use_ex and a_rem >= ex_l:
                bits.append(ex_l); has_ex = True; a_rem -= (ex_l + kerf)
            
            total_w += (a_rem + trim_f + trim_b)
            res.append({"r_l": r_len, "bits": bits, "rem": a_rem, "ex": has_ex})
        
        st.session_state.results = {"res": res, "waste": (total_w/total_r*100 if total_r else 0)}

    if "results" in st.session_state:
        r_data = st.session_state.results
        st.divider()
        st.subheader("🪵 Råvara att använda")
        usage = Counter([r['r_l'] for r in r_data['res'] if r['bits']])
        cols = st.columns(len(usage) if usage else 1)
        for i, (l, q) in enumerate(sorted(usage.items(), reverse=True)):
            cols[i].metric(f"{l} mm", f"{q} st")

        st.subheader("📦 Produktion")
        all_b = [b for r in r_data['res'] for b in r['bits']]
        b_st = Counter(all_b)
        st.write(f"**Spill:** {r_data['waste']:.1f}% | **Total lpm:** {sum(all_b)/1000:.1f} m")
        st.table(pd.DataFrame([{"Längd": f"{l} mm", "Antal": f"{b_st[l]} st"} for l in sorted(targets.keys(), reverse=True)]))

        st.subheader("🪚 Kaplista")
        patterns = Counter([(r['r_l'], tuple(r['bits']), r['ex']) for r in r_data['res'] if r['bits']])
        for (rl, bits, ex), q in patterns.items():
            st.write(f"**{q} st** á **{rl} mm** -> `{list(bits)}`")
            html = f'<div class="plank-box"><div class="segment trim" style="width:{(trim_f/rl)*100}%"></div>'
            for i, b in enumerate(bits):
                t = "extra" if (use_ex and b==ex_l and i==len(bits)-1 and ex) else "target"
                html += f'<div class="segment {t}" style="width:{(b/rl)*100}%">{b}</div>'
                html += f'<div style="width:{(kerf/rl)*100}%; background:#000;"></div>'
            st.markdown(html + '</div>', unsafe_allow_html=True)
