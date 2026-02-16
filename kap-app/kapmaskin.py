import streamlit as st
import pandas as pd
from collections import Counter

st.set_page_config(page_title="Kapmaskinen Pro v65", layout="wide")

# --- INITIALISERA SESSION STATE ---
if "inventory" not in st.session_state:
    st.session_state.inventory = {} 
if "target_lengths" not in st.session_state:
    st.session_state.target_lengths = {1060: 0, 1090: 0, 1120: 0}
if "shift_cost" not in st.session_state:
    st.session_state.shift_cost = 21000.0

# --- 1. SIDOPANEL ---
with st.sidebar:
    st.header("⚙️ Inställningar")
    kerf = st.number_input("Sågbladets bredd (mm)", value=4)
    trim_total = st.number_input("Renskär totalt (mm)", value=20)
    
    st.divider()
    st.header("📥 Excel-import")
    uploaded_file = st.file_uploader("Ladda upp matris (.xlsx)", type=["xlsx"])
    if uploaded_file is not None:
        if st.button("Läs in Excel"):
            try:
                df = pd.read_excel(uploaded_file)
                for col_idx in range(3, 19):
                    if col_idx >= len(df.columns): break
                    header_val = df.columns[col_idx]
                    try:
                        raw_l = float(header_val)
                        l_mm = int(round(raw_l * 1000)) if raw_l < 100 else int(round(raw_l))
                        total_qty = pd.to_numeric(df.iloc[:, col_idx], errors='coerce').fillna(0).sum()
                        if total_qty > 0:
                            st.session_state.inventory[l_mm] = st.session_state.inventory.get(l_mm, 0) + int(total_qty)
                    except: continue
                st.rerun()
            except Exception as e:
                st.error(f"Importfel: {e}")

    # --- DIN KODSNUTT: MANUELLT LAGER ---
    st.divider()
    st.header("➕ Manuellt Lager")
    m_col1, m_col2 = st.columns(2)
    manual_l = m_col1.number_input("Längd (mm)", value=5400, key="new_ra_l")
    manual_q = m_col2.number_input("Antal", value=100, key="new_ra_q")
    if st.button("➕ Lägg till i lager"):
        st.session_state.inventory[manual_l] = st.session_state.inventory.get(manual_l, 0) + manual_q
        st.rerun()

    if st.session_state.inventory:
        st.divider()
        st.subheader("📋 Lageröversikt")
        if st.button("Töm hela lagret", type="secondary"):
            st.session_state.inventory = {}
            st.rerun()
        for l in sorted(st.session_state.inventory.keys(), reverse=True):
            q = st.session_state.inventory[l]
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{q} st** á {l} mm")
            if c2.button("❌", key=f"del_inv_{l}"):
                del st.session_state.inventory[l]
                st.rerun()

# --- 2. HUVUDYTA ---
tab1, tab2 = st.tabs(["✂️ Optimering", "💰 Priskalkyl"])

with tab1:
    st.title("✂️ Kapmaskin v65")
    
    st.header("🎯 Mållängder")
    use_pct_logic = st.toggle("Prioritera procentmål", value=True)
    
    c1, c2, c3 = st.columns([2, 2, 1])
    new_l = c1.number_input("Måttlängd (mm)", value=1090)
    new_p = c2.number_input("Mål %", 0, 100, 33)
    if c3.button("Lägg till mått"):
        st.session_state.target_lengths[new_l] = new_p
        st.rerun()

    t_cols = st.columns(len(st.session_state.target_lengths))
    for i, (l, p) in enumerate(list(st.session_state.target_lengths.items())):
        with t_cols[i]:
            st.session_state.target_lengths[l] = st.number_input(f"{l}mm %", 0, 100, p, key=f"t_{l}")
            if st.button(f"Ta bort {l}", key=f"del_t_{l}"):
                del st.session_state.target_lengths[l]
                st.rerun()

    st.divider()
    max_unique = st.number_input("Max unika mått per planka", 1, 5, 2)
    use_extra = st.checkbox("Spara nyttigt spill (fyll ut brädan)", value=True)
    extra_len = st.number_input("Minsta spill-längd (mm)", value=1000)

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
            
            def find_best_pattern(available_len):
                best_p, min_waste, best_score = [], available_len, -999999
                def backtrack(rem, current_p):
                    nonlocal best_p, min_waste, best_score
                    found_any = False
                    def get_need_score(x):
                        if not use_pct_logic or total_cut_pieces == 0: return 0
                        return goal_pcts[x] - (count_tracker[x] / total_cut_pieces * 100)
                    for t in sorted(targets, key=get_need_score, reverse=True):
                        cost = t + (kerf if current_p else 0)
                        if cost <= rem:
                            if t not in current_p and len(set(current_p)) >= max_unique: continue
                            found_any = True
                            backtrack(rem - cost, current_p + [t])
                    if not found_any:
                        score = sum(get_need_score(bit) for bit in current_p) if use_pct_logic and current_p else 0
                        if rem < min_waste or (rem == min_waste and score > best_score):
                            min_waste, best_p, best_score = rem, current_p, score
                backtrack(available_len, [])
                return best_p, min_waste

            final_results = []
            all_raw = []
            for l, q in st.session_state.inventory.items():
                all_raw.extend([l] * q)
            all_raw.sort(reverse=True)

            for r_len in all_raw:
                p, waste = find_best_pattern(r_len - trim_total)
                total_ra_mm += r_len
                total_nytta_mm += sum(p)
                for bit in p:
                    count_tracker[bit] += 1
                    total_cut_pieces += 1
                if use_extra:
                    while waste >= (extra_len + kerf):
                        p.append(extra_len)
                        waste -= (extra_len + kerf)
                        extra_tracker += 1
                        total_nytta_mm += extra_len
                final_results.append((r_len, tuple(sorted(p)), waste))

            # --- DIN KODSNUTT: RESULTAT PROJICERING ---
            st.divider()
            st.header("📊 Resultat Optimering")
            spill_procent = (1 - (total_nytta_mm / total_ra_mm)) * 100 if total_ra_mm > 0 else 0
            c_s1, c_s2, c_s3, c_s4 = st.columns(4)
            c_s1.metric("Total råvara", f"{total_ra_mm/1000:.1f} m")
            c_s2.metric("Utfall", f"{total_nytta_mm/1000:.1f} m")
            c_s3.metric("Spill", f"{spill_procent:.2f} %")
            c_s4.metric("Extra bitar", f"{extra_tracker} st")

            # --- DETALJERAD LISTA ---
            summary = Counter(final_results)
            st.subheader("🪵 Kapinstruktioner")
            for (r_len, p_tuple, w), count in summary.items():
                with st.expander(f"📦 {count} st á {r_len} mm"):
                    st.write(f"Mönster: **{' + '.join(map(str, p_tuple))}**")
                    st.write(f"Spill: {int(w)} mm")

with tab2:
    st.title("💰 Priskalkyl")
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

