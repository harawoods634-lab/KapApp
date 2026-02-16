import streamlit as st
import pandas as pd
import re
from collections import Counter
from datetime import datetime
import io

st.set_page_config(page_title="Kapmaskinen Pro v47", layout="wide")

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
    st.header("➕ Lagerhantering")
    manual_l = st.number_input("Längd (mm)", value=5400, step=100, key="input_l")
    manual_q = st.number_input("Antal (st)", value=100, step=1, key="input_q")
    
    if st.button("➕ Lägg till i lager", use_container_width=True):
        st.session_state.manual_storage[manual_l] = st.session_state.manual_storage.get(manual_l, 0) + manual_q
        st.rerun()

    if st.session_state.manual_storage:
        st.write("### Aktuellt lager:")
        for l, q in list(st.session_state.manual_storage.items()):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{q} st á {l} mm")
            if c2.button("🗑️", key=f"del_{l}"):
                del st.session_state.manual_storage[l]
                st.rerun()
    
    st.divider()
    st.header("🗜️ Kapbegränsning")
    max_unique = st.number_input("Max unika längder per planka", min_value=1, max_value=10, value=2)
    
    st.divider()
    st.header("♻️ Nyttigt Spill")
    use_extra = st.checkbox("Spara extra längd?", value=True)
    extra_len = st.number_input("Längd (mm)", value=1000, disabled=not use_extra)
    
    st.header("📏 Renskär")
    trim_front = st.number_input("FRAM (mm)", value=10)
    trim_back = st.number_input("BAK (mm)", value=10)

# --- 2. HUVUDYTA ---
tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

# --- FLIK 1: OPTIMERING ---
with tab1:
    st.title("✂️ Kapmaskin v47")
    
    lager_plankor = []
    for l, q in st.session_state.manual_storage.items():
        lager_plankor.extend([l] * q)

    st.header("🎯 1. Mållängder & Strategi")
    use_pct_logic = st.toggle("Aktivera Procentstyrning", value=False)

    c1, c2, c3 = st.columns([2, 2, 1])
    new_l = c1.number_input("Ny längd", value=1200)
    new_p = c2.number_input("Mål %", 0, 100, 0, disabled=not use_pct_logic)
    if c3.button("➕ Lägg till mål"):
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
                    sorted_targets = sorted(targets, key=lambda x: (count_tracker[x] / max(1, total_cut_pieces)) - (goal_pcts[x]/100))
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

            # --- REDOVISNING OCH EXPORT ---
            st.divider()
            total_ra_m = sum([r[0] for r in resultat_raw]) / 1000
            total_nytta_m = sum([sum(r[1]) for r in resultat_raw]) / 1000
            utnyttjande = (total_nytta_m / total_ra_m * 100) if total_ra_m > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Råvara", f"{total_ra_m:.1f} m")
            m2.metric("Utnyttjande", f"{utnyttjande:.1f} %")
            m3.metric("Spill", f"{100 - utnyttjande:.1f} %")
            m4.metric("Nyttigt spill", f"{extra_tracker} st")

            # Skapa Export-fil
            export_list = []
            instruktioner = Counter(resultat_raw)
            for (ra_l, bitar), antal in sorted(instruktioner.items(), key=lambda x: x[0][0], reverse=True):
                export_list.append({
                    "Råvara (mm)": ra_l,
                    "Antal plankor": antal,
                    "Mönster (mm)": " + ".join(map(str, bitar))
                })
            
            df_export = pd.DataFrame(export_list)
            csv = df_export.to_csv(index=False).encode('utf-8-sig')
            
            st.download_button(
                label="📥 Ladda ner kapdata (CSV)",
                data=csv,
                file_name=f"kaplista_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                use_container_width=True
            )

            stat_df = []
            for l in targets:
                v_p = (count_tracker[l] / max(1, total_cut_pieces) * 100) if total_cut_pieces > 0 else 0
                stat_df.append({"Längd": l, "Antal": count_tracker[l], "Verklig %": f"{v_p:.1f}%"})
            st.table(pd.DataFrame(stat_df))

            st.header("🪵 Kaplista")
            for (ra_l, bitar), antal in sorted(instruktioner.items(), key=lambda x: x[0][0], reverse=True):
                with st.expander(f"📦 {antal} st á {ra_l} mm -> {list(bitar)}"):
                    st.write(f"Mönster: {' + '.join(map(str, bitar))}")

# --- FLIK 2: PRISKALKYL ---
with tab2:
    st.title("💰 Priskalkyl & Rabatter")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🌲 Material & Dimension")
        order_m = st.number_input("Orderstorlek (löpmeter)", min_value=1, value=500)
        raw_price_m3 = st.number_input("Råvarupris (kr/m³)", value=4500.0)
        c1, c2 = st.columns(2)
        raw_t = c1.number_input("Råvara Tjocklek (mm)", value=47.0, step=0.1)
        raw_b = c2.number_input("Råvara Bredd (mm)", value=150.0, step=0.1)
        nom_t = c1.number_input("Färdig Tjocklek (mm)", value=22.0, step=0.1)
        nom_b = c2.number_input("Färdig Bredd (mm)", value=145.0, step=0.1)
        split_parts = st.number_input("Antal delar vid klyvning (st)", min_value=1, value=2)

    with col_b:
        st.subheader("🏭 Produktion & Rabatt")
        capacity_m3_shift = st.number_input("Kapacitet (m³/skift)", value=50.0)
        plane_cost_m3 = st.number_input("Extra hyvelkostnad (kr/m³)", value=200.0)
        setup_cost = st.number_input("Ställkostnad (kr)", value=500.0)
        margin_pct = st.number_input("Vinstmarginal (%)", value=30.0)
        discount_pct = st.number_input("Procentrabatt till kund (%)", min_value=0.0, max_value=100.0, value=0.0)

    # Beräkningar
    calc_prod_cost_m3 = st.session_state.shift_cost / capacity_m3_shift if capacity_m3_shift > 0 else 0
    vol_m_raw = (raw_t * raw_b) / 1_000_000 
    vol_m_nom = (nom_t * nom_b) / 1_000_000
    total_order_m3 = vol_m_nom * order_m
    
    raw_cost_lpm = (vol_m_raw * raw_price_m3) / split_parts
    prod_cost_lpm = vol_m_nom * (calc_prod_cost_m3 + plane_cost_m3)
    total_cost_lpm = raw_cost_lpm + prod_cost_lpm
    
    base_sale_lpm = total_cost_lpm * (1 + (margin_pct/100))
    final_sale_lpm = base_sale_lpm * (1 - (discount_pct/100))
    total_order_price = (final_sale_lpm * order_m) + (setup_cost * (1 + (margin_pct/100)))
    total_discount_amount = (base_sale_lpm - final_sale_lpm) * order_m

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("Pris / lpm (efter rabatt)", f"{final_sale_lpm:.2f} kr")
    res2.metric("Totalvärde Order", f"{int(total_order_price)} kr")
    res3.metric("Rabatt i kr", f"{int(total_discount_amount)} kr", delta=f"-{discount_pct}%")

    vol1, vol2, vol3 = st.columns(3)
    vol1.metric("Total Volym", f"{total_order_m3:.3f} m³")
    vol2.metric("Beräknad Vikt", f"{int(total_order_m3 * 500)} kg")
    vol3.metric("Antal löpmeter", f"{order_m} m")
