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

# ================= CORREÇÃO GLOBAL DE REDE E SSL =================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# ================= CONFIGURAÇÕES DO PROFESSOR =================
MEU_CODIGO_ESCOLA = "COLEGIOM2"
MEU_LOGIN = "Marcelo3892" 
MINHA_SENHA = os.environ.get("SENHA_ACTIVESOFT", "SuaSenhaLocalAqui") 

# Etapa Padrão (Será substituída se houver a aba 'Config' na planilha)
ETAPA_ATUAL = "2ª Etapa"

# 🔥 DICIONÁRIO DE TURMAS EXPANDIDO (Com 3EM, 9A, 8B, etc)
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

JS_REACT_SETTER = """
    let elemento = arguments[0];
    let valor = arguments[1];
    let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(elemento, valor);
    elemento.dispatchEvent(new Event('input', { bubbles: true }));
    elemento.dispatchEvent(new Event('change', { bubbles: true }));
"""

def avisar_telegram(mensagem):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=10)
    except: pass

def conectar_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", SCOPE) 
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

# ================= FUNÇÕES DO DIÁRIO =================
def lancar_ocorrencias(navegador, wait, aula):
    if not str(aula.get('nao_fez', '')).strip(): return
    try:
        texto_ocorrencia = f"Não fez a tarefa: {aula['tarefa_nao_feita']}"
        numeros_alvo = [num.strip() for num in aula['nao_fez'].split(',')]
        try: navegador.switch_to.default_content()
        except: pass
        time.sleep(2)
        
        botao_ocorrencias = wait.until(EC.element_to_be_clickable((By.ID, "ocorrencias_de_alunos")))
        navegador.execute_script("arguments[0].click();", botao_ocorrencias)
        time.sleep(3)

        xpath_registrar = "//a[@href='/gerar_ocorrencias_lote/' or contains(text(), 'Registrar ocorrência')]"
        botao_registrar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_registrar)))
        navegador.execute_script("arguments[0].click();", botao_registrar)
        time.sleep(3)

        xpath_pesquisar = "//button[normalize-space(text())='Pesquisar']"
        botao_pesquisar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_pesquisar)))
        navegador.execute_script("arguments[0].click();", botao_pesquisar)
        time.sleep(5) 
        
        nome_plan = aula['turma'].upper().strip()
        num_t = "".join([c for c in nome_plan if c.isdigit()])
        letra_t = "A" if nome_plan.endswith("A") else "B" if nome_plan.endswith("B") else ""

        for num in numeros_alvo:
            try:
                linhas = navegador.find_elements(By.XPATH, f"//tr[td[normalize-space(text())='{num}']]")
                clicado = False
                for linha in linhas:
                    texto_turma = ""
                    for td in linha.find_elements(By.TAG_NAME, "td"):
                        if "/" in td.text and ("ANO" in td.text.upper() or "SÉRIE" in td.text.upper() or "SERIE" in td.text.upper()):
                            texto_turma = td.text.upper().strip()
                            break
                    if not texto_turma: texto_turma = linha.text.upper().strip()
                    
                    if num_t in texto_turma:
                        match = False
                        if letra_t: 
                            if texto_turma.endswith(letra_t): match = True
                        else: 
                            if "SÉRIE" in texto_turma or "SERIE" in texto_turma: match = True
                                
                        if match:
                            checkbox = linha.find_element(By.XPATH, ".//input[@type='checkbox']")
                            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
                            time.sleep(0.5)
                            if not checkbox.is_selected():
                                navegador.execute_script("arguments[0].click();", checkbox)
                            clicado = True
                            break 
            except: pass

        xpath_proximo = "//button[contains(., 'Próximo')]"
        botao_proximo = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_proximo)))
        navegador.execute_script("arguments[0].click();", botao_proximo)
        time.sleep(3)

        try:
            input_data = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='DD/MM/AAAA']")))
            input_data.click()
            input_data.send_keys(Keys.CONTROL + "a")
            input_data.send_keys(Keys.BACKSPACE)
            input_data.send_keys(aula['data'])
            input_data.send_keys(Keys.ESCAPE)
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
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_internet)
            navegador.execute_script("arguments[0].click();", botao_internet)
        except: pass

        try:
            caixa_obs = navegador.find_element(By.XPATH, "//textarea[contains(@class, 'form-control')]")
            caixa_obs.clear()
            caixa_obs.send_keys(texto_ocorrencia)
        except: pass

        try:
            botao_executar = navegador.find_element(By.XPATH, "//button[contains(text(), 'Executar')]")
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_executar)
            time.sleep(1)
            navegador.execute_script("arguments[0].click();", botao_executar)
            try: wait.until(EC.alert_is_present()).accept()
            except: pass
        except: pass

    except: pass
    finally:
        try: navegador.switch_to.default_content()
        except: pass

def lancar_faltas(navegador, wait, aula, etapa_atual):
    if aula['tipo_lancamento'] != "Pendente_Nova": return
    print(f"   [Frequência] Iniciando chamada para {aula['turma']}...")
    try:
        try: navegador.switch_to.default_content()
        except: pass
        time.sleep(2)
        
        try:
            botao_freq = wait.until(EC.element_to_be_clickable((By.ID, "frequencia_em_lote")))
            navegador.execute_script("arguments[0].click();", botao_freq)
        except:
            navegador.get("https://siga02.activesoft.com.br/diarios/frequencia_em_lote/")
        time.sleep(5)
        
        turma_bruta = aula['turma'].upper()
        curso = "FUNDAMENTAL" if "ANO" in turma_bruta else "MÉDIO"
        
        serie = ""
        for s in ["6", "7", "8", "9"]:
            if s in turma_bruta: serie = f"{s}° ANO"
        for s in ["1", "2", "3"]:
            if f"{s} SÉRIE" in turma_bruta or f"{s}ª SÉRIE" in turma_bruta: serie = f"{s}ª SÉRIE"
            
        turma_exata = turma_bruta.replace("º", "°")
        
        print("   [Frequência] 📍 Aplicando injeção JS dinâmica nas caixas de seleção...")
        
        # Função blindada: Re-busca os elementos na tela a cada iteração para driblar o React
        def preencher_select_blindado(idx, texto):
            try:
                # 1. Busca os inputs na hora (evita StaleElementReference)
                navegador.switch_to.default_content()
                inps = navegador.find_elements(By.XPATH, "//input[contains(@id, 'react-select') or @aria-autocomplete='list']")
                
                if not inps: # Caçador de iframes
                    frames = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
                    for f in frames:
                        navegador.switch_to.default_content()
                        try:
                            navegador.switch_to.frame(f)
                            inps = navegador.find_elements(By.XPATH, "//input[contains(@id, 'react-select') or @aria-autocomplete='list']")
                            if inps: break
                        except: pass
                        
                if idx >= len(inps): return
                inp = inps[idx]
                
                # 2. Rola a tela até a caixa e espera
                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                time.sleep(1)
                
                # 3. Força a abertura da caixa
                try: navegador.execute_script("arguments[0].parentNode.parentNode.click();", inp)
                except: pass
                time.sleep(1)
                
                navegador.execute_script("arguments[0].focus();", inp)
                
                # 4. Tenta digitar. Se o React der "not interactable", injeta na força bruta com JS (A Vacina das Notas)
                try:
                    inp.send_keys(Keys.CONTROL + "a")
                    inp.send_keys(Keys.BACKSPACE)
                    inp.send_keys(texto)
                except:
                    navegador.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", inp, texto)
                    
                time.sleep(1.5)
                
                # 5. Clica na opção que apareceu
                opcoes = navegador.find_elements(By.XPATH, f"//div[text()='{texto}'] | //li[text()='{texto}'] | //div[contains(text(), '{texto}')]")
                if opcoes:
                    navegador.execute_script("arguments[0].click();", opcoes[-1])
                else:
                    navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'ArrowDown'}));", inp)
                    time.sleep(0.5)
                    navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", inp)
                
                time.sleep(2) # Pausa crucial para o Activesoft carregar o próximo filtro
            except Exception as e:
                print(f"   [Frequência] ⚠️ Falha ao preencher filtro {idx}: {e}")

        # Índices: Curso(1), Série(2), Turma(3), Etapa(4)
        preencher_select_blindado(1, curso)        
        preencher_select_blindado(2, serie)        
        preencher_select_blindado(3, turma_exata)  
        preencher_select_blindado(4, etapa_atual)  
        
        try:
            input_data_ini = navegador.find_element(By.XPATH, "//input[contains(@class, 'InitialDatePicker')] | //input[@name='dataInicial']")
            input_data_fim = navegador.find_element(By.XPATH, "//input[contains(@class, 'FinalDatePicker')] | //input[@name='dataFinal']")
            
            navegador.execute_script(JS_REACT_SETTER, input_data_ini, aula['data'])
            navegador.execute_script(JS_REACT_SETTER, input_data_fim, aula['data'])
            time.sleep(1)
        except: pass

        try:
            botao_consultar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Consultar']")))
            navegador.execute_script("arguments[0].click();", botao_consultar)
            time.sleep(5) 
        except:
            print("   [Frequência] ⚠️ Não consegui clicar em 'Consultar'.")
        
        try:
            botao_selecione = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Selecione')]")))
            navegador.execute_script("arguments[0].click();", botao_selecione)
            time.sleep(1)
            opcao_presente = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Presente')] | //li[contains(text(), 'Presente')]")))
            navegador.execute_script("arguments[0].click();", opcao_presente)
            time.sleep(2)
        except: pass
            
        faltas_str = str(aula.get('faltas', '')).strip()
        if faltas_str:
            numeros_falta = [n.strip() for n in faltas_str.split(',')]
            for num in numeros_falta:
                try:
                    linha = navegador.find_element(By.XPATH, f"//tr[td[normalize-space(text())='{num}']]")
                    botao_status = linha.find_element(By.XPATH, ".//button[contains(@class, 'Toggle__ToggleButton')]")
                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_status)
                    time.sleep(0.5)
                    navegador.execute_script("arguments[0].click();", botao_status)
                    time.sleep(1)
                    
                    opcao_falta = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[text()='Falta'] | //li[text()='Falta'] | //button[text()='Falta']")))
                    navegador.execute_script("arguments[0].click();", opcao_falta)
                    time.sleep(0.5)
                    print(f"         ✔️ Falta cravada para o aluno Nº {num}")
                except: print(f"         ❌ Falha ao tentar marcar falta para o aluno Nº {num}")
        
        try:
            botao_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Salvar']")))
            navegador.execute_script("arguments[0].click();", botao_salvar)
            time.sleep(3)
            try: wait.until(EC.alert_is_present()).accept()
            except: pass
            print("   [Frequência] ✅ Chamada registrada e salva!")
        except:
            print("   [Frequência] ⚠️ Botão de salvar não encontrado (A lista de alunos pode não ter carregado).")
            
    except Exception as e: print(f"   [Frequência] ⚠️ Erro crítico: {e}")
    finally:
        try: navegador.switch_to.default_content()
        except: pass

# ================= MÓDULO DE NOTAS =================
def lancar_notas(navegador, wait, nota_info):
    print(f"   [Notas] ⏳ Varrendo iframes...")
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
            try:
                navegador.switch_to.frame(f)
                input_escondido = navegador.find_element(By.XPATH, "//input[contains(@id, 'react-select')]")
                if input_escondido: break
            except: pass
        if input_escondido: break
        time.sleep(1.5)
        
    if not input_escondido: raise Exception("Campo de Etapa sumiu.")

    print(f"   [Notas] 📍 [1/4] Selecionando a Etapa ({nota_info['etapa']})...")
    try:
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
        
        btn_consultar = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Consultar')]")))
        navegador.execute_script("arguments[0].click();", btn_consultar) 
        time.sleep(3) 

        print(f"   [Notas] 📍 [2/4] Criando nova avaliação...")
        btn_inserir = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Inserir avaliação')] | //*[name()='svg' and contains(@class, 'FaseNota')]")))
        navegador.execute_script("arguments[0].click();", btn_inserir)
        time.sleep(1.5)

        btn_nova = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Nova avaliação')]")))
        navegador.execute_script("arguments[0].click();", btn_nova)
        time.sleep(1.5) 
        
        print(f"   [Notas] 📍 [3/4] Preenchendo dados da prova ({nota_info['nome_prova']})...")
        input_nome = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Input-sg8yoa-0') and not(@readonly)]")))
        navegador.execute_script(JS_REACT_SETTER, input_nome, nota_info['nome_prova'])
        time.sleep(0.5)
        
        input_data = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Datepicker')]")))
        navegador.execute_script(JS_REACT_SETTER, input_data, nota_info['data_prova'])
        time.sleep(0.5)
        
        input_valor = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'InputDecimal')]")))
        navegador.execute_script(JS_REACT_SETTER, input_valor, nota_info['valor_prova'])
        time.sleep(0.5)
        
        btn_salvar = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Salvar')]")))
        navegador.execute_script("arguments[0].click();", btn_salvar)
        
        print("   [Notas]        -> Aguardando alerta de confirmação...")
        wait_modal = WebDriverWait(navegador, 10)
        btn_fechar = wait_modal.until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'swal2-confirm') or text()='Fechar']")))
        navegador.execute_script("arguments[0].click();", btn_fechar)
        time.sleep(3)
        
        print(f"   [Notas] 📍 [4/4] Lançando as notas com Mira a Laser...")
        cabecalhos_provas = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'TextClick')]")))
        
        indice_coluna_alvo = -1
        for i, cabecalho in enumerate(cabecalhos_provas):
            if cabecalho.text.strip() == nota_info['nome_prova']:
                indice_coluna_alvo = i
                break
                
        if indice_coluna_alvo == -1: indice_coluna_alvo = len(cabecalhos_provas) - 1 
        
        for num_aluno, nota in nota_info['notas_alunos'].items():
            try:
                linha_aluno = wait.until(EC.presence_of_element_located((By.XPATH, f"//td[text()='{num_aluno}']/ancestor::tr")))
                todas_as_caixas = linha_aluno.find_elements(By.XPATH, ".//input[contains(@class, 'InputNotaStyled')]")
                if len(todas_as_caixas) > indice_coluna_alvo:
                    input_nota_certo = todas_as_caixas[indice_coluna_alvo]
                    navegador.execute_script(JS_REACT_SETTER, input_nota_certo, nota)
                    time.sleep(0.2)
                    input_nota_certo.send_keys(Keys.TAB)
                    print(f"   [Notas]        ✔️ Lançado: Aluno {num_aluno} -> {nota}")
                    time.sleep(0.5)
            except Exception as e_nota: print(f"   [Notas]        ❌ Erro aluno {num_aluno}")

        print("   [Notas] ✅ Finalizado com sucesso! Notas na coluna correta.")
    except Exception as e:
        print(f"   [Notas] ❌ O robô de notas tropeçou: {e}")
        raise e

# ================= MOTOR CENTRAL =================
def vigiar():
    global ETAPA_ATUAL
    print("="*60)
    print(" 🚀 VERSÃO DO VIGIA: V19 (ETAPA DINÂMICA E MAPA TURBINADO)")
    print(" 👁️ SUPER VIGIA CENTRAL (DIÁRIOS + NOTAS) - GITHUB ACTIONS")
    print("="*60)
    
    hora_atual = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{hora_atual}] Varrendo o Google Sheets...")
    
    try:
        planilha = conectar_sheets()
        
        # 🛡️ NOVIDADE: LENDO A ETAPA DA ABA CONFIG 🛡️
        try:
            aba_config = planilha.worksheet("Config")
            valor_etapa = aba_config.acell("B1").value
            if valor_etapa:
                ETAPA_ATUAL = str(valor_etapa).strip()
                print(f"   ⚙️  INFO: Etapa atualizada pela planilha -> '{ETAPA_ATUAL}'")
        except:
            print(f"   ⚙️  INFO: Aba 'Config' não achada. Usando padrão -> '{ETAPA_ATUAL}'")
        
        abas_registos = [aba for aba in planilha.worksheets() if aba.title.startswith("registos_")]
        aulas_pendentes = []
        for aba in abas_registos:
            turma_nome = aba.title.replace("registos_", "")
            dados = aba.get_all_records()
            if not dados: continue
            
            cabecalhos = list(dados[0].keys())
            try: coluna_status = cabecalhos.index("Status") + 1
            except ValueError: coluna_status = 9 
            
            for indice, linha in enumerate(dados):
                linha_sheets = indice + 2 
                status_atual = str(linha.get("Status", "")).strip()
                if status_atual in ["Pendente", "Pendente_Nova"]:
                    aulas_pendentes.append({
                        "aba": aba, "linha_planilha": linha_sheets, "coluna_status": coluna_status,
                        "turma": turma_nome, "data": str(linha.get("Data", "")).strip(),
                        "resumo": str(linha.get("Resumo", "")).strip(), "para_casa": str(linha.get("Para Casa", "")).strip(),
                        "nao_fez": str(linha.get("Nao_Fez", "")).strip(), "tarefa_nao_feita": str(linha.get("Tarefa_Nao_Feita", "")).strip(),
                        "faltas": str(linha.get("Faltas", "")).strip(), "tipo_lancamento": status_atual
                    })

        abas_notas = [aba for aba in planilha.worksheets() if aba.title.startswith("Notas_")]
        notas_pendentes = []
        for aba in abas_notas:
            turma_nome = aba.title.replace("Notas_", "")
            dados = aba.get_all_values()
            if len(dados) < 5: continue
            
            linha_status = dados[1] 
            for col_idx, status in enumerate(linha_status):
                if str(status).strip() == "Pendente":
                    nome_prova = str(dados[0][col_idx]).strip()
                    data_prova = str(dados[2][col_idx]).strip()
                    valor_prova = str(dados[3][col_idx]).strip()
                    
                    notas_alunos = {}
                    for row_idx in range(4, len(dados)):
                        numero_aluno = str(dados[row_idx][0]).strip()
                        nota = str(dados[row_idx][col_idx]).strip()
                        if numero_aluno and nota:
                            notas_alunos[numero_aluno] = nota
                            
                    notas_pendentes.append({
                        "aba": aba, "turma": turma_nome,
                        "coluna_planilha": col_idx + 1,
                        "nome_prova": nome_prova, "data_prova": data_prova,
                        "valor_prova": valor_prova, "notas_alunos": notas_alunos,
                        "etapa": ETAPA_ATUAL
                    })

        if not aulas_pendentes and not notas_pendentes:
            print(f"🟢 Tudo em dia! Nenhuma tarefa pendente. Encerrando execução.")
            return

        print(f"🚨 TAREFAS: {len(aulas_pendentes)} Diários | {len(notas_pendentes)} Provas")
        
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        navegador = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(navegador, 10) 
        
        try:
            print("🔑 Fazendo login no sistema Activesoft...")
            navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
            wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(MEU_CODIGO_ESCOLA)
            navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(MEU_LOGIN)
            navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(MINHA_SENHA)
            navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
            time.sleep(3)
            
            try:
                xpath_logo = "//img[@alt='Activesoft Logo']"
                botao_logo = WebDriverWait(navegador, 3).until(EC.element_to_be_clickable((By.XPATH, xpath_logo)))
                navegador.execute_script("arguments[0].click();", botao_logo)
                time.sleep(2)
            except: pass 
            
            for aula in aulas_pendentes:
                try: navegador.switch_to.default_content()
                except: pass
                
                print(f"\n-> [DIÁRIO] Iniciando fluxo da turma {aula['turma']} ({aula['data']})")
                try:
                    navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
                    time.sleep(3)
                    
                    botao_exibir = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Exibir') or text()='Exibir']")))
                    navegador.execute_script("arguments[0].click();", botao_exibir)
                    time.sleep(5)

                    chave_busca = aula['turma'].upper().strip()
                    turma_site = MAPA_TURMAS.get(chave_busca, aula['turma'])
                    
                    wait_longo = WebDriverWait(navegador, 20)
                    xpath_turma = f"//*[contains(text(), '{turma_site}')]/ancestor::tr//a[contains(text(), 'Diário de classe')] | //*[contains(text(), '{turma_site}')]/ancestor::div[contains(@class, 'card')]//a[contains(text(), 'Diário de classe')]"
                    botao_diario = wait_longo.until(EC.element_to_be_clickable((By.XPATH, xpath_turma)))
                    navegador.execute_script("arguments[0].click();", botao_diario)
                    time.sleep(5) 
                    
                    numero_etapa = ETAPA_ATUAL[0] 
                    script_js = f"""
                    var num = '{numero_etapa}'; var rows = document.querySelectorAll('tr');
                    for (var i = 0; i < rows.length; i++) {{
                        var textoLinha = (rows[i].innerText || rows[i].textContent).toUpperCase();
                        if (textoLinha.includes(num) && textoLinha.includes('ETAPA') && !textoLinha.includes('RECUP')) {{
                            var links = rows[i].querySelectorAll('a');
                            for (var j = 0; j < links.length; j++) {{
                                var textoLink = (links[j].innerText || links[j].textContent).toUpperCase();
                                if (textoLink.includes('REGISTRO')) {{ links[j].click(); return 'SUCESSO'; }}
                            }}
                        }}
                    }} return 'FALHA';
                    """
                    navegador.switch_to.default_content()
                    resultado_js = navegador.execute_script(script_js)
                    
                    if resultado_js == 'FALHA':
                        frames = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
                        for f in frames:
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
                    
                    if aula['tipo_lancamento'] == "Pendente_Nova":
                        campo_data_nova = wait.until(EC.element_to_be_clickable((By.ID, "DataAulaNovo")))
                        campo_data_nova.click()
                        campo_data_nova.send_keys(Keys.CONTROL + "a")
                        campo_data_nova.send_keys(Keys.BACKSPACE)
                        campo_data_nova.send_keys(aula['data'])
                        time.sleep(0.5)
                        campo_data_nova.send_keys(Keys.ESCAPE)
                        campo_data_nova.send_keys(Keys.TAB)
                        time.sleep(1)

                        campo_conteudo = wait.until(EC.element_to_be_clickable((By.NAME, "ConteudoMinistradoNovo")))
                        campo_conteudo.click()
                        campo_conteudo.clear()
                        campo_conteudo.send_keys(aula['resumo'])
                        time.sleep(0.5)
                        
                        campo_tarefa = wait.until(EC.element_to_be_clickable((By.NAME, "TarefaNovo")))
                        campo_tarefa.click()
                        campo_tarefa.clear()
                        campo_tarefa.send_keys(aula['para_casa'])
                        time.sleep(1)

                        botao_gravar_novo = wait.until(EC.element_to_be_clickable((By.ID, "btnGravarNovo")))
                        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_gravar_novo)
                        time.sleep(0.5)
                        navegador.execute_script("arguments[0].click();", botao_gravar_novo)
                        time.sleep(3) 
                    else:
                        data_busca = aula['data'].strip()[:5]
                        xpath_botoes = "//a[contains(text(), 'Editar') or contains(@title, 'Editar')] | //button[contains(text(), 'Editar')] | //input[@value='Editar']"
                        botoes_editar = navegador.find_elements(By.XPATH, xpath_botoes)
                        
                        botao_alvo = None
                        linha_alvo = None
                        for botao in botoes_editar:
                            linha = botao.find_element(By.XPATH, "./ancestor::tr[1]")
                            textos_inputs = " ".join([str(inp.get_attribute("value")) for inp in linha.find_elements(By.TAG_NAME, "input") if inp.get_attribute("value")])
                            if data_busca in (str(linha.text) + " " + textos_inputs):
                                botao_alvo = botao
                                linha_alvo = linha
                                break
                        if not botao_alvo or not linha_alvo: raise Exception(f"Data {aula['data']} não localizada.")

                        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", linha_alvo)
                        time.sleep(1)
                        navegador.execute_script("arguments[0].click();", botao_alvo)
                        time.sleep(2) 

                        caixas_texto = linha_alvo.find_elements(By.TAG_NAME, "textarea")
                        if len(caixas_texto) >= 2:
                            caixas_texto[0].click(); caixas_texto[0].clear()
                            caixas_texto[0].send_keys(aula['resumo'])
                            caixas_texto[0].send_keys(Keys.TAB)
                            time.sleep(1)

                            caixas_texto[1].click(); caixas_texto[1].clear()
                            caixas_texto[1].send_keys(aula['para_casa'])
                            caixas_texto[1].send_keys(Keys.TAB)
                            time.sleep(1)
                        
                        botao_gravar = linha_alvo.find_element(By.XPATH, ".//a[contains(text(), 'Gravar')] | .//button[contains(text(), 'Gravar')] | .//input[@value='Gravar']")
                        navegador.execute_script("arguments[0].click();", botao_gravar)
                        time.sleep(3)

                    lancar_ocorrencias(navegador, wait, aula)
                    lancar_faltas(navegador, wait, aula, ETAPA_ATUAL)
                    navegador.switch_to.default_content() 
                    aula['aba'].update_cell(aula['linha_planilha'], aula['coluna_status'], "Lançado")
                    
                except Exception as e_aula:
                    print(f"   ❌ Erro na aula {aula['data']}: {e_aula}")
                    try: aula['aba'].update_cell(aula['linha_planilha'], aula['coluna_status'], "Erro Sistema")
                    except: pass

            for nota in notas_pendentes:
                try: navegador.switch_to.default_content()
                except: pass
                
                print(f"\n-> [NOTAS] Iniciando fluxo da avaliação '{nota['nome_prova']}' - Turma {nota['turma']}")
                try:
                    navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
                    time.sleep(3)
                    
                    botao_exibir = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Exibir') or text()='Exibir']")))
                    navegador.execute_script("arguments[0].click();", botao_exibir)
                    time.sleep(5)

                    chave_busca = nota['turma'].upper().strip()
                    turma_site = MAPA_TURMAS.get(chave_busca, nota['turma'])
                    
                    wait_longo = WebDriverWait(navegador, 20)
                    
                    print(f"   [Notas] 📍 Clicando no botão 'Digitação de notas' do painel...")
                    xpath_turma_notas = f"//*[contains(text(), '{turma_site}')]/ancestor::tr//*[contains(text(), 'Digitação de notas')] | //*[contains(text(), '{turma_site}')]/ancestor::div[contains(@class, 'card')]//*[contains(text(), 'Digitação de notas')]"
                    botao_notas_dash = wait_longo.until(EC.element_to_be_clickable((By.XPATH, xpath_turma_notas)))
                    navegador.execute_script("arguments[0].click();", botao_notas_dash)
                    time.sleep(6) 
                    
                    lancar_notas(navegador, wait, nota)
                    nota['aba'].update_cell(2, nota['coluna_planilha'], "Lançado")
                    
                except Exception as e_nota:
                    print(f"   ❌ Erro ao lançar notas: {e_nota}")
                    try: nota['aba'].update_cell(2, nota['coluna_planilha'], "Erro Sistema")
                    except: pass

        finally:
            navegador.quit()
            print("\n🔒 Fechando o navegador. Execução concluída!\n")

    except Exception as erro_geral:
        print(f"⚠️ Erro crítico: {erro_geral}")

if __name__ == "__main__":
    vigiar()
