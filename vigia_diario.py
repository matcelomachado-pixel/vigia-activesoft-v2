import os
import sys
import time
import re
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
try: 
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError: 
    pass

SPREADSHEET_ID = '17XZfEUKiiryGJgj_nXdQ7gXzdByEwsZ7ecax44ZeJmc'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

MAPA_TURMAS = {
    "8º ANO A": "EFII-8A-FD", "8º A": "EFII-8A-FD", "8 ANO A": "EFII-8A-FD", "8A": "EFII-8A-FD",
    "8º ANO B": "EFII-8B-FD", "8º B": "EFII-8B-FD", "8 ANO B": "EFII-8B-FD", "8B": "EFII-8B-FD",
    "9º ANO A": "EFII-9A-FD", "9º A": "EFII-9A-FD", "9 ANO A": "EFII-9A-FD", "9A": "EFII-9A-FD",
    "9º ANO B": "EFII-9B-FD", "9º B": "EFII-9B-FD", "9 ANO B": "EFII-9B-FD", "9B": "EFII-9B-FD",
    "1ª SÉRIE": "1ª SÉRIE", "1ª SÉRIE EM": "1ª SÉRIE", "1EM": "1ª SÉRIE", "1": "1ª SÉRIE",
    "2ª SÉRIE": "EM-2SEM-FD", "2ª SÉRIE EM": "EM-2SEM-FD", "2 SÉRIE": "EM-2SEM-FD", "2EM": "EM-2SEM-FD", "2": "EM-2SEM-FD",
    "3ª SÉRIE": "EM-3SEM-FD", "3ª SÉRIE EM": "EM-3SEM-FD", "3 SÉRIE": "EM-3SEM-FD", "3EM": "EM-3SEM-FD", "3": "EM-3SEM-FD",
    "6º ANO A": "6° ANO A", "6º ANO B": "6º ANO B", "6º A": "6° ANO A", "6º B": "6º ANO B", "6A": "6° ANO A", "6B": "6º ANO B", "6": "6° ANO A",
    "7º ANO A": "7° ANO A", "7º ANO B": "7º ANO B", "7º A": "7° ANO A", "7º B": "7º ANO B", "7A": "7° ANO A", "7B": "7º ANO B", "7": "7° ANO A"
}

JS_REACT_SETTER = """
    let elemento = arguments[0];
    let valor = arguments[1];
    let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(elemento, valor);
    elemento.dispatchEvent(new Event('input', { bubbles: true }));
    elemento.dispatchEvent(new Event('change', { bubbles: true }));
"""

def avisar_telegram(chat_id, mensagem):
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def conectar_sheets():
    for tentativa in range(6):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", SCOPE) 
            client = gspread.authorize(creds)
            return client.open_by_key(SPREADSHEET_ID)
        except Exception as e:
            if '429' in str(e) or 'Quota' in str(e):
                espera = 10 * (tentativa + 1)
                print(f"⏳ Limite do Google (429). Aguardando {espera}s...")
                time.sleep(espera)
            else:
                raise e
    raise Exception("Falha de conexão com o Google Sheets.")

def safe_get_values(aba):
    for tentativa in range(6):
        try:
            return aba.get_all_values()
        except Exception as e:
            if '429' in str(e) or 'Quota' in str(e):
                time.sleep(10 * (tentativa + 1))
            else:
                raise e
    return []

def safe_update(aba, row, col, val):
    for tentativa in range(6):
        try:
            aba.update_cell(row, col, val)
            return
        except Exception as e:
            if '429' in str(e) or 'Quota' in str(e):
                time.sleep(10 * (tentativa + 1))
            else:
                return

def achar_e_clicar(navegador, xpath_alvo, tempo_espera=3):
    navegador.switch_to.default_content()
    try:
        btn = WebDriverWait(navegador, tempo_espera).until(EC.presence_of_element_located((By.XPATH, xpath_alvo)))
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        time.sleep(0.5); navegador.execute_script("arguments[0].click();", btn)
        return True
    except: pass
        
    for f in navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame"):
        navegador.switch_to.default_content()
        try:
            navegador.switch_to.frame(f)
            btn = WebDriverWait(navegador, tempo_espera).until(EC.presence_of_element_located((By.XPATH, xpath_alvo)))
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.5); navegador.execute_script("arguments[0].click();", btn)
            return True
        except: pass
    return False

def check_swal_alert(navegador, contexto=""):
    try:
        time.sleep(2)
        swal = navegador.find_elements(By.XPATH, "//div[contains(@class, 'swal2-popup')]")
        if swal and swal[0].is_displayed():
            is_error_or_warning = navegador.find_elements(By.XPATH, "//div[contains(@class, 'swal2-icon-error') or contains(@class, 'swal2-error') or contains(@class, 'swal2-warning') or contains(@class, 'swal2-info')]")
            if is_error_or_warning and is_error_or_warning[0].is_displayed():
                msg = navegador.find_element(By.ID, "swal2-title").text
                try:
                    btn_confirm = navegador.find_element(By.XPATH, "//button[contains(@class, 'swal2-confirm')]")
                    navegador.execute_script("arguments[0].click();", btn_confirm)
                except: pass
                raise Exception(f"Bloqueio do Site ({contexto}): {msg}")
            else:
                try:
                    btn_confirm = navegador.find_element(By.XPATH, "//button[contains(@class, 'swal2-confirm')]")
                    if btn_confirm.is_displayed(): navegador.execute_script("arguments[0].click();", btn_confirm)
                except: pass
    except Exception as e:
        if "Bloqueio do Site" in str(e): raise e

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
        navegador.execute_script("arguments[0].click();", botao_ocorrencias); time.sleep(3)

        xpath_registrar = "//a[@href='/gerar_ocorrencias_lote/' or contains(text(), 'Registrar ocorrência')]"
        botao_registrar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_registrar)))
        navegador.execute_script("arguments[0].click();", botao_registrar); time.sleep(3)

        xpath_pesquisar = "//button[normalize-space(text())='Pesquisar']"
        botao_pesquisar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_pesquisar)))
        navegador.execute_script("arguments[0].click();", botao_pesquisar)
        
        print("   [Ocorrências] Aguardando lista de alunos...")
        time.sleep(4)
        check_swal_alert(navegador, "Ocorrências")
        
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//tbody/tr")))
        except:
            raise Exception("A tabela não carregou. Verifique se a data ou a etapa estão bloqueadas pela escola.")
        
        turma_exata = aula['turma_ativa'].upper()
        num_t = "".join([c for c in aula['turma_ativa'] if c.isdigit()])
        letra_t = aula['turma_ativa'][-1] if aula['turma_ativa'][-1].isalpha() else ""

        for num in numeros_alvo:
            try:
                linhas = navegador.find_elements(By.XPATH, f"//tr[td[normalize-space(text())='{num}']]")
                for linha in linhas:
                    texto_turma = ""
                    for td in linha.find_elements(By.TAG_NAME, "td"):
                        if "/" in td.text and ("ANO" in td.text.upper() or "SÉRIE" in td.text.upper() or "SERIE" in td.text.upper()):
                            texto_turma = td.text.upper().strip(); break
                            
                    if not texto_turma: texto_turma = linha.text.upper().strip()
                        
                    if num_t in texto_turma:
                        match = False
                        if letra_t: 
                            if texto_turma.endswith(letra_t): match = True
                        else: 
                            if "SÉRIE" in texto_turma or "SERIE" in texto_turma: match = True
                            
                        if match:
                            checkbox = linha.find_element(By.XPATH, ".//input[@type='checkbox']")
                            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox); time.sleep(0.5)
                            if not checkbox.is_selected(): navegador.execute_script("arguments[0].click();", checkbox)
                            break 
            except: pass

        xpath_proximo = "//button[contains(., 'Próximo')]"
        botao_proximo = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_proximo)))
        navegador.execute_script("arguments[0].click();", botao_proximo); time.sleep(3)

        try:
            input_data = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='DD/MM/AAAA']")))
            input_data.click(); time.sleep(0.5)
            input_data.send_keys(Keys.CONTROL + "a"); input_data.send_keys(Keys.BACKSPACE)
            input_data.send_keys(aula['data']); time.sleep(0.5); input_data.send_keys(Keys.ENTER); time.sleep(0.5); input_data.send_keys(Keys.ESCAPE)
        except: pass

        try:
            input_react = navegador.find_element(By.XPATH, "//input[@aria-autocomplete='list']")
            navegador.execute_script("arguments[0].focus();", input_react)
            input_react.send_keys("Não apresentou para casa"); time.sleep(1); input_react.send_keys(Keys.ENTER)
        except: pass

        try:
            botao_internet = navegador.find_element(By.XPATH, "//button[@label='Exibir esta observação na Internet']")
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_internet)
            navegador.execute_script("arguments[0].click();", botao_internet)
        except: pass

        try:
            caixa_obs = navegador.find_element(By.XPATH, "//textarea[contains(@class, 'form-control')]")
            caixa_obs.clear(); caixa_obs.send_keys(texto_ocorrencia)
        except: pass

        try:
            botao_executar = navegador.find_element(By.XPATH, "//button[contains(text(), 'Executar')]")
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_executar); time.sleep(1)
            navegador.execute_script("arguments[0].click();", botao_executar)
            try: wait.until(EC.alert_is_present()).accept()
            except: pass
        except: pass

    except Exception as e:
        raise Exception(f"Erro nas Ocorrências: {e}")
    finally:
        try: navegador.switch_to.default_content()
        except: pass

def lancar_faltas(navegador, wait, aula, etapa_atual):
    if aula['tipo_lancamento'] != "Pendente_Nova": return
    
    curso = aula['curso_ativo']
    serie_busca = aula['serie_ativo']
    turma_exata = aula['turma_ativa']
    disciplina_busca = aula.get('disciplina', '').strip()
    
    if not curso or not serie_busca or not turma_exata: raise Exception("DNA Activesoft ausente. Turma não mapeada corretamente.")
        
    print(f"   [Frequência] Iniciando chamada para {turma_exata}...")
    try:
        try: navegador.switch_to.default_content()
        except: pass
        time.sleep(2)
        
        try:
            botao_freq = wait.until(EC.element_to_be_clickable((By.ID, "frequencia_em_lote")))
            navegador.execute_script("arguments[0].click();", botao_freq)
        except: navegador.get("https://siga02.activesoft.com.br/diarios/frequencia_em_lote/")
        time.sleep(5)
        
        def preencher_select_blindado(idx, texto):
            if not texto: return
            try:
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
                        
                if idx >= len(inps): return
                inp = inps[idx]
                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp); time.sleep(1)
                
                try: navegador.execute_script("arguments[0].parentNode.parentNode.click();", inp)
                except: pass
                time.sleep(1)
                
                navegador.execute_script("arguments[0].focus();", inp)
                try:
                    inp.send_keys(Keys.CONTROL + "a"); inp.send_keys(Keys.BACKSPACE); inp.send_keys(texto); time.sleep(1.5)
                except:
                    navegador.execute_script(JS_REACT_SETTER, inp, texto); time.sleep(2)
                
                opcoes = navegador.find_elements(By.XPATH, f"//div[contains(text(), '{texto}')] | //li[contains(text(), '{texto}')]")
                if opcoes:
                    clicou_exato = False
                    for opcao in opcoes:
                        if texto.upper() == opcao.text.strip().upper():
                            navegador.execute_script("arguments[0].click();", opcao)
                            clicou_exato = True; break
                    if not clicou_exato: navegador.execute_script("arguments[0].click();", opcoes[-1])
                else:
                    try: inp.send_keys(Keys.ARROW_DOWN); time.sleep(0.5); inp.send_keys(Keys.ENTER)
                    except:
                        navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'ArrowDown'}));", inp)
                        time.sleep(0.5); navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", inp)
                time.sleep(2.5) 
            except Exception as e: print(f"   [Frequência] ⚠️ Falha ao preencher filtro {idx}: {e}")

        # 🔥 A CORREÇÃO DE LÓGICA: Contagem Dinâmica de Caixas 🔥
        inps_tela = navegador.find_elements(By.XPATH, "//input[contains(@id, 'react-select') or @aria-autocomplete='list']")
        qtd_caixas = len(inps_tela)
        
        preencher_select_blindado(1, curso)        
        preencher_select_blindado(2, serie_busca)       
        preencher_select_blindado(3, turma_exata)
        
        if qtd_caixas >= 6:
            if disciplina_busca: preencher_select_blindado(4, disciplina_busca)
            preencher_select_blindado(5, etapa_atual)
        elif qtd_caixas == 5:
            preencher_select_blindado(4, etapa_atual)
        else:
            preencher_select_blindado(qtd_caixas - 1, etapa_atual)
        
        try:
            inps_data = navegador.find_elements(By.XPATH, "//input[contains(@class, 'Datepicker') or contains(@class, 'DatePicker') or @placeholder='DD/MM/AAAA']")
            if inps_data:
                for input_dt in inps_data[:2]:
                    navegador.execute_script(JS_REACT_SETTER, input_dt, aula['data'])
                    time.sleep(0.5)
                    try: input_dt.send_keys(Keys.ENTER); time.sleep(0.2); input_dt.send_keys(Keys.ESCAPE)
                    except: pass
            else: raise Exception("Campos de data não encontrados.")
        except Exception as e: raise Exception(f"Erro ao preencher a data: {e}")

        try:
            botao_consultar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Consultar']")))
            navegador.execute_script("arguments[0].click();", botao_consultar)
            
            print("   [Frequência] Aguardando lista de alunos carregar...")
            time.sleep(6) 
            check_swal_alert(navegador, "Frequência")
            
        except Exception as e:
            if "Bloqueio do Site" in str(e): raise e
            raise Exception("O botão 'Consultar' estava bloqueado.")
        
        def clicar_opcao_tabela(botao_alvo, texto_opcao):
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_alvo); time.sleep(0.5)
            try: botao_alvo.click() 
            except: navegador.execute_script("arguments[0].click();", botao_alvo) 
            time.sleep(1) 
            
            xpath = f"//*[normalize-space(text())='{texto_opcao}']"
            opcoes = navegador.find_elements(By.XPATH, xpath)
            for op in reversed(opcoes):
                if op.is_displayed(): 
                    try: op.click(); return
                    except:
                        try: webdriver.ActionChains(navegador).move_to_element(op).click().perform(); return
                        except: navegador.execute_script("arguments[0].click();", op); return
            if opcoes: navegador.execute_script("arguments[0].click();", opcoes[-1])

        try:
            botao_mestre = wait.until(EC.presence_of_element_located((By.XPATH, "(//button[contains(@class, 'Toggle__ToggleButton')])[1]")))
            clicar_opcao_tabela(botao_mestre, "Presente")
            time.sleep(3) 
        except:
            check_swal_alert(navegador, "Frequência")
            raise Exception("A tabela do Activesoft veio vazia após consultar. A data ou etapa estão corretas no sistema da escola?")
            
        faltas_str = str(aula.get('faltas', '')).strip()
        mapa_alunos = aula.get('mapa_alunos', {})
        
        if faltas_str:
            numeros_falta = [n.strip() for n in faltas_str.split(',')]
            for num in numeros_falta:
                try:
                    nome_aluno = mapa_alunos.get(num, "")
                    linha_alvo = None
                    
                    if nome_aluno:
                        partes = nome_aluno.upper().split()
                        primeiro_nome = partes[0]
                        ultimo_nome = partes[-1] if len(partes) > 1 else partes[0]
                        xpath_nome = f"//tr[contains(translate(., 'abcdefghijklmnopqrstuvwxyzáéíóúâêôãõç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÂÊÔÃÕÇ'), '{primeiro_nome}') and contains(translate(., 'abcdefghijklmnopqrstuvwxyzáéíóúâêôãõç', 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÂÊÔÃÕÇ'), '{ultimo_nome}')]"
                        linhas = navegador.find_elements(By.XPATH, xpath_nome)
                        if linhas:
                            linha_alvo = linhas[0]
                            
                    if not linha_alvo:
                        indice_linha = int(num) + 1 
                        xpath_linha_indice = f"(//tbody/tr)[{indice_linha}]"
                        linha_alvo = navegador.find_element(By.XPATH, xpath_linha_indice)
                        
                    botao_status = linha_alvo.find_element(By.XPATH, ".//button[contains(@class, 'Toggle__ToggleButton')]")
                    clicar_opcao_tabela(botao_status, "Falta"); time.sleep(1)
                except Exception as erro_falta:
                    print(f"   [Frequência] ⚠️ Falha ao marcar falta para o aluno nº {num}: {erro_falta}")
        
        try:
            botao_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Salvar']")))
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_salvar); time.sleep(1)
            navegador.execute_script("arguments[0].click();", botao_salvar); time.sleep(3)
            
            try: wait.until(EC.alert_is_present()).accept()
            except: pass
                
            try:
                botao_sim = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'swal2-confirm')]")))
                navegador.execute_script("arguments[0].click();", botao_sim); time.sleep(3)
            except: pass
        except: raise Exception("Não consegui encontrar ou clicar no botão 'Salvar'.")
            
        check_swal_alert(navegador, "Salvar Frequência")
                
    except Exception as e:
        raise Exception(f"Falha na Frequência: {e}")

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
            try:
                navegador.switch_to.frame(f)
                input_escondido = navegador.find_element(By.XPATH, "//input[contains(@id, 'react-select')]")
                if input_escondido: break
            except: pass
        if input_escondido: break
        time.sleep(1.5)
        
    if not input_escondido: raise Exception("Campo de Etapa sumiu.")
    
    try:
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_escondido); time.sleep(0.5)
        navegador.execute_script("arguments[0].parentNode.parentNode.click();", input_escondido); time.sleep(1.5) 
        
        clicou = False
        opcoes = navegador.find_elements(By.XPATH, f"//div[contains(text(), '{nota_info['etapa']}')] | //li[contains(text(), '{nota_info['etapa']}')] | //span[contains(text(), '{nota_info['etapa']}')]")
        
        if opcoes: 
            for op in reversed(opcoes):
                if op.is_displayed():
                    try:
                        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", op); time.sleep(0.5)
                        try: op.click()
                        except: webdriver.ActionChains(navegador).move_to_element(op).click().perform()
                        clicou = True; break
                    except: pass
                
        if not clicou:
            navegador.execute_script("arguments[0].focus();", input_escondido)
            try: input_escondido.send_keys(nota_info['etapa'])
            except: pass
            time.sleep(1.5)
            try: input_escondido.send_keys(Keys.ARROW_DOWN); time.sleep(0.5); input_escondido.send_keys(Keys.ENTER)
            except:
                navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'ArrowDown'}));", input_escondido)
                time.sleep(0.5); navegador.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));", input_escondido)
                
        time.sleep(1.5)
        
        btn_consultar = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Consultar')]")))
        navegador.execute_script("arguments[0].click();", btn_consultar); time.sleep(3) 

        btn_inserir = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Inserir avaliação')] | //*[name()='svg' and contains(@class, 'FaseNota')]")))
        navegador.execute_script("arguments[0].click();", btn_inserir); time.sleep(1.5)

        btn_nova = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Nova avaliação')]")))
        navegador.execute_script("arguments[0].click();", btn_nova); time.sleep(1.5) 
        
        input_nome = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Input-sg8yoa-0') and not(@readonly)]")))
        navegador.execute_script(JS_REACT_SETTER, input_nome, nota_info['nome_prova']); time.sleep(0.5)
        
        input_data = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'Datepicker')]")))
        navegador.execute_script(JS_REACT_SETTER, input_data, nota_info['data_prova']); time.sleep(0.5)
        try: input_data.send_keys(Keys.ENTER); time.sleep(0.5); input_data.send_keys(Keys.ESCAPE)
        except: pass
        
        input_valor = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'InputDecimal')]")))
        navegador.execute_script(JS_REACT_SETTER, input_valor, nota_info['valor_prova']); time.sleep(0.5)
        
        btn_salvar = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Salvar')]")))
        navegador.execute_script("arguments[0].click();", btn_salvar)
        
        btn_fechar = WebDriverWait(navegador, 10).until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'swal2-confirm') or text()='Fechar']")))
        navegador.execute_script("arguments[0].click();", btn_fechar); time.sleep(3)
        
        cabecalhos_provas = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'TextClick')]")))
        
        indice_coluna_alvo = -1
        for i, cabecalho in enumerate(cabecalhos_provas):
            if cabecalho.text.strip() == nota_info['nome_prova']:
                indice_coluna_alvo = i; break
                
        if indice_coluna_alvo == -1: indice_coluna_alvo = len(cabecalhos_provas) - 1 
        
        for num_aluno, nota in nota_info['notas_alunos'].items():
            try:
                linha_aluno = wait.until(EC.presence_of_element_located((By.XPATH, f"//td[text()='{num_aluno}']/ancestor::tr")))
                todas_as_caixas = linha_aluno.find_elements(By.XPATH, ".//input[contains(@class, 'InputNotaStyled')]")
                
                if len(todas_as_caixas) > indice_coluna_alvo:
                    input_nota_certo = todas_as_caixas[indice_coluna_alvo]
                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_nota_certo); time.sleep(0.2)
                    
                    if str(nota).strip() in ["0", "0.0", "0,0"]:
                        try: input_nota_certo.click(); input_nota_certo.send_keys(Keys.BACKSPACE); input_nota_certo.send_keys("0,0") 
                        except: navegador.execute_script(JS_REACT_SETTER, input_nota_certo, "0,0")
                    else: navegador.execute_script(JS_REACT_SETTER, input_nota_certo, nota)
                        
                    time.sleep(0.2); input_nota_certo.send_keys(Keys.TAB); time.sleep(0.5)
            except: pass
    except Exception as e: raise e

# ================= MOTOR CENTRAL =================
def vigiar():
    print("="*60)
    print(" 🚀 VIGIA ASSESSOR.IA: V46.2 (CONTAGEM DINÂMICA DE FILTROS)")
    print("="*60)
    
    try:
        planilha = conectar_sheets()
        usuarios_cadastrados = {}
        
        try:
            dados_usuarios = safe_get_values(planilha.worksheet("Usuarios"))
            for row in dados_usuarios[1:]:
                if len(row) >= 7 and str(row[0]).strip():
                    usuarios_cadastrados[str(row[0]).strip()] = {
                        "nome": str(row[1]).strip(), 
                        "codigo": str(row[3]).strip(),
                        "login": str(row[4]).strip(), 
                        "senha": str(row[5]).strip(),
                        "aba_config": str(row[6]).strip()
                    }
        except Exception as e:
            print(f"⚠️ Erro ao ler a aba Usuarios: {e}")
            return
            
        aulas_por_prof = {}
        notas_por_prof = {}
        
        abas_registros = [aba for aba in planilha.worksheets() if aba.title.startswith("registros_")]
        for aba in abas_registros:
            turma_nome = aba.title.replace("registros_", "")
            dados_brutos = safe_get_values(aba)
            
            if len(dados_brutos) < 2: continue
                
            nome_aba_alunos = aba.title.replace("registros_", "alunos_")
            mapa_alunos_turma = {}
            try:
                dados_alunos = safe_get_values(planilha.worksheet(nome_aba_alunos))
                for r in dados_alunos[1:]:
                    if len(r) >= 2 and str(r[0]).strip():
                        mapa_alunos_turma[str(r[0]).strip()] = str(r[1]).strip()
            except: pass
            
            try:
                cabecalhos_reg = [str(c).strip().upper() for c in dados_brutos[0]]
                idx_curso = cabecalhos_reg.index("CURSO_ACTIVESOFT")
                idx_serie = cabecalhos_reg.index("SERIE_ACTIVESOFT")
                idx_turma = cabecalhos_reg.index("TURMA_ACTIVESOFT")
                curso_ativo = str(dados_brutos[1][idx_curso]).strip()
                serie_ativo = str(dados_brutos[1][idx_serie]).strip()
                turma_ativa = str(dados_brutos[1][idx_turma]).strip()
            except:
                curso_ativo, serie_ativo, turma_ativa = "", "", ""
            
            col_diario, col_ocorrencia, col_falta, col_id_prof, col_disciplina = -1, -1, -1, -1, -1
            for i, c in enumerate(cabecalhos_reg):
                if "DIARIO" in c or "DIÁRIO" in c or c == "STATUS": col_diario = i
                if "OCORRENCIA" in c or "OCORRÊNCIA" in c: col_ocorrencia = i
                if "FALTA" in c: col_falta = i
                if "ID_PROFESSOR" in c: col_id_prof = i
                if "DISCIPLINA" in c: col_disciplina = i
            
            if col_id_prof == -1: continue 
            
            for indice, row in enumerate(dados_brutos[1:]):
                linha_sheets = indice + 2 
                while len(row) < max(len(cabecalhos_reg), 15): row.append("") 
                    
                linha_dict = {cabecalhos_reg[i]: row[i] for i in range(min(len(cabecalhos_reg), len(row)))}
                data_aula = str(linha_dict.get("DATA", row[0])).strip()
                if not data_aula: continue
                
                if "/" in data_aula:
                    partes_data = data_aula.split("/")
                    if len(partes_data) == 3:
                        ano_atual = str(datetime.now().year)
                        if partes_data[2] != ano_atual:
                            partes_data[2] = ano_atual
                            data_aula = "/".join(partes_data)
                
                st_diario = str(row[col_diario]).strip() if col_diario != -1 else ""
                st_ocor = str(row[col_ocorrencia]).strip() if col_ocorrencia != -1 else ""
                st_falta = str(row[col_falta]).strip() if col_falta != -1 else ""
                id_prof = str(row[col_id_prof]).strip()
                disciplina_texto = str(row[col_disciplina]).strip() if col_disciplina != -1 else ""
                
                if id_prof and ("Pendente" in st_diario or "Pendente" in st_ocor or "Pendente" in st_falta):
                    if "Processando" in st_diario or "Processando" in st_ocor or "Processando" in st_falta: continue
                        
                    if id_prof not in aulas_por_prof: aulas_por_prof[id_prof] = []
                    aulas_por_prof[id_prof].append({
                        "aba": aba, "linha_planilha": linha_sheets, 
                        "col_status_diario": col_diario + 1, "status_diario": st_diario,
                        "col_status_ocorrencia": col_ocorrencia + 1, "status_ocorrencia": st_ocor,
                        "col_status_falta": col_falta + 1, "status_falta": st_falta,
                        "turma": turma_nome, "data": data_aula,
                        "resumo": str(linha_dict.get("RESUMO", "")).strip(), 
                        "para_casa": str(linha_dict.get("PARA CASA", "")).strip(),
                        "nao_fez": str(linha_dict.get("NAO_FEZ", "")).strip(), 
                        "tarefa_nao_feita": str(linha_dict.get("TAREFA_NAO_FEITA", "")).strip(),
                        "faltas": str(linha_dict.get("FALTAS", "")).strip(), 
                        "tipo_lancamento": st_falta, "disciplina": disciplina_texto,
                        "curso_ativo": curso_ativo, "serie_ativo": serie_ativo, "turma_ativa": turma_ativa,
                        "mapa_alunos": mapa_alunos_turma
                    })

        abas_notas = [aba for aba in planilha.worksheets() if aba.title.startswith("Notas_")]
        for aba in abas_notas:
            turma_nome = aba.title.replace("Notas_", "")
            dados = safe_get_values(aba)
            if len(dados) < 7: continue
            
            for col_idx, status in enumerate(dados[2]):
                if str(status).strip() == "Pendente":
                    id_prof = str(dados[1][col_idx]).strip()
                    if not id_prof: continue
                    
                    data_prova_crua = str(dados[3][col_idx]).strip()
                    if "/" in data_prova_crua:
                        partes_data_prova = data_prova_crua.split("/")
                        if len(partes_data_prova) == 3:
                            ano_atual_prova = str(datetime.now().year)
                            if partes_data_prova[2] != ano_atual_prova:
                                partes_data_prova[2] = ano_atual_prova
                                data_prova_crua = "/".join(partes_data_prova)
                    
                    disciplina_prova = str(dados[5][col_idx]).strip()
                    notas_alunos = {str(dados[row_idx][0]).strip(): str(dados[row_idx][col_idx]).strip() for row_idx in range(6, len(dados)) if str(dados[row_idx][0]).strip() and str(dados[row_idx][col_idx]).strip() != ""}
                        
                    if id_prof not in notas_por_prof: notas_por_prof[id_prof] = []
                    notas_por_prof[id_prof].append({
                        "aba": aba, "turma": turma_nome, "coluna_planilha": col_idx + 1,
                        "nome_prova": str(dados[0][col_idx]).strip(), "data_prova": data_prova_crua,
                        "valor_prova": str(dados[4][col_idx]).strip(), "notas_alunos": notas_alunos,
                        "disciplina": disciplina_prova
                    })

        ids_com_pendencias = set(list(aulas_por_prof.keys()) + list(notas_por_prof.keys()))
        if not ids_com_pendencias:
            print(f"🟢 Nenhuma tarefa pendente no Banco Central.")
            return

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        for id_prof in ids_com_pendencias:
            if id_prof not in usuarios_cadastrados: continue
                
            dados_prof = usuarios_cadastrados[id_prof]
            minhas_aulas = aulas_por_prof.get(id_prof, [])
            minhas_notas = notas_por_prof.get(id_prof, [])
            
            print(f"\n👨‍🏫 Iniciando Lote do Professor(a): {dados_prof['nome']} ({len(minhas_aulas)} Aulas | {len(minhas_notas)} Provas)")
            relatorio_telegram = f"🤖 <b>VIGIA - RELATÓRIO DO LOTE</b>\n\n"
            
            etapa_atual = "2ª Etapa"
            try:
                try: val = planilha.worksheet(dados_prof['aba_config']).acell("B1").value
                except: val = ""
                valor_cru = str(val).strip().lower()
                if "rec" in valor_cru and "1" in valor_cru: etapa_atual = "Recup. 1ª Etapa"
                elif "rec" in valor_cru and "2" in valor_cru: etapa_atual = "Recup. 2ª Etapa"
                elif "rec" in valor_cru and "3" in valor_cru: etapa_atual = "Recup. 3ª Etapa"
                elif "1" in valor_cru: etapa_atual = "1ª Etapa"
                elif "2" in valor_cru: etapa_atual = "2ª Etapa"
                elif "3" in valor_cru: etapa_atual = "3ª Etapa"
            except: pass
            
            navegador = webdriver.Chrome(options=chrome_options)
            wait = WebDriverWait(navegador, 10) 
            
            try:
                navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
                wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(dados_prof['codigo'])
                navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(dados_prof['login'])
                navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(dados_prof['senha'])
                navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
                time.sleep(3)
                
                try: WebDriverWait(navegador, 3).until(EC.element_to_be_clickable((By.XPATH, "//img[@alt='Activesoft Logo']"))).click(); time.sleep(2)
                except: pass 
                
                for aula in minhas_aulas:
                    if "Pendente" in aula['status_diario']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_diario'], "Processando...")
                    if "Pendente" in aula['status_ocorrencia']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_ocorrencia'], "Processando...")
                    if "Pendente" in aula['status_falta']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_falta'], "Processando...")

                    print(f"\n -> Iniciando Aula: {aula['turma']} ({aula['data']})")
                    relatorio_telegram += f"🏫 <b>{aula['turma']} ({aula['data']})</b>\n"
                    
                    try:
                        try: navegador.switch_to.default_content()
                        except: pass
                        
                        navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/"); time.sleep(3)
                        try: navegador.switch_to.alert.accept()
                        except: pass

                        achar_e_clicar(navegador, "//button[contains(text(), 'Exibir') or text()='Exibir']", tempo_espera=3); time.sleep(3)

                        turma_busca = MAPA_TURMAS.get(aula['turma_ativa'].upper().strip(), aula['turma_ativa'].upper().strip())
                        disciplina_busca = aula.get('disciplina', '').strip().upper()
                        
                        if disciplina_busca:
                            xpath_diario = f"//*[contains(text(), '{turma_busca}')]/ancestor::tr[contains(translate(., 'áéíóúãõç', 'AEIOUAOC'), '{disciplina_busca}')]//a[contains(text(), 'Diário de classe')] | //*[contains(text(), '{turma_busca}')]/ancestor::div[contains(@class, 'card')][contains(translate(., 'áéíóúãõç', 'AEIOUAOC'), '{disciplina_busca}')]//a[contains(text(), 'Diário de classe')]"
                        else:
                            xpath_diario = f"//*[contains(text(), '{turma_busca}')]/ancestor::tr//a[contains(text(), 'Diário de classe')] | //*[contains(text(), '{turma_busca}')]/ancestor::div[contains(@class, 'card')]//a[contains(text(), 'Diário de classe')]"
                        
                        if not achar_e_clicar(navegador, xpath_diario, tempo_espera=5):
                            raise Exception(f"Turma '{turma_busca}' (Disc: {disciplina_busca}) não foi achada.")
                            
                        time.sleep(5) 
                        
                        if aula['status_diario'] in ["Pendente", "Pendente_Nova"]:
                            try:
                                script_js = f"""
                                var e = '{etapa_atual}'.toUpperCase();
                                var rows = document.querySelectorAll('tr');
                                for (var i = 0; i < rows.length; i++) {{
                                    var text = (rows[i].innerText || rows[i].textContent).toUpperCase();
                                    if (text.includes(e)) {{
                                        if (!e.includes('REC') && text.includes('REC')) continue;
                                        var links = rows[i].querySelectorAll('a');
                                        for (var j = 0; j < links.length; j++) {{
                                            if ((links[j].innerText || links[j].textContent).toUpperCase().includes('REGISTRO')) {{ links[j].click(); return 'SUCESSO'; }}
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
                                    campo_data_nova = wait.until(EC.element_to_be_clickable((By.ID, "DataAulaNovo")))
                                    campo_data_nova.click(); campo_data_nova.send_keys(Keys.CONTROL + "a"); campo_data_nova.send_keys(Keys.BACKSPACE)
                                    campo_data_nova.send_keys(aula['data']); time.sleep(0.5); campo_data_nova.send_keys(Keys.ESCAPE); campo_data_nova.send_keys(Keys.TAB); time.sleep(1)

                                    campo_conteudo = wait.until(EC.element_to_be_clickable((By.NAME, "ConteudoMinistradoNovo")))
                                    campo_conteudo.click(); campo_conteudo.clear(); campo_conteudo.send_keys(aula['resumo']); time.sleep(0.5)
                                    
                                    campo_tarefa = wait.until(EC.element_to_be_clickable((By.NAME, "TarefaNovo")))
                                    campo_tarefa.click(); campo_tarefa.clear(); campo_tarefa.send_keys(aula['para_casa']); time.sleep(1)

                                    botao_gravar_novo = wait.until(EC.element_to_be_clickable((By.ID, "btnGravarNovo")))
                                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_gravar_novo); time.sleep(0.5)
                                    try: botao_gravar_novo.click()
                                    except: navegador.execute_script("arguments[0].click();", botao_gravar_novo)
                                else:
                                    data_busca = aula['data'].strip()[:5]
                                    botoes_editar = navegador.find_elements(By.XPATH, "//a[contains(text(), 'Editar') or contains(@title, 'Editar')] | //button[contains(text(), 'Editar')] | //input[@value='Editar']")
                                    botao_alvo, linha_alvo = None, None
                                    for botao in botoes_editar:
                                        linha = botao.find_element(By.XPATH, "./ancestor::tr[1]")
                                        textos_inputs = " ".join([str(inp.get_attribute("value")) for inp in linha.find_elements(By.TAG_NAME, "input") if inp.get_attribute("value")])
                                        if data_busca in (str(linha.text) + " " + textos_inputs):
                                            botao_alvo, linha_alvo = botao, linha; break
                                            
                                    if not botao_alvo or not linha_alvo: raise Exception(f"Data {aula['data']} não localizada para edição.")
                                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", linha_alvo); time.sleep(1)
                                    navegador.execute_script("arguments[0].click();", botao_alvo); time.sleep(2) 
                                    
                                    caixas_texto = linha_alvo.find_elements(By.TAG_NAME, "textarea")
                                    if len(caixas_texto) >= 2:
                                        caixas_texto[0].click(); caixas_texto[0].clear(); caixas_texto[0].send_keys(aula['resumo']); caixas_texto[0].send_keys(Keys.TAB); time.sleep(1)
                                        caixas_texto[1].click(); caixas_texto[1].clear(); caixas_texto[1].send_keys(aula['para_casa']); caixas_texto[1].send_keys(Keys.TAB); time.sleep(1)
                                    botao_gravar = linha_alvo.find_element(By.XPATH, ".//a[contains(text(), 'Gravar')] | .//button[contains(text(), 'Gravar')] | .//input[@value='Gravar']")
                                    navegador.execute_script("arguments[0].click();", botao_gravar)
                                    
                                time.sleep(3)
                                try: navegador.switch_to.alert.accept(); raise Exception("Alerta nativo de sistema.")
                                except Exception as e_a: 
                                    if "Alerta nativo" in str(e_a): raise e_a
                                
                                check_swal_alert(navegador, "Gravar Diário")
                                
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_diario'], "Lançado")
                                relatorio_telegram += "  ✅ Diário gravado.\n"
                                
                            except Exception as e_diario:
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_diario'], "Erro Sistema")
                                relatorio_telegram += f"  ❌ Erro Diário: {str(e_diario)[:80]}\n"

                        if aula['status_ocorrencia'] in ["Pendente", "Pendente_Nova", "Processando..."]:
                            try:
                                lancar_ocorrencias(navegador, wait, aula)
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_ocorrencia'], "Lançado")
                                relatorio_telegram += "  ✅ Ocorrências gravadas.\n"
                            except Exception as e_ocor:
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_ocorrencia'], "Erro Sistema")
                                relatorio_telegram += f"  ❌ Erro Ocorrências: {str(e_ocor)[:80]}\n"

                        if aula['status_falta'] in ["Pendente", "Pendente_Nova", "Processando..."]:
                            try:
                                lancar_faltas(navegador, wait, aula, etapa_atual)
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_falta'], "Lançado")
                                relatorio_telegram += "  ✅ Faltas gravadas.\n"
                            except Exception as e_falta:
                                safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_falta'], "Erro Sistema")
                                relatorio_telegram += f"  ❌ Erro Faltas: {str(e_falta)[:100]}\n"
                                
                    except Exception as erro_abrir_painel:
                        if "Processando..." in aula['status_diario'] or "Pendente" in aula['status_diario']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_diario'], "Erro Sistema")
                        if "Processando..." in aula['status_ocorrencia'] or "Pendente" in aula['status_ocorrencia']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_ocorrencia'], "Erro Sistema")
                        if "Processando..." in aula['status_falta'] or "Pendente" in aula['status_falta']: safe_update(aula['aba'], aula['linha_planilha'], aula['col_status_falta'], "Erro Sistema")
                        relatorio_telegram += "  🚨 Falha geral ao abrir a turma no painel.\n"

                for nota in minhas_notas:
                    safe_update(nota['aba'], 3, nota['coluna_planilha'], "Processando...")
                    nota['etapa'] = etapa_atual
                    print(f"\n -> Iniciando Notas: {nota['nome_prova']} ({nota['turma']})")
                    relatorio_telegram += f"\n📝 <b>Notas: {nota['nome_prova']} ({nota['turma']})</b>\n"
                    
                    try:
                        try: navegador.switch_to.default_content()
                        except: pass
                        navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/"); time.sleep(3)
                        try: navegador.switch_to.alert.accept()
                        except: pass

                        achar_e_clicar(navegador, "//button[contains(text(), 'Exibir') or text()='Exibir']", tempo_espera=3); time.sleep(3)

                        turma_busca = MAPA_TURMAS.get(nota['turma'].upper().strip(), nota['turma'].upper().strip())
                        disciplina_busca = nota.get('disciplina', '').strip().upper()
                        
                        if disciplina_busca:
                            xpath_notas = f"//*[contains(text(), '{turma_busca}')]/ancestor::tr[contains(translate(., 'áéíóúãõç', 'AEIOUAOC'), '{disciplina_busca}')]//*[contains(text(), 'Digitação de notas')] | //*[contains(text(), '{turma_busca}')]/ancestor::div[contains(@class, 'card')][contains(translate(., 'áéíóúãõç', 'AEIOUAOC'), '{disciplina_busca}')]//*[contains(text(), 'Digitação de notas')]"
                        else:
                            xpath_notas = f"//*[contains(text(), '{turma_busca}')]/ancestor::tr//*[contains(text(), 'Digitação de notas')] | //*[contains(text(), '{turma_busca}')]/ancestor::div[contains(@class, 'card')]//*[contains(text(), 'Digitação de notas')]"
                        
                        if not achar_e_clicar(navegador, xpath_notas, tempo_espera=5):
                            raise Exception(f"Turma '{turma_busca}' não foi achada na tela de notas.")
                            
                        time.sleep(6) 
                        lancar_notas(navegador, wait, nota)
                        
                        safe_update(nota['aba'], 3, nota['coluna_planilha'], "Lançado")
                        relatorio_telegram += "  ✅ Prova lançada com sucesso.\n"
                        
                    except Exception as e_nota:
                        safe_update(nota['aba'], 3, nota['coluna_planilha'], "Erro Sistema")
                        relatorio_telegram += f"  ❌ Erro ao lançar: {str(e_nota)[:80]}\n"

            finally:
                navegador.quit()
                avisar_telegram(id_prof, relatorio_telegram)

    except Exception as erro_geral:
        print(f"⚠️ Erro crítico geral: {erro_geral}")

if __name__ == "__main__":
    vigiar()
