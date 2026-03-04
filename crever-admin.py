import streamlit as st
import pandas as pd
import requests
import base64
import gspread
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

# Inizializzazione Session State per stabilità CPU
if 'df' not in st.session_state:
    df, ws = load_data()
    st.session_state.df = df
    st.session_state.ws = ws

st.set_page_config(page_title="Math Archive Pro", layout="wide")
tab1, tab2 = st.tabs(["➕ Inserimento", "🔍 Archivio"])

# --- TAB 1: INSERIMENTO ---
with tab1:
    st.header("Nuovo Esercizio")
    df_m = st.session_state.df

    # 1. DISCIPLINA
    all_disc = sorted(df_m['DISCIPLINA'].unique().tolist()) if not df_m.empty else ["Matematica", "Fisica"]
    disciplina = st.selectbox("Disciplina", all_disc)
        
    # --- LOGICA A CASCATA (FUORI DAL FORM) ---
    col1, col2 = st.columns(2)
    
    with col1:
        # 2. ARGOMENTO (Filtrato per Disciplina)
        filtered_args = sorted(df_m[df_m['DISCIPLINA'] == disciplina]['ARGOMENTO'].unique().tolist())
        arg_sel = st.selectbox("Seleziona Argomento", ["+ NUOVO ARGOMENTO"] + filtered_args)
        
        if arg_sel == "+ NUOVO ARGOMENTO":
            arg_final = st.text_input("Digita nome nuovo Argomento", key="new_arg_input")
        else:
            arg_final = arg_sel

    with col2:
        # 3. SUBARGOMENTO (Filtrato per Argomento)
        if arg_sel != "+ NUOVO ARGOMENTO":
            filtered_subs = sorted(df_m[df_m['ARGOMENTO'] == arg_sel]['SUBARGOMENTO'].unique().tolist())
            sub_sel = st.selectbox("Seleziona Sub-argomento", ["+ NUOVO SUB-ARGOMENTO"] + filtered_subs)
        else:
            # Se l'argomento è nuovo, anche il subargomento deve essere nuovo
            sub_sel = "+ NUOVO SUB-ARGOMENTO"

        if sub_sel == "+ NUOVO SUB-ARGOMENTO":
            sub_final = st.text_input("Digita nome nuovo Sub-argomento", key="new_sub_input")
        else:
            sub_final = sub_sel

    # --- FORM PER DATI STATICI E INVIO ---
    with st.form("insert_form", clear_on_submit=True):
        c3, c4, c5 = st.columns(3)
        with c3:
            tipo_ui = st.selectbox("Tipo", ["A - Aperto", "C - Chiuso"])
            comando = st.text_input("Comando")
        with c4:
            livello = st.selectbox("Livello", [1, 2, 3, 4, 5])
            soluzione = st.text_input("Soluzione (LaTeX)")
        with c5:
            img_file = st.file_uploader("Immagine", type=['png', 'jpg'])

        esercizio = st.text_area("Testo Esercizio (LaTeX)")

        submit = st.form_submit_button("SALVA ESERCIZIO")

    # --- LOGICA DI SALVATAGGIO ---
    if submit:
        if not esercizio or not arg_final or not sub_final:
            st.error("⚠️ Errore: Assicurati di aver inserito Argomento, Sub-argomento e Testo!")
        else:
            with st.spinner("Registrazione in corso..."):
                # Caricamento immagine (ImgBB)
                img_url = ""
                if img_file:
                    try:
                        api_key = st.secrets["IMGBB_API_KEY"]
                        img_b64 = base64.b64encode(img_file.getvalue()).decode('utf-8')
                        res = requests.post("https://api.imgbb.com/1/upload", data={"key": api_key, "image": img_b64})
                        img_url = res.json()["data"]["url"]
                    except:
                        st.warning("Caricamento immagine fallito, procedo senza.")
                
                # Calcolo ID e preparazione riga
                new_id = int(df_m['ID'].max()) + 1 if not df_m.empty else 0
                img_cell = f'=IMAGE("{img_url}")' if img_url else ""
                
                # Mapping colonne: ID, TIPO, DISCIPLINA, ARGOMENTO, SUBARGOMENTO, COMANDO, ESERCIZIO, IMMAGINE, LIVELLO, SOLUZIONE
                riga = [new_id, tipo_ui[0], disciplina, arg_final, sub_final, comando, esercizio, img_cell, livello, soluzione]
                
                # Scrittura su Google Sheets
                st.session_state.ws.append_row(riga, value_input_option='USER_ENTERED')
                
                st.success(f"✅ Esercizio salvato con ID {new_id}!")
                st.cache_data.clear() # Fondamentale per resettare le liste al prossimo avvio
                st.rerun()

# --- TAB 2: ARCHIVIO (Paginazione Anti-Lentezza) ---
with tab2:
    df_view = st.session_state.df
    
    # Filtri Dashboard
    f1, f2, f3 = st.columns([2,1,1])
    with f1: s_search = st.text_input("Cerca nel testo LaTeX:")
    with f2: s_arg = st.selectbox("Filtra per Argomento", ["Tutti"] + sorted(df_view['ARGOMENTO'].unique().tolist()))
    with f3: s_id = st.number_input("Cerca ID", min_value=0, step=1)

    # Logica Filtro
    if s_search: df_view = df_view[df_view['ESERCIZIO'].str.contains(s_search, case=False, na=False)]
    if s_arg != "Tutti": df_view = df_view[df_view['ARGOMENTO'] == s_arg]
    if s_id > 0: df_view = df_view[df_view['ID'] == s_id]

    # PAGINAZIONE (Fondamentale per la CPU)
    items_per_page = 20
    total_items = len(df_view)
    num_pages = (total_items // items_per_page) + 1
    
    c_pag1, c_pag2 = st.columns([1, 4])
    with c_pag1:
        page = st.number_input("Pagina", min_value=1, max_value=num_pages, step=1)
    
    start = (page - 1) * items_per_page
    end = start + items_per_page
    
    st.write(f"Visualizzazione record {start} - {min(end, total_items)} di {total_items}")

    for _, r in df_view.iloc[start:end].iterrows():
        with st.expander(f"ID {r['ID']} | {r['ARGOMENTO']} | {str(r['ESERCIZIO'])[:60]}..."):
            col_l, col_r = st.columns([1, 2])
            
            with col_l:
                # Caricamento immagine solo se checkbox attivo
                img_url = r['IMMAGINE'].split('"')[1] if 'http' in str(r['IMMAGINE']) else None
                if img_url:
                    if st.checkbox("👁️ Immagine", key=f"v_{r['ID']}"):
                        st.image(img_url, use_container_width=True)
                else: st.info("No img")
            
            with col_r:
                st.latex(r['ESERCIZIO'])
                st.caption(f"Comando: {r['COMANDO']} | Livello: {r['LIVELLO']}")
                if r['SOLUZIONE']: st.success(f"Soluzione: {r['SOLUZIONE']}")
                
                # MODIFICA
                with st.popover("📝 Modifica rapida"):
                    new_ese = st.text_area("Testo", value=r['ESERCIZIO'], key=f"te_{r['ID']}")
                    new_sol = st.text_input("Soluzione", value=r['SOLUZIONE'], key=f"ts_{r['ID']}")
                    if st.button("Aggiorna", key=f"bu_{r['ID']}"):
                        cell = st.session_state.ws.find(str(int(r['ID'])), in_column=1)
                        if cell:
                            st.session_state.ws.update_cell(cell.row, 7, new_ese)
                            st.session_state.ws.update_cell(cell.row, 10, new_sol)
                            st.cache_data.clear()
                            st.rerun()