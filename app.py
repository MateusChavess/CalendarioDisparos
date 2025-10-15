import streamlit as st

st.set_page_config(page_title="Login • Calendário de Disparos", layout="wide")

# ======= CONFIG LOGIN =======
VALID_USER = "Admin"
VALID_PASS = "Admin123"  # troque em produção

# ======= ESTILO: esconde dicas e toolbar =======
st.markdown("""
<style>
  [data-testid="InputInstructions"] { display: none !important; }
  /* Esconde o menu do Streamlit e o rodapé */
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}
  header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ======= SE JÁ LOGADO, VAI PRA PÁGINA PROTEGIDA =======
if st.session_state.get("logged_in", False):
    try:
        st.switch_page("pages/main.py")
    except Exception:
        # fallback para raiz caso o multipage não esteja habilitado corretamente
        st.markdown("<meta http-equiv='refresh' content='0; url=/pages/main' />", unsafe_allow_html=True)
    st.stop()

# ======= LOGIN UI =======
st.title("🔐 Acesso • Calendário de Disparos")

c1, c2, c3 = st.columns([1, 1.2, 1])
with c2:
    with st.form("login_form", clear_on_submit=False):
        user = st.text_input("Usuário", value="", placeholder="Digite seu usuário")
        pwd  = st.text_input("Senha", value="", placeholder="Digite sua senha", type="password")
        ok   = st.form_submit_button("Entrar", use_container_width=True)

        if ok:
            if user == VALID_USER and pwd == VALID_PASS:
                # Marca sessão como logada e salva o nome
                st.session_state.logged_in = True
                st.session_state.user_name = user
                # opcional: token p/ conferir em páginas protegidas
                st.session_state.auth_token = "ok"
                try:
                    st.switch_page("pages/main.py")
                except Exception:
                    st.markdown("<meta http-equiv='refresh' content='0; url=/pages/main' />", unsafe_allow_html=True)
                st.stop()
            else:
                st.error("Usuário ou senha inválidos.")
