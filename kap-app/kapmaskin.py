import streamlit as st
import pandas as pd
import re
from collections import Counter
from datetime import datetime

st.set_page_config(page_title="Kapmaskinen Pro v33", layout="wide")

# --- FLIK-STRUKTUR ---
tab1, tab2 = st.tabs(["✂️ Kapmaskin & Optimering", "💰 Priskalkyl & Försäljning"])

# --- 1. GEMENSAM SIDOPANEL ---
with st.sidebar:
    st.header("⚙️ Grundinställningar")
    kerf = st.number_input("Sågbladets bredd (mm)", value=4)
    st.divider()
    
    st.header("🏭 Fabriksinställningar")
    if "shift_cost" not in st.session_state:
        st.session_state.shift_cost = 21000.0
    st.session_state.shift_cost = st.number_input("Kostnad per skift (kr)", value=st.session_state.shift_cost, step=500.0)
    
    st.divider()
    st.header("♻️ Nyttigt Spill")
    use_extra = st.checkbox("Spara extra längd?", value=True)
    extra_len = st.number_input("Längd att spara (mm)", value=1000, disabled=not use_extra)
    
    st.header("🗜️ Kapbegränsning")
    max_unique = st.number_input("Max unika längder/planka", min_value=1, max_value=10, value=2)
    
    st.header("📏 Renskär (Trim)")
    trim_front = st.number_input("Renskär FRAM (mm)", value=10)
    trim_back = st.number_input("Renskär BAK (mm)", value=10)
    
    st.divider()
    st.header("➕ Manuellt Lager")
    if "manual_storage" not in st.session_state:
        st.session_state.manual_storage = {}
    m_col1, m_col2 = st.columns(2)
    manual_l = m_col1.number_input("Längd (mm)", value=5400, key="new_ra_l")
    manual_q = m_col2.number_input("Antal", value=100, key="new_ra_q")
    if st.button("➕ Lägg till i lager"):
        st.session_state.manual_storage[manual_l] = st.session_state.manual_storage.get(manual_l, 0) + manual_q
        st.rerun()
    
    if st.session_state.manual_storage:
        for l in sorted(st.session_state.manual_storage.keys(), reverse=True):
            q = st.session_state.manual_storage[l]
            c1, c2 = st.columns([3, 1])
            c1.write(f"{q} st á {l} mm")
            if c2.button("❌", key=f"del_ra_{l}"):
                del st.session_state.manual_storage[l]
                st.rerun()

# --- 2. FLIK 1: KAPMASKIN & OPTIMERING (HELA MOTORN) ---
with tab1:
    st.title("✂️ Kapmaskin & Optimering")
    
    st.header("📂 1. Importera Lager")
    file = st.file_uploader("Ladda upp Excel eller CSV", type=["xlsx", "csv"])

    lager_plankor = []
    for l, q in st.session_state.manual_storage.items():
        lager_plankor.extend([l] * q)

    if file:
        try:
            df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file)
            col_name = 'Paket' if 'Paket' in df.columns else df.columns[0]
            valda_paket = st.multiselect("Välj paket:", options=sorted(df[col_name].astype(str).unique().tolist()))
            valda_df = df[df[col_name].astype(str).isin(valda_paket)] if valda_paket else df
            
            for col in df.columns:
                match = re.findall(r'\d+\.\d+|\d+', str(col).replace(',', '.'))
                if match:
                    val = float(match[0])
                    mm_val = int(val * 1000) if val < 100 else int(val)
                    antal = int(pd.to_numeric(valda_df[col], errors='coerce').sum() or 0)
                    lager_plankor.extend([mm_val] * antal)
            st.success(f"Totalt lager: {len(lager_plankor)} st plankor.")
        except Exception as e:
            st.error(f"Fel vid filinläsning: {e}")

    if lager_plankor:
        st.divider()
        st.header("🎯 2. Mållängder & Procent")
        if "target_lengths" not in st.session_state:
            st.session_state.target_lengths = {1060: 75, 1120: 15, 1000: 10}

        c1, c2, c3 = st.columns([2, 2, 1])
        new_target_l = c1.number_input("Ny mållängd (mm)", value=1200)
        new_target_p = c2.number_input("Önskad %", value=0)
        if c3.button("➕ Lägg till mått"):
            st.session_state.target_lengths[new_target_l] = new_target_p
            st.rerun()

        t_cols = st.columns(len(st.session_state.target_lengths))
        for i, (l, p) in enumerate(list(st.session_state.target_lengths.items())):
            with t_cols[i]:
                st.session_state.target_lengths[l] = st.number_input(f"{l}mm (%)", 0, 100, p, key=f"edit_t_{l}")
                if st.button(f"Ta bort {l}", key=f"del_t_{l}"):
                    del st.session_state.target_lengths[l]
                    st.rerun()

        if 0 < sum(st.session_state.target_lengths.values()) <= 100:
            if st.button("🚀 KÖR OPTIMERING", type="primary", use_container_width=True):
                lager_plankor.sort(reverse=True)
                resultat_raw = []
                targets = {l: p for l, p in st.session_state.target_lengths.items() if p > 0}
                count_tracker = {l: 0 for l in targets}
                extra_tracker = 0
                total_cut_pieces = 0

                for ra_len in lager_plankor:
                    current_bits = []
                    selected_for_this_plank = set()
                    available_len = ra_len - trim_front - trim_back
                    rem = available_len
                    
                    min_len = min(targets.keys())
                    while rem >= min_len:
                        best_bit = None
                        kandidater = sorted(targets.keys(), key=lambda x: (count_tracker[x] / (total_cut_pieces or 1)))
                        for l in kandidater:
                            if len(selected_for_this_plank) >= max_unique and l not in selected_for_this_plank:
                                continue
                            needed = l + (kerf if current_bits else 0)
                            if needed <= rem:
                                best_bit = l
                                break
                        if best_bit:
                            current_bits.append(best_bit)
                            selected_for_this_plank.add(best_bit)
                            count_tracker[best_bit] += 1
                            total_cut_pieces += 1
                            rem -= (best_bit + (kerf if len(current_bits) > 1 else 0))
                        else:
                            break
                    
                    if use_extra:
                        needed_for_extra = extra_len + (kerf if current_bits else 0)
                        if rem >= needed_for_extra:
                            current_bits.append(extra_len)
                            extra_tracker += 1
                            rem -= needed_for_extra

                    if current_bits:
                        resultat_raw.append((ra_len, tuple(sorted(current_bits))))

                # Statistikvisning
                total_ra = sum([r[0] for r in resultat_raw])
                total_nytta = sum([sum(r[1]) for r in resultat_raw])
                spill_procent = ((total_ra - total_nytta) / total_ra) * 100 if total_ra > 0 else 0

                st.divider()
                st.header("📊 Resultat Optimering")
                c_s1, c_s2, c_s3, c_s4 = st.columns(4)
                c_s1.metric("Total råvara", f"{total_ra/1000:.1f} m")
                c_s2.metric("Utfall", f"{total_nytta/1000:.1f} m")
                c_s3.metric("Spill", f"{spill_procent:.2f} %")
                c_s4.metric("Extra bitar", f"{extra_tracker} st")

                txt = f"KAPLISTA v33\n" + "="*45 + f"\nSpill: {spill_procent:.2f}%\n"
                instruktioner = Counter(resultat_raw)
                sorterade_inst = sorted(instruktioner.items(), key=lambda x: x[0][0], reverse=True)

                curr_ui_ra = None
                for (ra_l, bitar), antal in sorterade_inst:
                    rest = ra_l - trim_front - sum(bitar) - (len(bitar)-1)*kerf - trim_back
                    txt += f"{antal} st á {ra_l} mm: Kapa {list(bitar)}\n"
                    if ra_l != curr_ui_ra:
                        st.markdown(f"#### 🪵 Råvara {ra_l} mm")
                        curr_ui_ra = ra_l
                    with st.expander(f"{antal} st plankor -> {list(bitar)}"):
                        st.write(f"Mönster: {' + '.join(map(str, bitar))} mm")
                        st.metric("Spill i ände", f"{rest + trim_back} mm")

                st.download_button("📥 LADDA NER KAPLISTA", txt, f"kaplista_{datetime.now().strftime('%Y%m%d')}.txt", use_container_width=True)

# --- 3. FLIK 2: PRISKALKYL & FÖRSÄLJNING (MED 8-SPLIT OCH TABELL) ---
with tab2:
    st.title("💰 Detaljerad Priskalkyl")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🌲 Dimensioner & Råvara")
        order_m = st.number_input("Order (längd i meter)", min_value=1, value=500)
        raw_price_m3 = st.number_input("Råvarupris (kr/m³)", value=4500.0, step=50.0)
        
        c1, c2 = st.columns(2)
        raw_t = c1.number_input("Råvara Tjocklek (mm)", value=47.0, step=0.1, key="rt_v33")
        raw_b = c2.number_input("Råvara Bredd (mm)", value=150.0, step=0.1, key="rb_v33")
        
        st.write("**Produkt (Nominella mått)**")
        nom_t = c1.number_input("Nominell Tjocklek (mm)", value=22.0, step=0.1, key="nt_v33")
        nom_b = c2.number_input("Nominell Bredd (mm)", value=145.0, step=0.1, key="nb_v33")
        
        st.divider()
        split_parts = st.number_input("Antal delar vid klyvning (st)", min_value=1, value=2, help="Ex: 1=ingen klyvning, 8=klyv till 8 bitar")

    with col_b:
        st.subheader("🏭 Kapacitetskalkyl")
        capacity_m3_shift = st.number_input("Kapacitet för produkt (m³/skift)", value=50.0, step=1.0)
        
        calc_prod_cost_m3 = st.session_state.shift_cost / capacity_m3_shift if capacity_m3_shift > 0 else 0
        st.info(f"Produktionskostnad bas: {calc_prod_cost_m3:.0f} kr/m³")
        
        plane_cost_m3 = st.number_input("Extra hyvelkostnad (kr/m³)", value=200.0)
        setup_cost = st.number_input("Ställkostnad (kr)", value=500.0)
        
        st.divider()
        margin_pct = st.number_input("Vinstmarginal (%)", value=30.0)
        discount_pct = st.number_input("Volymrabatt (%)", value=0.0)

    # Beräkningar
    vol_m_raw = (raw_t * raw_b) / 1_000_000 
    vol_m_nom = (nom_t * nom_b) / 1_000_000
    total_order_m3 = vol_m_nom * order_m
    
    # Självkostnad per löpmeter
    raw_cost_lpm = (vol_m_raw * raw_price_m3) / split_parts
    prod_cost_lpm = vol_m_nom * calc_prod_cost_m3
    extra_cost_lpm = vol_m_nom * plane_cost_m3
    total_cost_lpm = raw_cost_lpm + prod_cost_lpm + extra_cost_lpm
    
    # Försäljningspriser
    sale_lpm_no_disc = total_cost_lpm * (1 + (margin_pct/100))
    final_sale_lpm = sale_lpm_no_disc * (1 - (discount_pct/100))
    final_sale_m3 = final_sale_lpm / vol_m_nom if vol_m_nom > 0 else 0
    
    # Totalsummor
    total_raw_cost = raw_cost_lpm * order_m
    total_prod_cost = (prod_cost_lpm + extra_cost_lpm) * order_m
    total_setup_sale = setup_cost * (1 + (margin_pct/100)) * (1 - (discount_pct/100))
    total_order_price = (final_sale_lpm * order_m) + total_setup_sale

    # Resultatvisning Kalkyl
    st.divider()
    st.header(f"📊 Sammanställning ({total_order_m3:.3f} m³)")
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Pris / lpm", f"{final_sale_lpm:.2f} kr")
    r2.metric("Pris / m³", f"{int(final_sale_m3)} kr")
    r3.metric("Total Order", f"{int(total_order_price)} kr")
    r4.metric("Självkostnad / lpm", f"{total_cost_lpm:.2f} kr")

    st.subheader("📋 Kostnadsnedbrytning (Självkostnad exkl. marginal)")
    breakdown_data = {
        "Kategori": ["Råvara", "Produktion (Lön/Drift)", "Extra hyvling", "Ställkostnad (per order)"],
        "Per löpmeter": [f"{raw_cost_lpm:.2f} kr", f"{prod_cost_lpm:.2f} kr", f"{extra_cost_lpm:.2f} kr", "-"],
        "Total för order": [f"{int(total_raw_cost)} kr", f"{int(prod_cost_lpm * order_m)} kr", f"{int(extra_cost_lpm * order_m)} kr", f"{int(setup_cost)} kr"]
    }
    st.table(pd.DataFrame(breakdown_data))
