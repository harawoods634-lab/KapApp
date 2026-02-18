import streamlit as st
import pandas as pd
from collections import Counter
from datetime import datetime

st.set_page_config(page_title="Kapmaskinen Pro v81.0", layout="wide")

# --- SMART CACHING ---
@st.cache_data
def process_excel(file):
    try:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        raw_rows = []
        for col_idx in range(3, 19): 
            header_val = df.columns[col_idx]
            try:
                raw_l = float(header_val)
                l_mm = int(round(raw_l * 1000)) if raw_l < 100 else int(round(raw_l))
                for row_idx in range(len(df)):
                    qty = pd.to_numeric(df.iloc[row_idx, col_idx], errors='coerce')
                    if not pd.isna(qty) and qty > 0:
                        raw_rows.append({
                            'id': f"row_{row_idx}_col_{col_idx}_{datetime.now().timestamp()}",
                            'l': l_mm, 'q': int(qty),
                            'name': f"Paket {df.iloc[row_idx, 1] if len(df.columns)>1 else row_idx}"
                        })
            except: continue
        return raw_rows
    except: return None

# --- INITIALISERA SESSION STATE ---
if "inventory_rows" not in st.session_state:
    st.session_state.inventory_rows = [] 
if "target_lengths" not in st.session_state:
    st.session_state.target_lengths = {1060: 0, 1090: 0, 1120: 0}

# --- SIDOPANEL: LAGER ---
with st.sidebar:
    st.title("📦 Lagerhantering")
    uploaded_file = st.file_uploader("Ladda upp Excel/CSV", type=["xlsx", "csv"])
    if uploaded_file and st.button("📥 Importera till lager"):
        new_data = process_excel(uploaded_file)
        if new_data:
            st.session_state.inventory_rows.extend(new_data)
    
    st.divider()
    st.subheader("➕ Manuellt lager")
    m_l = st.number_input("Längd (mm)", value=5400, step=100)
    m_q = st.number_input("Antal (st)", value=100)
    if st.button("Lägg till brädor"):
        st.session_state.inventory_rows.append({'id': str(datetime.now().timestamp()), 'l': m_l, 'q': m_q, 'name': "Manuellt"})
        st.rerun()

    st.divider()
    st.subheader("📋 Inläst lager")
    if st.session_state.inventory_rows:
        if st.button("🗑️ Töm allt lager"):
            st.session_state.inventory_rows = []; st.rerun()
        for i, item in enumerate(st.session_state.inventory_rows):
            col_info, col_del = st.columns([4, 1])
            col_info.write(f"**{item['q']}st** {item['l']}mm")
            if col_del.button("❌", key=f"del_{item['id']}"):
                st.session_state.inventory_rows.pop(i); st.rerun()

# --- HUVUDYTA ---
tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

with tab1:
    st.title("✂️ Kapoptimering v81.0")
    
    with st.expander("🎯 Mållängder & Procent (Sätt 0% för fri optimering)", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_tl = c1.number_input("Ny längd (mm)", value=1200)
        new_tp = c2.number_input("Mål (%)", value=0)
        if c3.button("Lägg till"):
            st.session_state.target_lengths[new_tl] = new_tp; st.rerun()
        
        for tl in sorted(st.session_state.target_lengths.keys()):
            cl, cp, cd = st.columns([2, 2, 1])
            cl.write(f"**{tl} mm**")
            st.session_state.target_lengths[tl] = cp.number_input(f"% {tl}", 0, 100, st.session_state.target_lengths[tl], key=f"p_{tl}", label_visibility="collapsed")
            if cd.button("❌", key=f"d_{tl}"): del st.session_state.target_lengths[tl]; st.rerun()

    st.header("🛠️ Strategi")
    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
    opt_mode = col_s1.selectbox("Gruppering:", ["Målstyrd (Blanda fritt)", "Brädstyrd (En längd/bräda)", "Poststyrd (Hela paket)", "Längdstyrd (Samma råvarulängd)"])
    use_extra = col_s2.toggle("Extra bitar", value=True)
    extra_l = col_s3.number_input("Längd extra (mm)", value=1000)
    kerf = 4; trim = 20

    if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
        if not st.session_state.inventory_rows:
            st.error("Lagret är tomt!")
        else:
            targets = sorted(list(st.session_state.target_lengths.keys()), reverse=True)
            goal_pcts = st.session_state.target_lengths
            count_t = {l: 0 for l in targets}; total_c = 0; total_ra = 0; total_nytta = 0; extra_c = 0
            results = []

            def get_best_pattern(r_l, max_u):
                best_p, min_w, best_s = [], r_l, -999999
                def backtrack(rem, cur_p):
                    nonlocal best_p, min_w, best_s
                    # Sortering: Prioritera mått som ligger under sin %-nivå. 
                    # Om mål är 0%, använd minsta spill som sekundär drivkraft.
                    def score_func(x):
                        if total_c == 0: return goal_pcts[x]
                        return goal_pcts[x] - (count_t[x]/total_c*100)

                    sorted_t = sorted(targets, key=score_func, reverse=True)
                    found = False
                    for t in sorted_t:
                        cost = t + (kerf if cur_p else 0)
                        if cost <= rem:
                            if t not in cur_p and len(set(cur_p)) >= max_u: continue
                            found = True; backtrack(rem-cost, cur_p + [t])
                            if min_w < 10: return
                    if not found:
                        # Poängberäkning: Mål + utnyttjandegrad
                        s = sum(score_func(b) for b in cur_p) * 1000 - rem
                        if s > best_s: best_s, best_p, min_w = s, cur_p, rem
                backtrack(r_l - trim, [])
                return best_p, min_w

            # Kör logiken baserat på valt läge
            raw_data = st.session_state.inventory_rows
            if "Längdstyrd" in opt_mode:
                u_l = set(r['l'] for r in raw_data)
                items = [{'l': l, 'q': sum(r['q'] for r in raw_data if r['l']==l)} for l in u_l]
            elif "Poststyrd" in opt_mode:
                items = raw_data
            else: # Målstyrd/Brädstyrd - dela upp i enskilda brädor
                items = []
                for r in raw_data: items.extend([{'l': r['l'], 'q': 1}] * r['q'])

            for item in items:
                p, w = get_best_pattern(item['l'], 1 if "Målstyrd" not in opt_mode else 5)
                p_f = list(p)
                if use_extra:
                    while w >= (extra_l + kerf): p_f.append(extra_l); w -= (extra_l + kerf); extra_c += item['q']
                for _ in range(item['q']):
                    for b in p_f:
                        if b in count_t: count_t[b]+=1; total_c+=1
                    total_ra += item['l']; total_nytta += sum(p_f)
                results.append((item['l'], tuple(sorted(p_f)), w, item['q']))

            # --- RESULTATVISNING ---
            st.divider()
            spill_pct = (1 - (total_nytta / total_ra)) * 100 if total_ra > 0 else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("SPILL TOTALT", f"{spill_pct:.2f} %", delta_color="inverse")
            c2.metric("Råvara", f"{total_ra/1000:.1f} m")
            c3.metric("Antal huvudbitar", total_c)
            c4.metric("Extra bitar", extra_c)

            st.header("📋 Kaplista")
            export_txt = f"KAPLISTA v81.0\nSPILL: {spill_pct:.2f}%\n" + "="*50 + "\n"
            
            # Gruppera mönster för snyggare lista
            final_summary = Counter(results)
            for (rl, bits, w, _), qty in final_summary.items():
                row_spill = (w / rl) * 100
                line = f"{qty} st á {rl} mm --> {list(bits)} (Spill: {int(w)} mm / {row_spill:.1f}%)"
                export_txt += line + "\n"
                with st.expander(line):
                    st.write(f"Mönster: {' + '.join(map(str, bits))} mm")
            
            st.download_button("📥 LADDA NER KAPLISTA (TXT)", export_txt, "kaplista.txt", use_container_width=True, type="primary")
