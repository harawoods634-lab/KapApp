import streamlit as st
import pandas as pd
import re
from collections import Counter
from datetime import datetime
import io

st.set_page_config(page_title="Kapmaskinen Pro v52", layout="wide")

# --- INITIALISERA SESSION STATE ---
if "manual_storage" not in st.session_state:
    st.session_state.manual_storage = {}
if "target_lengths" not in st.session_state:
    st.session_state.target_lengths = {1060: 0, 1090: 0, 1120: 0}
if "shift_cost" not in st.session_state:
    st.session_state.shift_cost = 21000.0

# --- 1. SIDOPANEL ---
with st.sidebar:
    st.header("⚙️ Grundinställningar")
    kerf = st.number_input("Sågbladets bredd (mm)", value=4)
    
    st.divider()
    st.header("🏭 Fabriksinställningar")
    st.session_state.shift_cost = st.number_input("Kostnad per skift (kr)", value=st.session_state.shift_cost, step=500.0)
    
    st.divider()
    # --- SEKTION: AVANCERAD IMPORT (Kolumn A + D-S) ---
    st.header("📥 Import av Lagerlista")
    st.info("Logik: Kolumn A = Längd, Kolumn D-S = Antal (summeras)")
    uploaded_file = st.file_uploader("Ladda upp Excel (.xlsx)", type=["xlsx"])
    
    if uploaded_file is not None:
        try:
            df_import = pd.read_excel(uploaded_file)
            
            # Förhandsvisning
            st.write("Rådata (första raderna):")
            st.dataframe(df_import.head(3))
            
            if st.button("➕ Summera och lägg till i lager", use_container_width=True):
                count_added = 0
                for _, row in df_import.iterrows():
                    try:
                        # Kolumn A (index 0) är längden. Konvertera m till mm om det behövs.
                        raw_l = float(row.iloc[0])
                        # Om längden är ex 5.4, gör om till 5400
                        l_mm = int(raw_l * 1000) if raw_l < 100 else int(raw_l)
                        
                        # Kolumn D till S är index 3 till och med 18 (19 kolumner totalt)
                        # Vi summerar alla värden i det spannet för denna rad
                        row_quantities = row.iloc[3:19] 
                        q_total = pd.to_numeric(row_quantities, errors='coerce').sum()
                        
                        if q_total > 0:
                            st.session_state.manual_storage[l_mm] = st.session_state.manual_storage.get(l_mm, 0) + int(q_total)
                            count_added += 1
                    except:
                        continue
                
                st.success(f"Klart! Uppdaterade {count_added} unika längder.")
                st.rerun()
        except Exception as e:
            st.error(f"Fel vid inläsning: {e}")

    st.divider()
    # --- SEKTION: MANUELLT ---
    st.header("➕ Knacka själv")
    manual_l = st.number_input("Längd (mm)", value=5400, step=100)
    manual_q = st.number_input("Antal (st)", value=100, step=1)
    if st.button("Lägg till manuellt", use_container_width=True):
        st.session_state.manual_storage[manual_l] = st.session_state.manual_storage.get(manual_l, 0) + manual_q
        st.rerun()

    if st.session_state.manual_storage:
        st.divider()
        st.header("📋 Aktuellt lager")
        if st.button("Rensa lager"):
            st.session_state.manual_storage = {}
            st.rerun()
        for l, q in list(st.session_state.manual_storage.items()):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{q} st á {l} mm")
            if c2.button("❌", key=f"del_{l}"):
                del st.session_state.manual_storage[l]
                st.rerun()

    st.divider()
    max_unique = st.number_input("Max unika längder per planka", min_value=1, max_value=10, value=2)
    use_extra = st.checkbox("Spara extra längd?", value=True)
    extra_len = st.number_input("Längd (mm)", value=1000, disabled=not use_extra)
    trim_front = st.number_input("FRAM (mm)", value=10)
    trim_back = st.number_input("BAK (mm)", value=10)

# --- 2. HUVUDYTA ---
tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

with tab1:
    st.title("✂️ Kapmaskin v52")
    lager_plankor = []
    for l, q in st.session_state.manual_storage.items():
        lager_plankor.extend([l] * q)

    st.header("🎯 1. Mållängder")
    use_pct_logic = st.toggle("Aktivera Procentstyrning", value=False)
    c1, c2, c3 = st.columns([2, 2, 1])
    new_l = c1.number_input("Ny längd", value=1200)
    new_p = c2.number_input("Mål %", 0, 100, 0, disabled=not use_pct_logic)
    if c3.button("➕"):
        st.session_state.target_lengths[new_l] = new_p
        st.rerun()

    t_cols = st.columns(len(st.session_state.target_lengths))
    for i, (l, p) in enumerate(list(st.session_state.target_lengths.items())):
        with t_cols[i]:
            st.session_state.target_lengths[l] = st.number_input(f"{l}mm %", 0, 100, p, key=f"t_{l}", disabled=not use_pct_logic)
            if st.button(f"Ta bort {l}", key=f"del_t_{l}"):
                del st.session_state.target_lengths[l]
                st.rerun()

    if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
        if not lager_plankor:
            st.error("Lagret är tomt!")
        else:
            lager_plankor.sort(reverse=True)
            resultat_raw = []
            targets = sorted(list(st.session_state.target_lengths.keys()), reverse=True)
            goal_pcts = st.session_state.target_lengths
            count_tracker = {l: 0 for l in targets}
            total_cut_pieces = 0
            extra_tracker = 0

            def get_best_combination(rem_len, current_pattern):
                best_pattern = list(current_pattern)
                min_waste = rem_len
                unique_in_pattern = set(current_pattern)
                if use_pct_logic and sum(goal_pcts.values()) > 0:
                    v_p_total = max(1, total_cut_pieces)
                    sorted_targets = sorted(targets, key=lambda x: (count_tracker[x] / v_p_total) - (goal_pcts[x]/100))
                else:
                    sorted_targets = targets
                for t in sorted_targets:
                    if len(unique_in_pattern | {t}) > max_unique: continue
                    needed = t + (kerf if current_pattern else 0)
                    if needed <= rem_len:
                        res_pattern, res_waste = get_best_combination(rem_len - needed, current_pattern + [t])
                        if res_waste < min_waste:
                            min_waste = res_waste
                            best_pattern = res_pattern
                        if min_waste == 0: break
                return best_pattern, min_waste

            for ra_len in lager_plankor:
                available = ra_len - trim_front - trim_back
                pattern, waste_after = get_best_combination(available, [])
                for b in pattern:
                    count_tracker[b] += 1
                    total_cut_pieces += 1
                if use_extra:
                    while waste_after >= (extra_len + kerf):
                        pattern.append(extra_len); waste_after -= (extra_len + kerf); extra_tracker += 1
                    if not pattern and waste_after >= extra_len:
                         pattern.append(extra_len); waste_after -= extra_len; extra_tracker += 1
                resultat_raw.append((ra_len, tuple(sorted(pattern))))

            st.divider()
            total_ra_m = sum([r[0] for r in resultat_raw]) / 1000
            total_nytta_m = sum([sum(r[1]) for r in resultat_raw]) / 1000
            utnyttjande = (total_nytta_m / total_ra_m * 100) if total_ra_m > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Råvara", f"{total_ra_m:.1f} m")
            m2.metric("Utnyttjande", f"{utnyttjande:.1f} %")
            m3.metric("Spill", f"{100 - utnyttjande:.1f} %")
            m4.metric("Nyttigt spill", f"{extra_tracker} st")

            # EXPORT
            export_list = []
            instruktioner = Counter(resultat_raw)
            for (ra_l, bitar), antal in sorted(instruktioner.items(), key=lambda x: x[0][0], reverse=True):
                export_list.append({"Råvara (mm)": ra_l, "Antal": antal, "Mönster": " + ".join(map(str, bitar))})
            df_export = pd.DataFrame(export_list)
            csv_data = df_export.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Ladda ner kapdata (CSV)", data=csv_data, file_name=f"kapning_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv', use_container_width=True)

            stat_df = []
            for l in targets:
                v_p = (count_tracker[l] / max(1, total_cut_pieces) * 100) if total_cut_pieces > 0 else 0
                stat_df.append({"Längd": l, "Antal": count_tracker[l], "Verklig %": f"{v_p:.1f}%"})
            st.table(pd.DataFrame(stat_df))

            st.header("🪵 Kaplista")
            for (ra_l, bitar), antal in sorted(instruktioner.items(), key=lambda x: x[0][0], reverse=True):
                with st.expander(f"📦 {antal} st á {ra_l} mm -> {list(bitar)}"):
                    st.write(f"Mönster: {' + '.join(map(str, bitar))}")

with tab2:
    st.title("💰 Priskalkyl")
    # ... (Samma priskalkylskod som tidigare)
    st.write("Använd priskalkylen för att räkna ut lönsamhet baserat på m³.")
