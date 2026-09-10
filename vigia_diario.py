import os
import sys
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import urllib3
import ssl
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try: ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError: pass

MEU_CODIGO_ESCOLA = "COLEGIOM2"
MEU_LOGIN = "Marcelo3892" 
MINHA_SENHA = os.environ.get("SENHA_ACTIVESOFT", "SuaSenhaLocalAqui") 
ETAPA_ATUAL = "2ª Etapa"

MAPA_TURMAS = {
    "8º ANO A": "EFII-8A-FD", "8º A": "EFII-8A-FD", "8 ANO A": "EFII-8A-FD", "8A": "EFII-8A-FD",
    "8º ANO B": "EFII-8B-FD", "8º B": "EFII-8B-FD", "8 ANO B": "EFII-8B-FD", "8B": "EFII-8B-FD",
    "9º ANO A": "EFII-9A-FD", "9º A": "EFII-9A-FD", "9 ANO A": "EFII-9A-FD", "9A": "EFII-9A-FD",
    "9º ANO B": "EFII-9B-FD", "9º B": "EFII-9B-FD", "9 ANO B": "EFII-9B-FD", "9B": "EFII-9B-FD",
    "2ª SÉRIE": "EM-2SEM-FD", "2ª SÉRIE EM": "EM-2SEM-FD", "2 SÉRIE": "EM-2SEM-FD", "2EM": "EM-2SEM-FD",
    "3ª SÉRIE": "EM-3SEM-FD", "3ª SÉRIE EM": "EM-3SEM-FD", "3 SÉRIE": "EM-3SEM-FD", "3EM": "EM-3SEM-FD",
    "6º ANO A": "6° ANO A", "6º ANO B": "6º ANO B", "6º A": "6° ANO A", "6º B": "6º ANO B", "6A": "6° ANO A", "6B": "6º ANO B",
    "7º ANO A": "7° ANO A", "7º ANO B": "7º ANO B", "7º A": "7° ANO A", "7º B": "7º ANO B", "7A": "7° ANO A", "7B": "7º ANO B",
    "1ª SÉRIE": "1ª SÉRIE", "1ª SÉRIE EM": "1ª SÉRIE", "1EM": "1ª SÉRIE"
}

SPREADSHEET_ID = '1oLo2lYbgqOgyT5Kd02pUAZ0EYWCGqLY0H1rks0aHwX4'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
JS_REACT_SETTER = "let e=arguments[0],v=arguments[1],s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));"

def avisar_telegram(mensagem):
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}, timeout=10)
        except: pass

def conectar_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", SCOPE) 
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

# ================= FUNÇÕES DO DIÁRIO =================
def lancar_ocorrencias(navegador, wait, aula):
    if not str(aula.get('nao_fez', '')).strip(): return
    try:
        texto_ocorrencia = f"Não fez a tarefa: {aula['tarefa_nao_feita']}"
        numeros_alvo = [num.strip() for num in aula['nao_fez'].split(',')]
        
        try: navegador.switch_to.default_content()
        except: pass
        time.sleep(2)
        
        wait.until(EC.element_to_be_clickable((By.ID, "ocorrencias_de_alunos"))).click()
        time.sleep(3)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@href='/gerar_ocorrencias_lote/' or contains(text(), 'Registrar ocorrência')]"))).click()
        time.sleep(3)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Pesquisar']"))).click()
        time.sleep(5) 
        
        nome_plan = aula['turma'].upper().strip()
        num_t = "".join([c for c in nome_plan if c.isdigit()])
        letra_t = "A" if nome_plan.endswith("A") else "B" if nome_plan.endswith("B") else ""

        for num in numeros_alvo:
            linhas = navegador.find_elements(By.XPATH, f"//tr[td[normalize-space(text())='{num}']]")
            for linha in linhas:
                texto_turma = ""
                for td in linha.find_elements(By.TAG_NAME, "td"):
                    if "/" in td.text and ("ANO" in td.text.upper() or "SÉRIE" in td.text.upper() or "SERIE" in td.text.upper()):
                        texto_turma = td.text.upper().strip(); break
                if not texto_turma: texto_turma = linha.text.upper().strip()
                
                if num_t in texto_turma and (letra_t in texto_turma if letra_t else "SÉRIE" in texto_turma or "SERIE" in texto_turma):
                    checkbox = linha.find_element(By.XPATH, ".//input[@type='checkbox']")
                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
                    time.sleep(0.5)
                    if not checkbox.is_selected(): navegador.execute_script("arguments[0].click();", checkbox)
                    break 

        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Próximo')]"))).click()
        time.sleep(3)

        try:
            input_data = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='DD/MM/AAAA']")))
            input_data.click()
            input_data.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, aula['data'], Keys.ESCAPE)
            time.sleep(0.5)
        except: pass

        try:
            input_react = navegador.find_element(By.XPATH, "//input[@aria-autocomplete='list']")
            navegador.execute_script("arguments[0].focus();", input_react)
            input_react.send_keys("Não apresentou para casa")
            time.sleep(1)
            input_react.send_keys(Keys.ENTER)
        except: pass

        try:
            botao_internet = navegador.find_element(By.XPATH, "//button[@label='Exibir esta observação na Internet']")
            navegador.execute_script("arguments[0].click();", botao_internet)
        except: pass

        navegador.find_element(By.XPATH, "//textarea[contains(@class, 'form-control')]").send_keys(texto_ocorrencia)

        botao_executar = navegador.find_element(By.XPATH, "//button[contains(text(), 'Executar')]")
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_executar)
        time.sleep(1)
        navegador.execute_script("arguments[0].click();", botao_executar)
        try: wait.until(EC.alert_is_present()).accept()
        except: pass
        
    except Exception as e:
        raise Exception(f"Erro no preenchimento das ocorrências: {e}")
    finally:
        try: navegador.switch_to.default_content()
        except: pass

def lancar_faltas(navegador, wait, aula, etapa_atual):
    if aula['tipo_lancamento'] != "Pendente_Nova": 
        return 
        
    faltas_str = str(aula.get('faltas', '')).strip()

    try:
        try: navegador.switch_to.default_content()
        except: pass
        time.sleep(2)
        
        try: wait.until(EC.element_to_be_clickable((By.ID, "frequencia_em_lote"))).click()
        except: navegador.get("https://siga02.activesoft.com.br/diarios/frequencia_em_lote/")
        time.sleep(5)
        
        turma_bruta = aula['turma'].upper()
        curso = "FUNDAMENTAL" if "ANO" in turma_bruta else "MÉDIO"
        serie_busca = next((s for s in ["6", "7", "8", "9"] if s in turma_bruta), next((s for s in ["1", "2", "3"] if f"{s} SÉRIE" in turma_bruta or f"{s}ª SÉRIE" in turma_bruta), ""))
        turma_exata = turma_bruta.replace("º", "°")
        
        def preencher_select_blindado(idx, texto):
            navegador.switch_to.default_content()
            inps = navegador.find_elements(By.XPATH, "//input[contains(@id, 'react-select') or @aria-autocomplete='list']")
            if not inps: 
                frames = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
                for f in frames:
                    navegador.switch_to.default_content()
                    try:
                        navegador.switch_to.frame(f)
                        inps = navegador.find_elements(By.XPATH, "//input[contains(@id, 'react-select') or @aria-autocomplete='list']")
                        if inps: break
                    except: pass
            if not inps: raise Exception("Painel de faltas não carregou os campos.")
            if idx >= len(inps): return
            inp = inps[idx]
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
            time.sleep(1)
            try: navegador.execute_script("arguments[0].parentNode.parentNode.click();", inp)
            except: pass
            time.sleep(1)
            navegador.execute_script("arguments[0].focus();", inp)
            try: inp.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, texto); time.sleep(1.5)
            except: navegador.execute_script(JS_REACT_SETTER, inp, texto); time.sleep(2)
            
            opcoes = navegador.find_elements(By.XPATH, f"//div[contains(text(), '{texto}')] | //li[contains(text(), '{texto}')]")
            if opcoes:
                for opcao in opcoes:
                    if texto.upper() == opcao.text.strip().upper():
                        navegador.execute_script("arguments[0].click();", opcao); break
            else:
                navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'ArrowDown'}));", inp)
                time.sleep(0.5)
                navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", inp)
            time.sleep(2.5) 

        preencher_select_blindado(1, curso)        
        preencher_select_blindado(2, serie_busca)       
        preencher_select_blindado(3, turma_exata)  
        preencher_select_blindado(5, etapa_atual)
        
        try:
            inps_data = navegador.find_elements(By.XPATH, "//input[contains(@class, 'Datepicker') or contains(@class, 'DatePicker') or @placeholder='DD/MM/AAAA']")
            for input_dt in inps_data[:2]:
                navegador.execute_script(JS_REACT_SETTER, input_dt, aula['data']); time.sleep(0.5)
        except: pass

        botao_consultar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Consultar']")))
        navegador.execute_script("arguments[0].click();", botao_consultar)
        time.sleep(8) 
        
        def clicar_opcao_tabela(botao_alvo, texto_opcao):
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_alvo)
            time.sleep(0.5)
            try: botao_alvo.click() 
            except: navegador.execute_script("arguments[0].click();", botao_alvo) 
            time.sleep(1) 
            opcoes = navegador.find_elements(By.XPATH, f"//*[normalize-space(text())='{texto_opcao}']")
            for op in opcoes:
                if op.is_displayed():
                    try: op.click(); return
                    except: webdriver.ActionChains(navegador).move_to_element(op).click().perform(); return
            if opcoes: navegador.execute_script("arguments[0].click();", opcoes[-1])

        botao_selecione = wait.until(EC.presence_of_element_located((By.XPATH, "(//button[contains(@class, 'Toggle__ToggleButton') and contains(., 'Selecione')])[1]")))
        clicar_opcao_tabela(botao_selecione, "Presente")
        time.sleep(3) 
            
        if faltas_str:
            for num in [n.strip() for n in faltas_str.split(',')]:
                linha = navegador.find_element(By.XPATH, f"(//tbody/tr)[{int(num) + 1}]")
                botao_status = linha.find_element(By.XPATH, ".//button[contains(@class, 'Toggle__ToggleButton')]")
                clicar_opcao_tabela(botao_status, "Falta")
                time.sleep(1)
        
        botao_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Salvar')]")))
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", botao_salvar)
        time.sleep(2)
        
        try:
            botao_sim = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'swal2-confirm') and contains(text(), 'Sim')]")))
            navegador.execute_script("arguments[0].click();", botao_sim)
            time.sleep(3)
        except: pass
            
    except Exception as e: 
        raise Exception(f"Erro na digitação de faltas: {e}")

# ================= MÓDULO DE NOTAS =================
def lancar_notas(navegador, wait, nota_info):
    input_escondido = None
    for tentativa in range(12):
        try:
            navegador.switch_to.default_content()
            input_escondido = navegador.find_element(By.XPATH, "//input[contains(@id, 'react-select')]")
            if input_escondido: break
        except: pass
        frames = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
        for f in frames:
            navegador.switch_to.default_content()
            try: navegador.switch_to.frame(f); input_escondido = navegador.find_element(By.XPATH, "//input[contains(@id, 'react-select')]")
            except: pass
            if input_escondido: break
        if input_escondido: break
        time.sleep(1.5)
        
    if not input_escondido: raise Exception("Campo de Etapa sumiu.")

    navegador.execute_script("arguments[0].parentNode.parentNode.click();", input_escondido)
    time.sleep(1)
    navegador.execute_script("arguments[0].focus();", input_escondido)
    input_escondido.send_keys(nota_info['etapa'])
    time.sleep(1.5) 
    
    opcoes = navegador.find_elements(By.XPATH, f"//div[text()='{nota_info['etapa']}']")
    if opcoes: navegador.execute_script("arguments[0].click();", opcoes[-1])
    else:
        navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'ArrowDown'}));", input_escondido)
        time.sleep(0.5)
        navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", input_escondido)
    time.sleep(1.5)
    
    wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Consultar')]"))).click()
    time.sleep(3) 

    wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Inserir avaliação')] | //*[name()='svg' and contains(@class, 'FaseNota')]"))).click()
    time.sleep(1.5)
    wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Nova avaliação')]"))).click()
    time.sleep(1.5) 
    
    navegador.execute_script(JS_REACT_SETTER, wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Input-sg8yoa-0') and not(@readonly)]"))), nota_info['nome_prova'])
    time.sleep(0.5)
    navegador.execute_script(JS_REACT_SETTER, wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Datepicker')]"))), nota_info['data_prova'])
    time.sleep(0.5)
    navegador.execute_script(JS_REACT_SETTER, wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'InputDecimal')]"))), nota_info['valor_prova'])
    time.sleep(0.5)
    
    wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Salvar')]"))).click()
    navegador.execute_script("arguments[0].click();", WebDriverWait(navegador, 10).until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'swal2-confirm') or text()='Fechar']"))))
    time.sleep(3)
    
    cabecalhos_provas = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'TextClick')]")))
    indice_coluna_alvo = next((i for i, cab in enumerate(cabecalhos_provas) if cab.text.strip() == nota_info['nome_prova']), len(cabecalhos_provas) - 1)
    
    for num_aluno, nota in nota_info['notas_alunos'].items():
        try:
            linha_aluno = wait.until(EC.presence_of_element_located((By.XPATH, f"//td[text()='{num_aluno}']/ancestor::tr")))
            todas_as_caixas = linha_aluno.find_elements(By.XPATH, ".//input[contains(@class, 'InputNotaStyled')]")
            if len(todas_as_caixas) > indice_coluna_alvo:
                input_nota_certo = todas_as_caixas[indice_coluna_alvo]
                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_nota_certo)
                time.sleep(0.2)
                
                if str(nota).strip() in ["0", "0.0", "0,0"]:
                    try: input_nota_certo.click(); input_nota_certo.send_keys(Keys.BACKSPACE, "0,0") 
                    except: navegador.execute_script(JS_REACT_SETTER, input_nota_certo, "0,0")
                else:
                    navegador.execute_script(JS_REACT_SETTER, input_nota_certo, nota)
                    
                time.sleep(0.2)
                input_nota_certo.send_keys(Keys.TAB)
                time.sleep(0.5)
        except Exception: pass

# ================= MOTOR CENTRAL =================
def vigiar():
    global ETAPA_ATUAL
    print("="*60)
    print(" 🚀 VERSÃO DO VIGIA: V30 (LIMPADOR DE PÁRA-BRISA ATIVADO)")
    print("="*60)
    
    try:
        planilha = conectar_sheets()
        
        try:
            valor_cru = str(planilha.worksheet("Config").acell("B1").value).strip().lower()
            if valor_cru:
                if "rec" in valor_cru and "1" in valor_cru: ETAPA_ATUAL = "Rec. 1ª Etapa"
                elif "rec" in valor_cru and "2" in valor_cru: ETAPA_ATUAL = "Rec. 2ª Etapa"
                elif "rec" in valor_cru and "3" in valor_cru: ETAPA_ATUAL = "Rec. 3ª Etapa"
                elif "1" in valor_cru: ETAPA_ATUAL = "1ª Etapa"
                elif "2" in valor_cru: ETAPA_ATUAL = "2ª Etapa"
                elif "3" in valor_cru: ETAPA_ATUAL = "3ª Etapa"
        except: pass
        
        abas_registos = [aba for aba in planilha.worksheets() if aba.title.startswith("registos_")]
        aulas_pendentes = []
        for aba in abas_registos:
            turma_nome = aba.title.replace("registos_", "")
            dados_brutos = aba.get_all_values()
            if len(dados_brutos) < 2: continue
            
            cabecalhos = [str(c).strip() for c in dados_brutos[0]]
            col_diario = next((i + 1 for i, c in enumerate(cabecalhos) if "DIARIO" in c.upper() or "DIÁRIO" in c.upper() or c.upper() == "STATUS"), 9)
            col_ocorrencia = next((i + 1 for i, c in enumerate(cabecalhos) if "OCORRENCIA" in c.upper() or "OCORRÊNCIA" in c.upper()), col_diario + 1)
            col_falta = next((i + 1 for i, c in enumerate(cabecalhos) if "FALTA" in c.upper()), col_diario + 2)
            
            for indice, row in enumerate(dados_brutos[1:]):
                linha_sheets = indice + 2 
                while len(row) < len(cabecalhos): row.append("")
                linha_dict = {cabecalhos[i]: row[i] for i in range(len(cabecalhos))}
                
                st_diario = str(row[col_diario - 1]).strip() if len(row) >= col_diario else ""
                st_ocor = str(row[col_ocorrencia - 1]).strip() if len(row) >= col_ocorrencia else ""
                st_falta = str(row[col_falta - 1]).strip() if len(row) >= col_falta else ""
                
                if "Pendente" in st_diario or "Pendente" in st_ocor or "Pendente" in st_falta:
                    aulas_pendentes.append({
                        "aba": aba, "linha_planilha": linha_sheets, 
                        "col_status_diario": col_diario, "status_diario": st_diario,
                        "col_status_ocorrencia": col_ocorrencia, "status_ocorrencia": st_ocor,
                        "col_status_falta": col_falta, "status_falta": st_falta,
                        "turma": turma_nome, "data": str(linha_dict.get("Data", "")).strip(),
                        "resumo": str(linha_dict.get("Resumo", "")).strip(), "para_casa": str(linha_dict.get("Para Casa", "")).strip(),
                        "nao_fez": str(linha_dict.get("Nao_Fez", "")).strip(), "tarefa_nao_feita": str(linha_dict.get("Tarefa_Nao_Feita", "")).strip(),
                        "faltas": str(linha_dict.get("Faltas", "")).strip(), "tipo_lancamento": st_diario
                    })

        abas_notas = [aba for aba in planilha.worksheets() if aba.title.startswith("Notas_")]
        notas_pendentes = []
        for aba in abas_notas:
            turma_nome = aba.title.replace("Notas_", "")
            dados = aba.get_all_values()
            if len(dados) < 5: continue
            for col_idx, status in enumerate(dados[1]):
                if str(status).strip() == "Pendente":
                    notas_alunos = {}
                    for row_idx in range(4, len(dados)):
                        numero_aluno = str(dados[row_idx][0]).strip()
                        nota = str(dados[row_idx][col_idx]).strip()
                        if numero_aluno and nota != "": notas_alunos[numero_aluno] = nota
                    notas_pendentes.append({
                        "aba": aba, "turma": turma_nome, "coluna_planilha": col_idx + 1,
                        "nome_prova": str(dados[0][col_idx]).strip(), "data_prova": str(dados[2][col_idx]).strip(),
                        "valor_prova": str(dados[3][col_idx]).strip(), "notas_alunos": notas_alunos, "etapa": ETAPA_ATUAL
                    })

        if not aulas_pendentes and not notas_pendentes:
            print(f"🟢 Nenhuma tarefa pendente.")
            return

        print(f"🚨 TAREFAS: {len(aulas_pendentes)} Aulas com Pendências | {len(notas_pendentes)} Provas")
        relatorio_telegram = f"🤖 <b>VIGIA DE AULAS - RESULTADO</b>\n⚙️ <b>Etapa:</b> {ETAPA_ATUAL}\n\n"
        
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        navegador = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(navegador, 10) 
        
        try:
            navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
            wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(MEU_CODIGO_ESCOLA)
            navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(MEU_LOGIN)
            navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(MINHA_SENHA)
            navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
            time.sleep(3)
            
            for aula in aulas_pendentes:
                print(f"\n-> Iniciando {aula['turma']} ({aula['data']})")
                relatorio_telegram += f"🏫 <b>{aula['turma']} ({aula['data']})</b>\n"
                try: navegador.switch_to.default_content()
                except: pass
                
                try:
                    navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
                    time.sleep(3)
                    
                    # 🔥 LIMPADOR DE PÁRA-BRISA (Fecha modais travados) 🔥
                    try: navegador.switch_to.alert.accept()
                    except: pass
                    try: navegador.execute_script("document.querySelectorAll('.swal2-container').forEach(e => e.remove());")
                    except: pass

                    try:
                        botao_exibir = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Exibir') or text()='Exibir']")))
                        navegador.execute_script("arguments[0].click();", botao_exibir)
                    except Exception: raise Exception("Botão 'Exibir' não carregou no painel inicial.")
                    
                    time.sleep(5)

                    turma_site = MAPA_TURMAS.get(aula['turma'].upper().strip(), aula['turma'])
                    try:
                        xpath_turma = f"//*[contains(text(), '{turma_site}')]/ancestor::tr//a[contains(text(), 'Diário de classe')] | //*[contains(text(), '{turma_site}')]/ancestor::div[contains(@class, 'card')]//a[contains(text(), 'Diário de classe')]"
                        botao_diario = WebDriverWait(navegador, 15).until(EC.element_to_be_clickable((By.XPATH, xpath_turma)))
                        navegador.execute_script("arguments[0].click();", botao_diario)
                    except Exception: raise Exception(f"Turma '{turma_site}' não foi achada na tela.")
                    
                    time.sleep(5) 
                    
                    if aula['status_diario'] in ["Pendente", "Pendente_Nova"]:
                        try:
                            script_js = f"""
                            var e = '{ETAPA_ATUAL}'.toUpperCase();
                            var rows = document.querySelectorAll('tr');
                            for (var i = 0; i < rows.length; i++) {{
                                var text = (rows[i].innerText || rows[i].textContent).toUpperCase();
                                if (text.includes(e)) {{
                                    if (!e.includes('REC') && text.includes('REC')) {{ continue; }}
                                    var links = rows[i].querySelectorAll('a');
                                    for (var j = 0; j < links.length; j++) {{
                                        var tLink = (links[j].innerText || links[j].textContent).toUpperCase();
                                        if (tLink.includes('REGISTRO')) {{ links[j].click(); return 'SUCESSO'; }}
                                    }}
                                }}
                            }} return 'FALHA';
                            """
                            navegador.switch_to.default_content()
                            if navegador.execute_script(script_js) == 'FALHA':
                                for f in navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame"):
                                    navegador.switch_to.default_content()
                                    try:
                                        navegador.switch_to.frame(f)
                                        if navegador.execute_script(script_js) == 'SUCESSO': break
                                    except: pass
                            time.sleep(3)
                            
                            try:
                                frames = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
                                if frames: navegador.switch_to.frame(frames[0])
                            except: pass
                            
                            if aula['status_diario'] == "Pendente_Nova":
                                wait.until(EC.element_to_be_clickable((By.ID, "DataAulaNovo"))).send_keys(Keys.CONTROL + "a", Keys.BACKSPACE, aula['data'], Keys.ESCAPE, Keys.TAB)
                                wait.until(EC.element_to_be_clickable((By.NAME, "ConteudoMinistradoNovo"))).send_keys(aula['resumo'])
                                wait.until(EC.element_to_be_clickable((By.NAME, "TarefaNovo"))).send_keys(aula['para_casa'])
                                botao_gravar = wait.until(EC.element_to_be_clickable((By.ID, "btnGravarNovo")))
                                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", botao_gravar)
                            else:
                                data_busca = aula['data'].strip()[:5]
                                botoes_editar = navegador.find_elements(By.XPATH, "//a[contains(text(), 'Editar') or contains(@title, 'Editar')] | //button[contains(text(), 'Editar')] | //input[@value='Editar']")
                                botao_alvo, linha_alvo = None, None
                                for botao in botoes_editar:
                                    linha = botao.find_element(By.XPATH, "./ancestor::tr[1]")
                                    textos = " ".join([str(inp.get_attribute("value")) for inp in linha.find_elements(By.TAG_NAME, "input") if inp.get_attribute("value")])
                                    if data_busca in (str(linha.text) + " " + textos):
                                        botao_alvo, linha_alvo = botao, linha
                                        break
                                if not botao_alvo: raise Exception(f"Data {aula['data']} não localizada para edição.")
                                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", botao_alvo)
                                time.sleep(2) 
                                caixas_texto = linha_alvo.find_elements(By.TAG_NAME, "textarea")
                                if len(caixas_texto) >= 2:
                                    caixas_texto[0].clear(); caixas_texto[0].send_keys(aula['resumo'], Keys.TAB)
                                    caixas_texto[1].clear(); caixas_texto[1].send_keys(aula['para_casa'], Keys.TAB)
                                navegador.execute_script("arguments[0].click();", linha_alvo.find_element(By.XPATH, ".//a[contains(text(), 'Gravar')] | .//button[contains(text(), 'Gravar')] | .//input[@value='Gravar']"))
                                
                            time.sleep(3)
                            
                            try: navegador.switch_to.alert.accept(); raise Exception("Alerta nativo de sistema do navegador.")
                            except Exception as e_a: 
                                if "Alerta nativo" in str(e_a): raise e_a
                                
                            try:
                                erro_swal = navegador.find_elements(By.XPATH, "//div[contains(@class, 'swal2-icon-error') or contains(@class, 'swal2-error')]")
                                if erro_swal and erro_swal[0].is_displayed():
                                    titulo_erro = navegador.find_element(By.ID, "swal2-title").text
                                    navegador.execute_script("arguments[0].click();", navegador.find_element(By.XPATH, "//button[contains(@class, 'swal2-confirm')]"))
                                    raise Exception(f"Activesoft recusou: {titulo_erro}")
                                btn_sim = navegador.find_elements(By.XPATH, "//button[contains(@class, 'swal2-confirm')]")
                                if btn_sim and btn_sim[0].is_displayed(): navegador.execute_script("arguments[0].click();", btn_sim[0])
                            except Exception as c_e:
                                if "Activesoft recusou" in str(c_e): raise c_e
                                
                            for err in navegador.find_elements(By.XPATH, "//*[contains(translate(text(), 'ERRO', 'erro'), 'erro') or contains(translate(text(), 'NÃO É POSSÍVEL', 'não é possível'), 'não é possível')]"):
                                if err.is_displayed():
                                    try: motivo = err.find_element(By.XPATH, "..").text
                                    except: motivo = err.text
                                    raise Exception(f"Aviso na tela: {motivo.replace(chr(10), ' - ')}")
                                
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_diario'], "Lançado")
                            print("   [Diário] ✅ Gravado com sucesso.")
                            relatorio_telegram += "  ✅ Diário gravado.\n"
                        except Exception as e_diario:
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_diario'], "Erro Sistema")
                            print(f"   [Diário] ❌ Erro: {str(e_diario)[:80]}")
                            relatorio_telegram += f"  ❌ Erro Diário: {str(e_diario)[:80]}\n"

                    if aula['status_ocorrencia'] in ["Pendente", "Pendente_Nova"]:
                        try:
                            lancar_ocorrencias(navegador, wait, aula)
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_ocorrencia'], "Lançado")
                            print("   [Ocorrências] ✅ Gravadas com sucesso.")
                            relatorio_telegram += "  ✅ Ocorrências gravadas.\n"
                        except Exception as e_ocor:
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_ocorrencia'], "Erro Sistema")
                            print(f"   [Ocorrências] ❌ Erro: {str(e_ocor)[:80]}")
                            relatorio_telegram += f"  ❌ Erro Ocorrências: {str(e_ocor)[:80]}\n"

                    if aula['status_falta'] in ["Pendente", "Pendente_Nova"]:
                        try:
                            lancar_faltas(navegador, wait, aula, ETAPA_ATUAL)
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_falta'], "Lançado")
                            print("   [Faltas] ✅ Gravadas com sucesso.")
                            relatorio_telegram += "  ✅ Faltas gravadas.\n"
                        except Exception as e_falta:
                            aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_falta'], "Erro Sistema")
                            print(f"   [Faltas] ❌ Erro: {str(e_falta)[:80]}")
                            relatorio_telegram += f"  ❌ Erro Faltas: {str(e_falta)[:80]}\n"

                except Exception as erro_abrir_painel:
                    print(f"❌ Falha crítica ao abrir a turma: {erro_abrir_painel}")
                    if "Pendente" in aula['status_diario']: aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_diario'], "Erro Sistema")
                    if "Pendente" in aula['status_ocorrencia']: aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_ocorrencia'], "Erro Sistema")
                    if "Pendente" in aula['status_falta']: aula['aba'].update_cell(aula['linha_planilha'], aula['col_status_falta'], "Erro Sistema")
                    relatorio_telegram += "  🚨 Falha geral ao abrir a turma no painel.\n"

            for nota in notas_pendentes:
                print(f"\n-> Iniciando Notas: {nota['nome_prova']} ({nota['turma']})")
                relatorio_telegram += f"\n📝 <b>Notas: {nota['nome_prova']} ({nota['turma']})</b>\n"
                try: navegador.switch_to.default_content()
                except: pass
                
                try:
                    navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
                    time.sleep(3)
                    
                    try: navegador.switch_to.alert.accept()
                    except: pass
                    try: navegador.execute_script("document.querySelectorAll('.swal2-container').forEach(e => e.remove());")
                    except: pass

                    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Exibir') or text()='Exibir']"))).click()
                    time.sleep(5)

                    turma_site = MAPA_TURMAS.get(nota['turma'].upper().strip(), nota['turma'])
                    WebDriverWait(navegador, 20).until(EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{turma_site}')]/ancestor::tr//*[contains(text(), 'Digitação de notas')] | //*[contains(text(), '{turma_site}')]/ancestor::div[contains(@class, 'card')]//*[contains(text(), 'Digitação de notas')]"))).click()
                    time.sleep(6) 
                    
                    lancar_notas(navegador, wait, nota)
                    nota['aba'].update_cell(2, nota['coluna_planilha'], "Lançado")
                    print("   [Notas] ✅ Prova lançada com sucesso.")
                    relatorio_telegram += "  ✅ Prova lançada com sucesso.\n"
                    
                except Exception as e_nota:
                    nota['aba'].update_cell(2, nota['coluna_planilha'], "Erro Sistema")
                    print(f"   [Notas] ❌ Erro ao lançar: {str(e_nota)[:80]}")
                    relatorio_telegram += f"  ❌ Erro ao lançar: {str(e_nota)[:80]}\n"

        finally:
            navegador.quit()
            avisar_telegram(relatorio_telegram)

    except Exception as erro_geral:
        print(f"⚠️ Erro crítico: {erro_geral}")

if __name__ == "__main__":
    vigiar()
