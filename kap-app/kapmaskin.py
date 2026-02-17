import streamlit as st
import pandas as pd
from collections import Counter
from datetime import datetime

st.set_page_config(page_title="Kapmaskinen Pro v71.2", layout="wide")

# --- SMART CACHING ---
@st.cache_data
def process_excel(file):
    try:
        df = pd.read_excel(file) if hasattr(file, 'name') and file.name.endswith('.xlsx') else pd.read_csv(file)
        new_inventory = {}
        for col_idx in range(3, 19):
            if col_idx >= len(df.columns): break
            header_val = df.columns[col_idx]
            try:
                raw_l = float(header_val)
                l_mm = int(round(raw_l * 1000)) if raw_l < 100 else int(round(raw_l))
                total_qty = pd.to_numeric(df.iloc[:, col_idx], errors='coerce').fillna(0).sum()
                if total_qty > 0:
                    new_inventory[l_mm] = new_inventory.get(l_mm, 0) + int(total_qty)
            except: continue
        return new_inventory
    except:
        return None

if "inventory" not in st.session_state:
    st.session_state.inventory = {} 
if "target_lengths" not in st.session_state:
    st.session_state.target_lengths = {1060: 32, 1090: 46, 1120: 22}

# --- SIDOPANEL ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    kerf = st.number_input("Sågbladets bredd (mm)", value=4)
    trim_total = st.number_input("Renskär totalt (mm)", value=20)
    
    st.divider()
    st.header("📥 Excel-import")
    uploaded_file = st.file_uploader("Ladda upp råvarufil", type=["xlsx", "csv"])
    if uploaded_file is not None:
        if st.button("Läs in fil"):
            data = process_excel(uploaded_file)
            if data:
                st.session_state.inventory.update(data)
                st.success("Lager uppdaterat!")
                st.rerun()

    st.header("➕ Manuellt Lager")
    m_col1, m_col2 = st.columns(2)
    manual_l = m_col1.number_input("Längd (mm)", value=5400, key="new_ra_l")
    manual_q = m_col2.number_input("Antal", value=100, key="new_ra_q")
    if st.button("➕ Lägg till"):
        st.session_state.inventory[manual_l] = st.session_state.inventory.get(manual_l, 0) + manual_q
        st.rerun()

# --- HUVUDYTA ---
tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

with tab1:
    st.title("✂️ Kapoptimering v71.2")
    
    st.header("🎯 Mållängder & Procent")
    use_pct_logic = st.toggle("Tvinga fram procentmål (Högsta prioritet)", value=True)
    
    t_cols = st.columns(len(st.session_state.target_lengths))
    for i, (l, p) in enumerate(list(st.session_state.target_lengths.items())):
        with t_cols[i]:
            st.session_state.target_lengths[l] = st.number_input(f"{l}mm %", 0, 100, p, key=f"t_{l}")
            if st.button(f"Ta bort {l}", key=f"del_t_{l}"):
                del st.session_state.target_lengths[l]
                st.rerun()

    st.divider()
    max_unique = st.number_input("Max unika mått per planka", 1, 5, 2)
    use_extra = st.checkbox("Fyll ut med extra bitar", value=True)
    extra_len = st.number_input("Längd på extra bit (mm)", value=1000)

    if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
        if not st.session_state.inventory:
            st.warning("Lagret är tomt!")
        else:
            targets = sorted(list(st.session_state.target_lengths.keys()), reverse=True)
            goal_pcts = st.session_state.target_lengths
            count_tracker = {l: 0 for l in targets}
            total_cut_pieces = 0
            extra_tracker = 0
            total_ra_mm = 0
            total_nytta_mm = 0
            
            all_pieces = []
            for l, q in st.session_state.inventory.items():
                all_pieces.extend([l] * q)
            all_pieces.sort(reverse=True)

            def find_forced_pattern(available_len):
                best_p, min_waste, best_score = [], available_len, -999999999
                def backtrack(rem, current_p):
                    nonlocal best_p, min_waste, best_score
                    found_any = False
                    def get_urgent_score(x):
                        if not use_pct_logic: return 0
                        if total_cut_pieces == 0: return goal_pcts[x]
                        current_pct = (count_tracker[x] / total_cut_pieces * 100)
                        return goal_pcts[x] - current_pct

                    sorted_targets = sorted(targets, key=get_urgent_score, reverse=True)
                    for t in sorted_targets:
                        cost = t + (kerf if current_p else 0)
                        if cost <= rem:
                            if t not in current_p and len(set(current_p)) >= max_unique: continue
                            found_any = True
                            backtrack(rem - cost, current_p + [t])
                            if min_waste < 50: return 
                    if not found_any:
                        s = sum(get_urgent_score(bit) for bit in current_p) * 1000
                        if s > best_score or (s == best_score and rem < min_waste):
                            best_score, best_p, min_waste = s, current_p, rem
                backtrack(available_len, [])
                return best_p, min_waste

            final_results_raw = []
            prog = st.progress(0)
            for i, r_len in enumerate(all_pieces):
                p, waste = find_forced_pattern(r_len - trim_total)
                if p:
                    total_ra_mm += r_len
                    p_list = list(p)
                    for bit in p_list:
                        count_tracker[bit] += 1
                        total_cut_pieces += 1
                        total_nytta_mm += bit
                    if use_extra:
                        while waste >= (extra_len + kerf):
                            p_list.append(extra_len)
                            waste -= (extra_len + kerf)
                            extra_tracker += 1
                            total_nytta_mm += extra_len
                    final_results_raw.append((r_len, tuple(sorted(p_list)), waste))
                if i % 20 == 0: prog.progress((i + 1) / len(all_pieces))
            prog.empty()

            # --- RESULTATVISNING ---
            st.divider()
            st.header("📊 Resultat & Kontroll")
            
            m_cols = st.columns(len(targets))
            for i, t in enumerate(targets):
                act_pct = (count_tracker[t] / total_cut_pieces * 100) if total_cut_pieces > 0 else 0
                diff = act_pct - goal_pcts[t]
                m_cols[i].metric(f"{t} mm", f"{act_pct:.1f}%", f"{diff:.1f}% från mål")

            spill_p = (1 - (total_nytta_mm / total_ra_mm)) * 100 if total_ra_mm > 0 else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total råvara", f"{total_ra_mm/1000:.1f} m")
            c2.metric("Utfall", f"{total_nytta_mm/1000:.1f} m")
            c3.metric("Spill", f"{spill_p:.2f} %")
            c4.metric("Extra bitar", f"{extra_tracker} st")

            # --- EXPORT-GENERERING ---
            export_txt = f"KAPLISTA - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            export_txt += "="*50 + "\nSUMMERING ANTAL BITAR:\n"
            for t in sorted(targets):
                export_txt += f"{t} mm: {count_tracker[t]} st\n"
            if extra_tracker > 0:
                export_txt += f"{extra_len} mm (Extra): {extra_tracker} st\n"
            export_txt += f"\nTotal råvara: {total_ra_mm/1000:.1f} m\nSpill: {spill_p:.2f}%\n"
            export_txt += "="*50 + "\n\nKAPINSTRUKTIONER:\n"

            summary = Counter(final_results_raw)
            for (ra_l, bitar, rest), antal in summary.items():
                line = f"{antal} st á {ra_l} mm  -->  Kapa: {list(bitar)}  (Spill: {int(rest)} mm)\n"
                export_txt += line
                with st.expander(f"{antal} st á {ra_l} mm -> {list(bitar)}"):
                    st.write(f"Mönster: {' + '.join(map(str, bitar))} mm")
                    st.write(f"Ändspill: {int(rest)} mm")

            st.download_button("📥 LADDA NER KAPLISTA", export_txt, f"kaplista_{datetime.now().strftime('%Y%m%d_%H%M')}.txt", use_container_width=True, type="primary")

with tab2:
    st.title("💰 Priskalkyl")
    st.info("Kalkylatorn kan läggas här.")
