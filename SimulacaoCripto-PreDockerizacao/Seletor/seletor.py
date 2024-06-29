from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from time import perf_counter, sleep
from flask import Flask,jsonify, make_response,request
from datetime import time,datetime,timedelta
import requests as rq
import uuid
import threading
import random

app = Flask(__name__)
job_queue = Queue()

processing_thread = None

relogio_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
validadores_cadastrados = []
ultimos_escolhidos = []
validadores_offlines = []
Fila_de_espera = []
validadores_que_sairam_da_fila = []
ids_validadores_selecionados = []
validadores_escolhidos = []

#################### Estrutura de dados do Seletor ############################

class Seletor():
    nome:str
    ip:str
    carteira_validador:float
    def __init__(self,nome,ip):
        self.nome=nome
        self.ip=ip
        self.carteira_validador = 0

class Validador():
    id:str
    saldo:str
    ip:str
    token:str
    vezes_expulso:int
    flag:int
    n_transacao:int
    vezes_escolhido:int
    em_hold:bool
    foi_expulso_ultima_vez:bool
    def __init__(self,id,saldo,ip,token,foi_expulso_ultima_vez):
        self.id = id
        self.saldo = saldo
        self.ip = ip
        self.token = token
        self.vezes_expulso = 0
        self.vezes_escolhido = 0
        self.flag = 0 
        self.n_transacao=0
        self.foi_expulso_ultima_vez = foi_expulso_ultima_vez
        self.em_hold = False

    def escolhidoCincoVezes(self):
        if self.vezes_escolhido<5:
            self.vezes_escolhido+=1
        if self.vezes_escolhido>=5 or self.em_hold:
            self.em_hold=True
        
    def contatadorHold(self):
        if self.em_hold:
            self.vezes_escolhido-=1
        if self.vezes_escolhido==0:
            self.em_hold=False
            self.vezes_escolhido=0
    
    def zerarContador(self):
        self.vezes_escolhido=0

    def incrementarFlag(self):
        self.flag+=1
        self.n_transacao=0
        if self.flag > 2:
            self.vezes_expulso += 1
            self.foi_expulso_ultima_vez = True

    def incrementarTransacao(self):
        if(self.flag>0):
            self.n_transacao+=1
            if(self.n_transacao>=10000):
                self.flag-=1
                self.n_transacao=0


#################### Funções do Seletor ############################

# Função para processar jobs da fila
def process_jobs():
    global job_atual
    while True:
        job = job_queue.get()
        if job is None:
            break
        job_atual = job
        process_job(job)
        job_queue.task_done()
            
def process_job(job):
    global relogio_atual
    relogio_atual = pegarRelogioBanco()
    tempo_1_start = perf_counter()
    
    print("Job recebido")
    validadores_validos = []
    # Request para obter o saldo do cliente
    tentativas = 0 
    while True: # Tolerancia a falha, caso o servidor nao responda, a job sai da fila 
        try:
            response = rq.get(f"http://127.0.0.1:5000/cliente/{job['remetente']}")
            cliente_data = response.json()
            saldo_cliente = cliente_data.get("qtdMoeda")
            job["saldo"] = saldo_cliente
            break 
            #else:
                #print("Falha ao obter o saldo do cliente. Código de status:", response.status_code)
        except:
            tentativas+=1
            print(f"Erro ao tentar obter saldo do cliente ao contatar banco. Timeout em {tentativas}/3")
            if tentativas >= 3:
                print("Job anulada/não executada")
                return
            sleep(2)

    for validador in Fila_de_espera:
        if validador.em_hold == False:
            validadores_validos.append(validador)
    
    if len(validadores_validos) < 3:
        print("Não existem validadores suficientes na fila para validar")
        segundos = 0
        while len(validadores_validos) < 3 and segundos != 60:
            for validador in Fila_de_espera:
                #if validador not in validadores_validos:
                if (validador.em_hold == False) and (validador not in validadores_validos):
                    validadores_validos.append(validador)
            sleep(1)
            segundos += 1
            print(f"Segundos restantes: {segundos}")
                    
        if len(validadores_validos) < 3 and segundos == 60:
            print("Tempo esgotado, não foi possível validar a job pois não existem validadores válidos suficientes para validar a job")
            tempo_1_stop = perf_counter()
            relogio_atual += timedelta(seconds=tempo_1_stop-tempo_1_start)
            enviar_log_banco("Não foi possivel concluir a transacao pois o tempo de espera expirou.", relogio_atual)
            return
        
        verificar_fila(validadores_validos)
        tempo_1_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_1_stop-tempo_1_start)
        enviar_log_banco(f"Validadores coletados da Fila de espera: {[validador.id for validador in validadores_que_sairam_da_fila]}", relogio_atual)
        
        tempo_2_start = perf_counter()
        if sincronismo_relogios(validadores_que_sairam_da_fila) == False:
            tempo_2_stop = perf_counter()
            relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)
            enviar_log_banco(f"Não existem validadores suficientes para continuar a validação do trabalho.", relogio_atual)
            return
        else:
            tempo_2_stop = perf_counter()
            relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)
            enviar_log_banco(f"Validadores sincronizados.", relogio_atual)
        
        tempo_3_start = perf_counter()
        validadores_escolhidos = selecionar_validadores(validadores_que_sairam_da_fila) # retorna json dos validadores escolhidos
        tempo_3_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_3_stop-tempo_3_start)
        tempo_4_start = perf_counter()
        enviar_log_banco(f"Validadores escolhidos para validar o trabalho: {validadores_escolhidos}.", relogio_atual)
        
        colocar_na_fila(validadores_que_sairam_da_fila,validadores_escolhidos)
        tempo_4_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_4_stop-tempo_4_start)
        
        tempo_5_start = perf_counter()
        lista_consenso = enviar_job_validador(validadores_escolhidos,job, relogio_atual)
        tempo_5_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_5_stop-tempo_5_start)
        enviar_log_banco(f"Trabalho enviado para os validadores.", relogio_atual)
        
        tempo_6_start = perf_counter()
        status_aprovacao =validar_consenso(lista_consenso)
        tempo_6_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_6_stop-tempo_6_start)
        enviar_log_banco(f"Consenso geral dos validadores: {status_aprovacao}.", relogio_atual)
    else:
        verificar_fila(validadores_validos)
        tempo_1_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_1_stop-tempo_1_start)
        enviar_log_banco(f"Validadores coletados da Fila de espera: {[validador.id for validador in validadores_que_sairam_da_fila]}", relogio_atual)
        
        tempo_2_start = perf_counter()
        if sincronismo_relogios(validadores_que_sairam_da_fila) == False:
            tempo_2_stop = perf_counter()
            relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)
            enviar_log_banco(f"Não existem validadores suficientes para continuar a validação do trabalho.", relogio_atual)
            return
        else:
            tempo_2_stop = perf_counter()
            relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)
            enviar_log_banco(f"Validadores sincronizados.", relogio_atual)
        
        tempo_3_start = perf_counter()
        validadores_escolhidos = selecionar_validadores(validadores_que_sairam_da_fila) # retorna json dos validadores escolhidos
        tempo_3_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_3_stop-tempo_3_start)
        tempo_4_start = perf_counter()
        enviar_log_banco(f"Validadores escolhidos para validar o trabalho: {validadores_escolhidos}.", relogio_atual)
        
        colocar_na_fila(validadores_que_sairam_da_fila,validadores_escolhidos)
        tempo_4_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_4_stop-tempo_4_start)
        
        tempo_5_start = perf_counter()
        lista_consenso = enviar_job_validador(validadores_escolhidos,job, relogio_atual)
        tempo_5_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_5_stop-tempo_5_start)
        enviar_log_banco(f"Trabalho enviado para os validadores.", relogio_atual)
        
        tempo_6_start = perf_counter()
        status_aprovacao =validar_consenso(lista_consenso)
        tempo_6_stop = perf_counter()
        relogio_atual += timedelta(seconds=tempo_6_stop-tempo_6_start)
        enviar_log_banco(f"Consenso geral dos validadores: {status_aprovacao}.", relogio_atual)
        
    #limpa lista para proxima transacao
    validadores_que_sairam_da_fila.clear()
    tentativas=0
    while True:
        try:
            response = rq.post(f"http://127.0.0.1:5000/transacoes/{job['id']}/{status_aprovacao}")
            print("Modificação de transação enviada banco")
            break
        except:
            tentativas+=1
            print(f"Erro ao tentar enviar o status da translação para o banco. Timeout em {tentativas}/3")
            if tentativas>=3:
                print("Erro ao enviar o status da translação para o banco.")
                return
            sleep(2)

    if status_aprovacao == 1:
        taxas = job["valor"] * 0.015
        quantia_rem = job["saldo"] - (taxas + job["valor"])
        
        while True:
            try:
                response = rq.get(f"http://127.0.0.1:5000/cliente/{job['recebedor']}")
                cliente_data = response.json()
                quantia_dest = cliente_data.get("qtdMoeda")
                break
            except:
                tentativas+=1
                print(f"Erro ao tentar enviar o status da translação para o banco. Timeout em {tentativas}/3")
                if tentativas>=3:
                    print("Erro ao enviar o status da translação para o banco.")
                    for validador in validadores_escolhidos:
                        if (validador.foi_expulso_ultima_vez == False):
                            Fila_de_espera.append(validador)
                        else:
                            url = 'http://' + validador.ip + '/validador/avisos'
                            data = {'aviso':'Voce foi expulso por ma conduta.'}
                            response = rq.post(url,json=data)
                            n_validador_expulsos+=1
                            
                    validadores_offlines.clear()
                    return
                sleep(2)
        
        quantia_dest =  quantia_dest + (job["valor"])
        dict_resposta_trabalho = {
            "id_remetente": job['remetente'],
            "id_destinatario": job['recebedor'],
            "quantia_rem": quantia_rem,
            "quantia_dest": quantia_dest
        }
        tentativas = 0
        while True:
            try:
                response = rq.post(f"http://127.0.0.1:5000/transacoes/receberDadosAtualizados", json=dict_resposta_trabalho)
                print("Dados enviados para o banco")
                break
            except:
                tentativas+=1
                print(f"Erro ao tentar enviar dados atualizados remetente/destinatario para o banco. Timeout em {tentativas}/3")
                if tentativas>=3:
                    print("Erro ao enviar o status dados para o banco.")
                    return
                sleep(2)
            
        #recompensas
        seletor_atual.carteira_validador += job["valor"] * 0.005
        
        n_validador_expulsos = 0
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez:
                    url = 'http://' + validador.ip + '/validador/avisos'
                    data = {'aviso':'Voce foi expulso por ma conduta.'}
                    response = rq.post(url,json=data)
                    n_validador_expulsos+=1

        #decrementa em hold para todos que estao no banco de dados (os que foram escolhidos nao tinham q se a excesao?)
        for validador in validadores_cadastrados:
            if validador.id not in validadores_escolhidos: # adicionei essa linha para decrementar o contador em hold apenas dos usuarios que não foram escolhidos
                validador.contatadorHold()

        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez == False: #paga apenas quem n foi expulso
                    validador.saldo += job["valor"] * (0.01/(3-n_validador_expulsos))
                    if validador.id not in validadores_offlines:
                        Fila_de_espera.append(validador)
                    if validador not in ultimos_escolhidos:
                        validador.zerarContador()
                        validador.escolhidoCincoVezes()
                    elif not ultimos_escolhidos:
                        validador.escolhidoCincoVezes() 
                    elif validador in ultimos_escolhidos:
                        validador.escolhidoCincoVezes()

        ultimos_escolhidos.clear()
        validadores_offlines.clear()
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                ultimos_escolhidos.append(validador)
    else:
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez:
                    url = 'http://' + validador.ip + '/validador/avisos'
                    data = {'aviso':'Voce foi expulso por ma conduta.'}
                    response = rq.post(url,json=data)

        #decrementa em hold para todos que estao no banco de dados (os que foram escolhidos nao tinham q se a excesao?)
        for validador in validadores_cadastrados:
            if validador.id not in validadores_escolhidos: # adicionei essa linha para decrementar o contador em hold apenas dos usuarios que não foram escolhidos
                validador.contatadorHold()

        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez == False: #paga apenas quem n foi expulso
                    if validador.id not in validadores_offlines:
                        Fila_de_espera.append(validador)
                    if validador not in ultimos_escolhidos:
                        validador.zerarContador()
                        validador.escolhidoCincoVezes()
                    elif not ultimos_escolhidos:
                        validador.escolhidoCincoVezes() 
                    elif validador in ultimos_escolhidos:
                        validador.escolhidoCincoVezes()

        ultimos_escolhidos.clear()
        validadores_offlines.clear()
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                ultimos_escolhidos.append(validador)
    return "Job validada"
        
        
###########################fim do processo de Jobs#####################################
# 
# 
# 
# 
##################################Funções dos jobs###################################

""" def selecionar_validadores(validadores_fila):
    id_validadores = []
    
    saldo_modificado = []
    for validador in validadores_fila:
        if validador.flag==0:
            id_validadores.append(validador.id)
            saldo_modificado.append(validador.saldo)     
        elif validador.flag==1:
            id_validadores.append(validador.id)
            saldo_modificado.append(validador.saldo*0.5)     
        else:
            id_validadores.append(validador.id)
            saldo_modificado.append(validador.saldo*0.25)     
            
    #maior saldo
    escolhidos = []
    pesos_validadores = [None]*(len(saldo_modificado))
    for n in range(3):
        maior = 0
        for x in range(1,len(saldo_modificado)):
            if saldo_modificado[maior]<saldo_modificado[x]:
                maior = x

        pesos_validadores[maior] = 20.0
        #distribuição comforme saldo
        total_pesos=0
        for x in range(0,len(saldo_modificado)):
            total_pesos+=saldo_modificado[x]
        for x in range(0,len(saldo_modificado)):
            if x != maior:
                pesos_validadores[x] = (saldo_modificado[x]/total_pesos)*(20*len(saldo_modificado))
                if pesos_validadores[x]>=20:
                    pesos_validadores[x]=20

        #Sorteio 3 validadores
        
        escolhido = random.choices(id_validadores,pesos_validadores)[0]
        escolhidos.append(escolhido)
        for x in range(0,len(id_validadores)):
            if id_validadores[x] == escolhido:
                break
        pesos_validadores.pop(x)
        saldo_modificado.pop(x)
        id_validadores.pop(x)

    return escolhidos """
    
    
def selecionar_validadores(validadores_fila):

    validadores_disponiveis = validadores_fila

    # Calcula os pesos com base no saldo e nas flags
    pesos_validadores = []
    for v in validadores_disponiveis:
        if v.flag == 0:
            peso = 1.0  # Sem redução
        elif v.flag == 1:
            peso = 0.5  # Redução de 50%
        else:
            peso = 0.25  # Redução de 75%
        pesos_validadores.append(peso * v.saldo)

    # Limita os pesos a no máximo 20
    total_pesos = sum(pesos_validadores)
    pesos_validadores = [min(peso / total_pesos * 20, 20) for peso in pesos_validadores]

    # Escolhe 3 validadores aleatoriamente com base nos pesos
    escolhidos = set()
    while len(escolhidos) < 3:
        escolhido = random.choices(validadores_disponiveis, weights=pesos_validadores, k=1)[0]
        escolhidos.add(escolhido)
        index = validadores_disponiveis.index(escolhido)
        validadores_disponiveis.pop(index)
        pesos_validadores.pop(index)

    return [v.id for v in escolhidos]

def colocar_na_fila(validadores,ids_escolhidos):
    for validador in validadores:
        if validador.id not in ids_escolhidos:
            Fila_de_espera.append(validador)
            
  
def enviar_request(validador, job, relogio_atual):
    url = f"http://{validador.ip}/validador/validarJob"
    tentativas = 0
    tempo1 = perf_counter()
    consenso_dict = {}
    
    while True:
        try:
            resposta = rq.post(url, json=job)
            resposta = resposta.json()
            consenso_dict = {
                "id_validador": str(resposta.get('id_validador')),
                "token": resposta.get('token'),
                "status": resposta.get('status')
            }
            break
        except:
            tentativas += 1
            if tentativas >= 3:
                consenso_dict = {
                    "id_validador": validador.id,
                    "token": "invalido",
                    "status": 0
                }
                print(f"Validador ~{validador.id}~ Não respondeu as 3 tentativas, invalidando seu status")
                tempo2 = perf_counter()
                relogio_atual += timedelta(seconds=tempo2-tempo1)
                enviar_log_banco(f"Não foi possivel enviar trabalho para o validador ~{validador.id}~, definindo status para 0.", relogio_atual)
                validadores_offlines.append(validador.id)
                break
            print(f"Validador ~{validador.id}~ Não responde, timeout em {tentativas}/3")
            sleep(2)
    
    return consenso_dict        


def enviar_job_validador(id_validadores, job, relogio_atual):
    lista_consenso = []
    
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(enviar_request, validador, job, relogio_atual)
            for validador in validadores_cadastrados
            if validador.id in id_validadores
        ]
        
        for future in as_completed(futures):
            lista_consenso.append(future.result())
    
    return lista_consenso

def validar_consenso(lista_consenso):
    sucessos = 0
    falhas = 0
    invalido = 0
    for verificacao in lista_consenso:
        print(type(verificacao['id_validador']))
        print(verificacao['status'])
        print(verificacao["token"])
        
        for validador in validadores_cadastrados:
            print(type(validador.id))
            print(validador.token)
            if validador.id == verificacao['id_validador']:
                if verificacao["token"] == validador.token:
                    if verificacao['status']==1:
                        sucessos+=1
                    elif verificacao['status']==2:
                        falhas+=1
                    else:
                        invalido +=1
                else:
                    verificacao['status'] = 0
                    invalido += 1

    print("Sucessos:",sucessos)
    print("Falhas:",falhas)
    print("Invalidos:",invalido)
    
    if sucessos>falhas and sucessos>invalido:
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id  == verificacao['id_validador']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==1:
                            validador.incrementarTransacao()
                        elif verificacao['status']==2:
                            validador.incrementarFlag()
        print("Job validada com sucesso (sucessos>falhas and sucessos>invalido) ")
        return 1
    elif (falhas>sucessos and falhas>invalido) or sucessos==falhas:
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id  == verificacao['id_validador']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==1:
                            validador.incrementarFlag()
                        elif verificacao['status']==2:
                            validador.incrementarTransacao()
        print("Job NAO validada com sucesso POR CAUSA DE EMPATE ou FALHA")
        return 2
    elif invalido > sucessos and invalido > falhas and sucessos == 0 and falhas == 0:
        print("Job invalidada POR CAUSA DE MUITAS RESPOSTAS INVALIDAS")
        return 0

def verificar_fila(validadores_validos):

    print("Fila de espera validadores possui o minimo de validadores para validar!")
    x = len(validadores_validos)
    max = 0
    while(x > 0 and max < 6):
        validadores_que_sairam_da_fila.append(validadores_validos[0])
        validadores_validos.pop(0)
        x -=1
        max +=1
    print("Validadores que sairam da fila", validadores_que_sairam_da_fila)
    
    #apaga validadores escolhidos da fila de espera
    for validador in validadores_que_sairam_da_fila:
        if validador in Fila_de_espera:
            Fila_de_espera.remove(validador)
    
    if len(validadores_que_sairam_da_fila) >= 3:
        for validador in validadores_que_sairam_da_fila:
            #guarda ids para verificar se o id existe no banco ao receber a resposta da validacao 
            ids_validadores_selecionados.append(validador.id)
        
def enviarRelogio(validador_atual,relogio_final):
    tentativas_a = 0
    while True:
        try:
            tempo_1 = perf_counter()
            response = rq.post(f"http://{validador_atual.ip}/validador/receberRelogio",json={'relogio': str(relogio_final)}) #enviar relogio para validador 
            if response.status_code == 200:
                tempo_2 = perf_counter()
                correcao_cristian = (tempo_2 - tempo_1)/2
                tentativas_b = 0
                while True:
                    tempo_3_start = perf_counter()
                    try:
                        response = rq.post(f"http://{validador_atual.ip}/validador/receberAtraso",json={'atraso': correcao_cristian})
                        tempo_3_stop = perf_counter()
                        return
                    except:
                        tentativas_b+=1
                        print(f"Erro ao tentar enviar atraso de relogio ao validador ~{validador_atual.id}~. Timeout em {tentativas_b}/3")
                        if tentativas_b >= 3:
                            validadores_que_sairam_da_fila.remove(validador_atual)
                            tempo_3_stop = perf_counter()
                            relogio_final += timedelta(seconds=tempo_3_stop-tempo_3_start)
                            enviar_log_banco(f"Validador {validador_atual.id} foi removido da eleição por perda de conexão", relogio_final)
                            print(f"Sincronizo não realizado com validador {validador_atual.id}")
                            return False
                        sleep(2)       
        except:
            tentativas_a+=1
            print(f"Erro ao tentar enviar relogio ao validador ~{validador_atual.id}~. Timeout em {tentativas_a}/3")
            if tentativas_a >= 3:
        
                validadores_que_sairam_da_fila.remove(validador_atual)
                print(f"Sincronizo não realizado com validador {validador_atual.id}")
                return False
            sleep(2)     

def pegarRelogioBanco():
    tentativas = 0
    while True:
        try:
            tempo_1 = perf_counter()
            response = rq.get("http://127.0.0.1:5000/hora")
            tempo_2 = perf_counter()
            correcao_cristian = (tempo_2 - tempo_1)/2
            relogio = response.json()
            relogio_final = datetime.strptime(relogio, '%Y-%m-%d %H:%M:%S.%f') + timedelta(seconds=correcao_cristian)
            print(relogio_final)
            #################
            #2024-06-11 00:19:45.906937
            ################
            return relogio_final
        except:
            tentativas+=1
            print(f"Erro ao tentar obter relogio do banco. Timeout em {tentativas}/3")
            if tentativas >= 3:
                print("Job anulada/não executada")
                return False
            sleep(2)

def sincronismo_relogios(lista_validadores): 
    lista_validadores
    global relogio_atual #SELETOR

    ###SINCRONIZAR
    relogio_atual = pegarRelogioBanco()
    if relogio_atual != False:
        for validador in lista_validadores:
            enviarRelogio(validador,relogio_atual)
        if len(validadores_que_sairam_da_fila)<3:
            for validador in validadores_que_sairam_da_fila:
                Fila_de_espera.append(validador)
            validadores_que_sairam_da_fila.clear()
            print("Não existem validadores suficientes para continuar a validação do trabalho.")
            return False
    else:
        return False
    ####FIM DA SINCRONIZAÇÃO    
    ##print(f'Rotas coletadas da fila: {len(validadores)}')
    #log = f"Relogios dos seguintes validadores foram sincronizados usando o modelo de c: {lista_validadores}"
    #log = f"IDs foram distribuidos para os seguintes validadores: {lista_validadores}"
    #enviar_log_banco(log)   
def enviar_log_banco(log, horario):
    #envia logs para banco porem caso o banco nao consiga receber, o programa ira continuar funcionando normalmente
    tentativas = 0
    horario_str = horario.strftime('%Y-%m-%d %H:%M:%S')
    while True:
            try:
                rq.post(f"http://127.0.0.1:5000/transacoes/log", json={"log": log, "horario":horario_str})
                print("Log enviado ao banco")
                break
            except rq.exceptions.RequestException as e:
                print(e)
                tentativas+=1
                print(f"Erro ao tentar enviar o status da translação para o banco. Timeout em {tentativas}/3")
                if tentativas>=3:
                    print("Erro ao enviar Log para o banco. Continuando com a transação..")
                    break
                sleep(2)

#############################################################################################
#############################################################################################     
        
def cadastrar_seletor_banco(seletor_atual):
    while True: 
        try:
            response = rq.post(f"http://127.0.0.1:5000/seletor/{seletor_atual.nome}/{seletor_atual.ip}")
            if response.status_code == 200:
                print(f"Seletor cadastrado no banco")
                break
        except rq.exceptions.RequestException as e:
            sleep(2)
            print(f"Erro ao se cadastrar Seletor no banco...tentando novamente: {e}")

#################### Rotas Flask do Seletor ############################    

@app.route('/seletor/cadastrarValidador', methods=["POST"])
def cadastrarValidador():
    dados_receber = request.json
    id = str(dados_receber.get('id'))
    saldo = dados_receber.get('saldo')
    ip = dados_receber.get('ip')

    if id == "":
        if saldo < 50:
            resposta = make_response("Saldo insuficiente")
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
        else:
            #criando o objeto validador
            id  = str(len(validadores_cadastrados) + 1)
            if len(validadores_cadastrados) > 0:
                token_igual = True
                while token_igual:
                    token_igual = False
                    token = str(uuid.uuid1())
                    for validador in validadores_cadastrados:
                        if validador.token == token:
                            token_igual = True
                print(token)
            else:
                token = str(uuid.uuid1())
    
            validador = Validador(id=id, saldo=saldo, ip=ip, token=token, foi_expulso_ultima_vez=False)
            
            validadores_cadastrados.append(validador)
            Fila_de_espera.append(validador)
            resposta = make_response(validador.token+" "+str(validador.id))
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
    else:
        #verifica se validador existe no banco, caso contrario, avisar validador que id nao existe no banco
        validador_existe = False
        #verifica se validador no banco
        for validador in validadores_cadastrados:
            if validador.id == id:
                validador_existe = True
                validador_encontrado = validador
                break
        #se o validador existir no banco e tiver flags, verificar se o saldo que ele digitou compensa pelas vezes que foi expulso  
        #if validador_existe == True and validador_encontrado.vezes_expulso <= 2:
        if validador_existe == True:
            if validador_encontrado.vezes_expulso <= 2 and validador_encontrado.vezes_expulso > 0:
                if validador_encontrado.foi_expulso_ultima_vez == True:       # se foi expulso, verificar se novo saldo
                    if validador_encontrado.vezes_expulso == 1:
                        if (saldo < 100 ):
                            resposta = make_response("Saldo insuficiente")
                            resposta.headers['Content-type'] = 'text/plain'
                            return resposta
                    elif validador_encontrado.vezes_expulso == 2:
                        if (saldo < 200):
                            resposta = make_response("Saldo insuficiente")
                            resposta.headers['Content-type'] = 'text/plain'
                            return resposta        
            elif validador_encontrado.vezes_expulso > 2:
                resposta = make_response("Validador foi banido permamentemente do banco")
                resposta.headers['Content-type'] = 'text/plain'
                return resposta
            #teste se existe outro validador ligado em outra rota
            for validador in Fila_de_espera:
                if validador.id == id:
                    resposta = make_response("Validador ja esta na Fila")
                    resposta.headers['Content-type'] = 'text/plain'
                    return resposta
            #se estiver tudo ok, ele cadastra na fila de espera
            validador_encontrado.ip = ip
            Fila_de_espera.append(validador_encontrado)
            resposta = make_response(validador_encontrado.token+" "+validador_encontrado.id)
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
        else:
            resposta = make_response("Validador nao existe no banco de dados do seletor")
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
    
@app.route('/seletor/transacoes', methods=["POST"])
def transacoes():
    
    job = request.json
    job_queue.put(job)
    
    return "Recebi uma transacao"


with app.app_context():
    nome = input("Digite o seu nome para cadastrar no banco: ")
    
    ip = f"127.0.0.1:{5001}"
    seletor_atual = Seletor(nome=nome, ip=ip)
    cadastrar_seletor_banco(seletor_atual)
    pegarRelogioBanco()


if __name__ == "__main__":
    
    processing_thread = threading.Thread(target=process_jobs)
    processing_thread.daemon = True
    processing_thread.start()
    
    app.run(host='0.0.0.0', port=5001)