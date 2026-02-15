import streamlit as st
import pandas as pd
import re

# Sätt sidans titel och layout
st.set_page_config(page_title="Kapmaskinen", layout="wide")
st.title("🛠️ KAPMASKIN v1.0")

# --- INSTÄLLNINGAR I SIDOPANELEN ---
with st.sidebar:
    st.header("Inställningar")
    raw_len = st.number_input("Råmaterialets längd (mm)", value=6000)
    kerf = st.number_input("Sågbladets bredd (mm)", value=4)
    target_waste = st.slider("Önskat max-spill per planka (%)", 0, 100, 10)

# --- FILUPPLADDNING ---
file = st.file_uploader("Ladda upp din Excel-fil", type=["xlsx", "csv"])

if file:
    # Läs in filen (stöder både Excel och CSV)
    df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file)
    
    st.write("### 1. Välj paket att optimera")
    
    # Letar efter en kolumn för urval. Vi använder första kolumnen om 'Paket' inte hittas.
    col_name = 'Paket' if 'Paket' in df.columns else df.columns[0]
    
    paket_lista = df[col_name].astype(str).unique().tolist()
    valda_paket = st.multiselect("Välj paket ur listan:", options=paket_lista)
    
    if valda_paket:
        # Filtrera fram de valda paketen
        valda_df = df[df[col_name].astype(str).isin(valda_paket)]
        
        # Identifiera längder (t.ex. 3.6, 4.2) och räkna antal bitar
        behov = []
        for col in df.columns:
            col_clean = str(col).replace(',', '.')
            # Letar efter siffror/decimaler i kolumnnamnet
            match = re.findall(r'\d+\.\d+|\d+', col_clean)
            
            if match:
                val = float(match[0])
                # Omvandla meter till mm (t.ex. 4.2 -> 4200)
                mm_val = int(val * 1000) if val < 100 else int(val)
                
                # Räkna ihop totalt antal bitar i de valda raderna
                antal = int(pd.to_numeric(valda_df[col], errors='coerce').sum() or 0)
                for _ in range(antal):
                    behov.append(mm_val)

        if behov:
            st.success(f"✅ {len(behov)} bitar redo för optimering.")
            
            if st.button("BERÄKNA KAPSCHEMA"):
                # Algoritm: First Fit Decreasing
                behov.sort(reverse=True)
                plankor = []
                
                for bit in behov:
                    passade = False
                    for p in plankor:
                        if sum(p) + (len(p) * kerf) + bit <= raw_len:
                            p.append(bit)
                            passade = True
                            break
                    if not passade:
                        plankor.append([bit])
                
                # --- RESULTAT ---
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("Antal 6m-längder", f"{len(plankor)} st")
                
                anvand_mm = sum(behov)
                total_mm = len(plankor) * raw_len
                snitt_forlust = sum(len(p)-1 for p in plankor) * kerf
                # Verkligt spill beräknat på totalt material minus använd trä och sågsnitt
                spill_pct = (1 - (anvand_mm / (total_mm - snitt_forlust))) * 100
                c2.metric("Total spillprocent", f"{spill_pct:.1f} %")
                c3.metric("Bitar totalt", len(behov))

                st.write("### Kapningsplan")
                for i, p in enumerate(plankor):
                    p_spill = (1 - (sum(p) / raw_len)) * 100
                    ikon = "✅" if p_spill <= target_waste else "⚠️"
                    with st.expander(f"{ikon} Planka {i+1} (Spill: {p_spill:.1f}%)"):
                        st.write(f"Kapa dessa längder: **{' + '.join(map(str, p))} mm**")
                        st.progress(min(sum(p)/raw_len, 1.0))
        else:
            st.warning("Inga bitar hittades i de valda paketen.")
    else:
        st.info("Välj ett eller flera paket i listan ovanför för att börja.")
