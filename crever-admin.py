import streamlit as st
import pandas as pd
import requests
import base64
import gspread
import os
import time
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE E CACHE ---
def get_gspread_client():
    creds_info = st.secrets["connections"]["gsheets"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_data():
    gc = get_gspread_client()
    ws = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"]).get_worksheet(0)
    data = ws.get_all_records(value_render_option='FORMULA')
    df = pd.DataFrame(data).dropna(how="all")
    df.columns = [c.upper().strip() for c in df.columns]
    return df, ws

import os

import os
import requests
import base64

def upload_to_imgbb(uploaded_file):
    if not uploaded_file: return None
    
    api_key = st.secrets["IMGBB_API_KEY"]
    url = "https://api.imgbb.com/1/upload"
    
    # Codifica l'immagine
    img_b64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    
    # Estraiamo il nome senza estensione (es. id_84.png -> id_84)
    # ImgBB aggiungerà l'estensione corretta automaticamente
    file_name_raw = os.path.splitext(uploaded_file.name)[0]
    
    payload = {
        "key": api_key,
        "image": img_b64,
        "name": file_name_raw  # Carica con il nome originale nella root
    }
    
    try:
        response = requests.post(url, data=payload)
        json_res = response.json()
        
        if json_res["status"] == 200:
            # Restituisce l'URL diretto dell'immagine
            return json_res["data"]["url"]
        else:
            st.error(f"Errore ImgBB: {json_res['error']['message']}")
            return None
    except Exception as e:
        st.error(f"Errore di connessione durante l'upload: {e}")
        return None

if 'df' not in st.session_state:
    df, ws = load_data()
    st.session_state.df = df
    st.session_state.ws = ws

st.set_page_config(page_title="Math Archive Pro", layout="wide")
tab1, tab2, tab3 = st.tabs(["➕ Inserimento", "🔍 Archivio", "📊 Statistiche"])

# --- TAB 1: INSERIMENTO ---
with tab1:
    st.header("Nuovo Esercizio")
    df_m = st.session_state.df

    # --- LOGICA A CASCATA (FUORI DAL FORM PER REATTIVITÀ) ---
    c1, c2 = st.columns(2)
    with c1:
        # 1. DISCIPLINA
        all_disc = sorted(df_m['DISCIPLINA'].unique().tolist()) if not df_m.empty else ["Matematica", "Fisica"]
        disciplina = st.selectbox("Disciplina", all_disc)
        filtered_args = sorted(df_m[df_m['DISCIPLINA'] == disciplina]['ARGOMENTO'].unique().tolist())
    with c2:
        # Calcolo dell'ID per il prossimo inserimento
        next_id_display = int(st.session_state.df['ID'].max() + 1) if not st.session_state.df.empty else 0
        st.text_input("ID Prossimo Esercizio", value=next_id_display, disabled=True)
        
    # --- LOGICA A CASCATA (FUORI DAL FORM PER REATTIVITÀ) ---
    c3, c4 = st.columns(2)
    with c3:
        # 2. ARGOMENTO (Filtrato)
        arg_sel = st.selectbox("Seleziona Argomento", ["+ NUOVO ARGOMENTO"] + filtered_args)
        arg_final = st.text_input("Digita nome nuovo Argomento") if arg_sel == "+ NUOVO ARGOMENTO" else arg_sel
    with c4:
        # 4. SUBARGOMENTO (Filtrato)
        if arg_sel != "+ NUOVO ARGOMENTO":
            filtered_subs = sorted(df_m[df_m['ARGOMENTO'] == arg_sel]['SUBARGOMENTO'].unique().tolist())
            sub_sel = st.selectbox("Seleziona Sub-argomento", ["+ NUOVO SUB-ARGOMENTO"] + filtered_subs)
        else:
            sub_sel = "+ NUOVO SUB-ARGOMENTO"
        
        sub_final = st.text_input("Digita nome nuovo Sub-argomento") if sub_sel == "+ NUOVO SUB-ARGOMENTO" else sub_sel

    # --- FORM PER IL RESTO DEI CAMPI ---
    with st.form("insert_form", clear_on_submit=True):
        c5, c6 = st.columns(2)
        with c5:
            tipo_ui = st.selectbox("Tipo", ["A - Aperto", "C - Chiuso"])
            comando = st.text_input("Comando")
        with c6:
            livello = st.selectbox("Livello", [1, 2, 3, 4, 5])
            soluzione = st.text_input("Soluzione (LaTeX)")

        esercizio = st.text_area("Testo Esercizio (LaTeX)")
        img_file = st.file_uploader("Immagine", type=['png', 'jpg'])

        submit = st.form_submit_button("SALVA ESERCIZIO")

    if submit:
        if not esercizio or not arg_final or not sub_final:
            st.error("⚠️ Errore: Assicurati di aver inserito Argomento, Sub-argomento e Testo!")
        else:
            with st.spinner("Registrazione in corso e sincronizzazione database..."):
                img_url = upload_to_imgbb(img_file) # La funzione ora gestisce nome e album
                if img_file:
                    try:
                        api_key = st.secrets["IMGBB_API_KEY"]
                        img_b64 = base64.b64encode(img_file.getvalue()).decode('utf-8')
                        res = requests.post("https://api.imgbb.com/1/upload", data={"key": api_key, "image": img_b64})
                        img_url = res.json()["data"]["url"]
                    except: st.warning("Errore upload immagine.")

                new_id = int(df_m['ID'].max()) + 1 if not df_m.empty else 0
                img_cell = f'=IMAGE("{img_url}")' if img_url else ""
                
                # Mapping preciso colonne Sheet: ID, TIPO, DISCIPLINA, ARGOMENTO, SUBARGOMENTO, COMANDO, ESERCIZIO, IMMAGINE, LIVELLO, SOLUZIONE
                riga = [new_id, tipo_ui[0], disciplina, arg_final, sub_final, comando, esercizio, img_cell, livello, soluzione]
                
                # 1. Scrittura su Google Sheets
                st.session_state.ws.append_row(riga, value_input_option='USER_ENTERED')
                
                # 2. PULIZIA CACHE E AGGIORNAMENTO SESSION STATE
                st.cache_data.clear() # Svuota la cache della funzione load_data()
                
                # Ricarichiamo i dati aggiornati per riflettere i nuovi Argomenti/Subargomenti
                new_df, new_ws = load_data()
                st.session_state.df = new_df
                st.session_state.ws = new_ws
                
                st.success(f"✅ Esercizio salvato con ID {new_id}!")
                # 2. Piccolo ritardo (es. 2 secondi)
                time.sleep(2)                
                
                # 3. RE-RUN PER AGGIORNARE I WIDGET
                st.rerun()


# --- TAB 2: ARCHIVIO ---
with tab2:
    st.header("Ricerca e Gestione Esercizi")
    
    # Usiamo i dati in session_state per la massima velocità
    df_v = st.session_state.df.copy()

    # --- FILTRI IN COLONNA (ORDINE RICHIESTO) ---
    f_col = st.columns(5)
    
    with f_col[0]:
        # 1. DISCIPLINA
        list_disc = ["Tutti"] + sorted(df_v['DISCIPLINA'].unique().tolist())
        s_disc = st.selectbox("Disciplina", list_disc, key="filter_disc")
        if s_disc != "Tutti":
            df_v = df_v[df_v['DISCIPLINA'] == s_disc]

    with f_col[1]:
        # 2. TIPO
        list_tipo = ["Tutti"] + sorted(df_v['TIPO'].unique().tolist())
        s_tipo = st.selectbox("Tipo", list_tipo, key="filter_tipo")
        if s_tipo != "Tutti":
            df_v = df_v[df_v['TIPO'] == s_tipo]

    with f_col[2]:
        # 3. ARGOMENTO (Filtrato dai precedenti)
        list_arg = ["Tutti"] + sorted(df_v['ARGOMENTO'].unique().tolist())
        s_arg = st.selectbox("Argomento", list_arg, key="filter_arg")
        if s_arg != "Tutti":
            df_v = df_v[df_v['ARGOMENTO'] == s_arg]

    with f_col[3]:
        # 4. SUBARGOMENTO (Filtrato dai precedenti)
        list_sub = ["Tutti"] + sorted(df_v['SUBARGOMENTO'].unique().tolist())
        s_sub = st.selectbox("Subargomento", list_sub, key="filter_sub")
        if s_sub != "Tutti":
            df_v = df_v[df_v['SUBARGOMENTO'] == s_sub]

    with f_col[4]:
        # 5. LIVELLO
        # Assicuriamoci che LIVELLO sia trattato come stringa o numero pulito per il filtro
        list_liv = ["Tutti"] + sorted([str(x) for x in df_v['LIVELLO'].unique() if pd.notna(x)])
        s_liv = st.selectbox("Livello", list_liv, key="filter_liv")
        if s_liv != "Tutti":
            df_v = df_v[df_v['LIVELLO'].astype(str) == s_liv]

    # Ricerca testuale libera
    s_search = st.text_input("🔍 Cerca parole chiave nel testo LaTeX:", key="filter_search")
    if s_search:
        df_v = df_v[df_v['ESERCIZIO'].str.contains(s_search, case=False, na=False)]

    st.divider()

    # --- VISUALIZZAZIONE E PAGINAZIONE ---
    total_results = len(df_v)
    st.write(f"Risultati trovati: **{total_results}**")

    if total_results > 0:
        items_per_page = 20
        num_pages = (total_results // items_per_page) + (1 if total_results % items_per_page > 0 else 0)
        
        c_pag1, c_pag2 = st.columns([1, 4])
        with c_pag1:
            page = st.number_input("Pagina", min_value=1, max_value=num_pages, step=1, key="archive_page")
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        # Rendering degli expander per i risultati filtrati
        for _, r in df_v.iloc[start_idx:end_idx].iterrows():
            # Intestazione con ID, Argomento e Subargomento
            with st.expander(f"(ID: {r['ID']}) | {r['ARGOMENTO']} ➔ {r['SUBARGOMENTO']}"):
                
                # Layout a due colonne bilanciate
                col_info, col_main = st.columns([1, 2])
                
                with col_info:
                    # Metadati con stile omogeneo (senza icone eccessive o colori forti)
                    st.markdown(f"**Disciplina:** {r['DISCIPLINA']}")
                    st.markdown(f"**Tipo:** {r['TIPO']}")
                    st.markdown(f"**Livello:** {r['LIVELLO']}")
                    st.markdown(f"**Comando:**")
                    st.write(r['COMANDO'])
                    
                    # Gestione Immagine sotto i dati tecnici
                    img_raw = str(r['IMMAGINE'])
                    if "http" in img_raw:
                        img_url = img_raw.split('"')[1] if '"' in img_raw else img_raw
                        st.image(img_url, width='stretch')
                    else:
                        st.caption("Nessuna immagine associata")

                with col_main:
                    # Sezione Testo Esercizio
                    st.markdown("**Testo dell'Esercizio:**")
                    # st.latex(r['ESERCIZIO'])
                    st.write(r['ESERCIZIO'])
                    
                    st.markdown("---") # Linea di separazione sottile
                    
                    # Sezione Soluzione
                    st.markdown("**Soluzione:**")
                    # st.latex(r['SOLUZIONE'])
                    st.write(r['SOLUZIONE'])


                    
                    # --- POPOVER DI MODIFICA COMPLETA ---
                    with st.popover("📝 Modifica Integrale", width='stretch'):
                        st.markdown("### 🛠️ Editor Esercizio")
                        st.subheader(f"ID: {r['ID']}")

                        # Tre colonne invece di due per distribuire il carico orizzontalmente
                        ed1, ed2, ed3 = st.columns(3)
                        with ed1:
                            new_disc = st.selectbox("Disciplina", all_disc, index=all_disc.index(r['DISCIPLINA']), key=f"ed_d_{r['ID']}")
                            new_tipo = st.selectbox("Tipo", ["A", "C"], index=0 if r['TIPO']=="A" else 1, key=f"ed_t_{r['ID']}")
                        with ed2:
                            new_arg = st.text_input("Argomento", value=r['ARGOMENTO'], key=f"ed_a_{r['ID']}")
                            new_sub = st.text_input("Subargomento", value=r['SUBARGOMENTO'], key=f"ed_s_{r['ID']}")
                        with ed3:
                            new_liv = st.selectbox("Livello", [1,2,3,4,5], index=int(r['LIVELLO'])-1, key=f"ed_l_{r['ID']}")
                            new_sol = st.text_input("Soluzione (LaTeX)", value=r['SOLUZIONE'], key=f"ed_sl_{r['ID']}")

                        new_com = st.text_input("Comando", value=r['COMANDO'], key=f"ed_c_{r['ID']}")
                        new_ese = st.text_area("Testo (LaTeX)", value=r['ESERCIZIO'], key=f"ed_e_{r['ID']}", height=200)
                        new_img_file = st.file_uploader("Cambia Immagine", type=['png', 'jpg'], key=f"ed_i_{r['ID']}")

                        if st.button("AGGIORNA TUTTO", key=f"save_all_{r['ID']}", width='stretch'):
                            with st.spinner("Sincronizzazione modifiche in corso..."):
                                # 1. Gestione immagine (mantiene vecchia o carica nuova)
                                final_img_cell = r['IMMAGINE']
                                if new_img_file:
                                    new_url = upload_to_imgbb(new_img_file)
                                    if new_url:
                                        final_img_cell = f'=IMAGE("{new_url}")'

                                # 2. Invio dati a Google Sheets (Batch Update per velocità)
                                cell = st.session_state.ws.find(str(int(r['ID'])), in_column=1)
                                if cell:
                                    row_idx = cell.row
                                    # Assicurati che l'ordine delle colonne (B, C, D...) corrisponda al tuo Sheet
                                    updates = [
                                        {'range': f'B{row_idx}', 'values': [[new_tipo]]},
                                        {'range': f'C{row_idx}', 'values': [[new_disc]]},
                                        {'range': f'D{row_idx}', 'values': [[new_arg]]},
                                        {'range': f'E{row_idx}', 'values': [[new_sub]]},
                                        {'range': f'F{row_idx}', 'values': [[new_com]]},
                                        {'range': f'G{row_idx}', 'values': [[new_ese]]},
                                        {'range': f'H{row_idx}', 'values': [[final_img_cell]]},
                                        {'range': f'I{row_idx}', 'values': [[new_liv]]},
                                        {'range': f'J{row_idx}', 'values': [[new_sol]]},
                                    ]
                                    st.session_state.ws.batch_update(updates, value_input_option='USER_ENTERED')

                                    # --- 3. IL CUORE DEL REFRESH ---
                                    st.cache_data.clear()  # Svuota la cache di load_data()
                                    
                                    # Ricarica i dati freschi da Google Sheets nel Session State
                                    new_df, new_ws = load_data()
                                    st.session_state.df = new_df
                                    st.session_state.ws = new_ws
                                    
                                    st.success(f"✅ Record ID {r['ID']} aggiornato e database sincronizzato!")
                                    # 2. Piccolo ritardo (es. 2 secondi)
                                    time.sleep(2)

                                    # Riavvia l'app per mostrare i nuovi dati nei filtri e negli expander
                                    st.rerun()

# --- TAB 3: STATISTICHE (Versione High-Readability) ---
with tab3:
    df_tree = st.session_state.df.copy()

    if not df_tree.empty:
        # 1. TOTALONE IN CIMA
        st.subheader("Riepilogo Generale")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Esercizi Totali", len(df_tree), delta=None)
        with c2:
            num_arg = len(df_tree['ARGOMENTO'].unique())
            st.metric("Argomenti Coperti", num_arg)
        with c3:
            avg_diff = pd.to_numeric(df_tree['LIVELLO'], errors='coerce').mean()
            st.metric("Difficoltà Media", f"{avg_diff:.1f} / 5")

        st.divider()
        st.subheader("Esplora la Struttura")

        # Ordinamento per coerenza visiva
        df_tree = df_tree.sort_values(['DISCIPLINA', 'TIPO', 'ARGOMENTO', 'SUBARGOMENTO'])
        
        # --- ALBERO GERARCHICO ---
        for disc in sorted(df_tree['DISCIPLINA'].unique()):
            df_d = df_tree[df_tree['DISCIPLINA'] == disc]
            
            # LIVELLO 1: DISCIPLINA
            with st.expander(f"📁 **{disc.upper()}** — ({len(df_d)} esercizi)", expanded=False):
                
                # LIVELLO 2: TIPO
                for t in sorted(df_d['TIPO'].unique()):
                    df_t = df_d[df_d['TIPO'] == t]
                    label_t = "Aperto" if t == "A" else "Chiuso"
                    
                    with st.expander(f"📄 **Tipo {t}** ({label_t}) — {len(df_t)} esercizi"):
                        
                        # LIVELLO 3: ARGOMENTO
                        for arg in sorted(df_t['ARGOMENTO'].unique()):
                            df_a = df_t[df_t['ARGOMENTO'] == arg]
                            
                            with st.expander(f"🔹 {arg} ({len(df_a)})"):
                                
                                # LIVELLO 4: SUBARGOMENTO (Punto finale)
                                for sub in sorted(df_a['SUBARGOMENTO'].unique()):
                                    df_s = df_a[df_a['SUBARGOMENTO'] == sub]
                                    
                                    # Layout riga finale: Subargomento a sinistra, Badge a destra
                                    col_sub, col_lev = st.columns([2, 3])
                                    
                                    with col_sub:
                                        st.markdown(f"**{sub}** ({len(df_s)})")
                                    
                                    with col_lev:
                                        # Creiamo dei badge neutri per i livelli
                                        lv_counts = df_s['LIVELLO'].value_counts()
                                        badge_cols = st.columns(5) # Spazio per i 5 livelli
                                        
                                        for i in range(1, 6):
                                            # Cerchiamo il conteggio (gestendo sia stringhe che int)
                                            count = lv_counts.get(str(i), 0) or lv_counts.get(i, 0)
                                            
                                            # Stile Neutro: Grigio chiaro se > 0, quasi bianco se 0
                                            bg_color = "#e0e0e0" if count > 0 else "#f9f9f9"
                                            text_color = "#000000" if count > 0 else "#cccccc"
                                            font_weight = "bold" if count > 0 else "normal"
                                            border_style = "1px solid #ccc" if count > 0 else "1px dashed #eee"
                                            
                                            badge_cols[i-1].markdown(
                                                f"""<div style="
                                                    background-color:{bg_color}; 
                                                    color:{text_color}; 
                                                    padding:2px 4px; 
                                                    border-radius:4px; 
                                                    text-align:center;
                                                    font-size:14px;
                                                    font-weight:{font_weight};
                                                    border:{border_style};
                                                ">Liv.{i}--> {count}</div>""", 
                                                unsafe_allow_html=True
                                            )
                                    st.markdown("<div style='margin-bottom: -10px; border-bottom: 1px solid #f0f2f6;'></div>", unsafe_allow_html=True)
        
        st.divider()
        st.subheader("💡 Suggerimenti per il tuo Archivio")
        c_cons1, c_cons2 = st.columns(2)

        with c_cons1:
            # Trova i Subargomenti "Deboli"
            weak_subs = df_tree.groupby(['ARGOMENTO', 'SUBARGOMENTO']).size()
            weak_subs = weak_subs[weak_subs == 1].reset_index(name='count')
            
            st.markdown("**🌱 Subargomenti da potenziare (solo 1 esercizio):**")
            if not weak_subs.empty:
                for _, row in weak_subs.head(5).iterrows(): # Mostriamo i primi 5
                    st.write(f"- {row['ARGOMENTO']} > {row['SUBARGOMENTO']}")
            else:
                st.success("Ottimo! Ogni subargomento ha almeno 2 esercizi.")

        with c_cons2:
            # Analisi Copertura Immagini
            st.markdown("**🖼️ Copertura Visiva per Disciplina:**")
            img_analysis = df_tree.copy()
            img_analysis['has_img'] = img_analysis['IMMAGINE'].astype(str).str.contains("http")
            img_stats = img_analysis.groupby('DISCIPLINA')['has_img'].mean() * 100
            
            for disc, perc in img_stats.items():
                st.write(f"- {disc}: **{perc:.0f}%** con immagini")
    else:
        st.info("Nessun dato presente nel database.")