from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from queue import Queue
from time import sleep, time
from flask import Flask,jsonify, make_response,request
from datetime import datetime,timedelta
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
#ids_validadores_selecionados = []
validadores_escolhidos = []

#################### Estrutura de dados do Seletor ############################

class Seletor():
    id:int
    nome:str
    ip:str
    qtdMoeda:float
    def __init__(self,nome,ip):
        self.id = 0
        self.nome=nome
        self.ip=ip
        self.qtdMoeda = 0.0

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
    tempo_1_start = time()
    
    print("Job recebido")
    validadores_validos = []
    # Request para obter o saldo do cliente
    tentativas = 0 
    while True: # Tolerancia a falha, caso o servidor nao responda, a job sai da fila 
        try:
            response = rq.get(f"http://main_banco_container:5000/cliente/{job['remetente']}")
            cliente_data = response.json()
            saldo_cliente = cliente_data.get("qtdMoeda")
            job["saldo"] = saldo_cliente
            break 
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
    
    if len(validadores_validos) < 3:#Verifica se existem validadores suficientes na fila. se nao existir, inicia um contador e verifica a cada segundo se tem mais validadores
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
            tempo_1_stop = time()
            relogio_atual += timedelta(seconds=tempo_1_stop-tempo_1_start)
            enviar_log_banco("Não foi possivel concluir a transacao pois o tempo de espera expirou.", relogio_atual)
            return

    
    verificar_fila(validadores_validos)#funcao que coleta min 3 validadores e max 6 da fila
    tempo_1_stop = time()
    relogio_atual += timedelta(seconds=tempo_1_stop-tempo_1_start)
    enviar_log_banco(f"Validadores coletados da Fila de espera: {[validador.id for validador in validadores_que_sairam_da_fila]}", relogio_atual)
    
    tempo_2_start = time()
    if sincronismo_relogios(validadores_que_sairam_da_fila) == False: #sincroniza os validadores coletados utilizando o relogio do banco com relogio de christian
        tempo_2_stop = time()                                 #se a funcao retornar False, significa que ou um contato com o banco falhou-
        relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)#ou um validador perdeu a conexão durante o sincronismo e não existem mais validadores suficientes-
        enviar_log_banco(f"Não existem validadores suficientes para continuar com a eleição.", relogio_atual)#para continuar com a validação
        return
    else:
        tempo_2_stop = time()
        relogio_atual += timedelta(seconds=tempo_2_stop-tempo_2_start)
        enviar_log_banco(f"Validadores sincronizados.", relogio_atual)
    
    tempo_3_start = time()
    validadores_escolhidos = selecionar_validadores(validadores_que_sairam_da_fila) # retorna lista de ids dos validadores escolhidos
    tempo_3_stop = time()
    relogio_atual += timedelta(seconds=tempo_3_stop-tempo_3_start)
    tempo_4_start = time()
    enviar_log_banco(f"Validadores escolhidos para validar o trabalho: {validadores_escolhidos}.", relogio_atual)
    
    colocar_na_fila(validadores_que_sairam_da_fila,validadores_escolhidos)#coloca validadores que não foram escolhidos de volta na fila
    tempo_4_stop = time()
    relogio_atual += timedelta(seconds=tempo_4_stop-tempo_4_start)
    
    tempo_5_start = time()
    lista_consenso = enviar_job_validador(validadores_escolhidos,job, relogio_atual)#envia json job para os validadores
    tempo_5_stop = time()
    relogio_atual += timedelta(seconds=tempo_5_stop-tempo_5_start)
    enviar_log_banco(f"Trabalho enviado para os validadores.", relogio_atual)
    
    tempo_6_start = time()
    status_aprovacao =validar_consenso(lista_consenso)#conta quantos sucesso, falhas e invalidos existem e retorna 1(sucesso),2(falha),0(Invalido) baseado na maioria
    tempo_6_stop = time()
    relogio_atual += timedelta(seconds=tempo_6_stop-tempo_6_start)
    enviar_log_banco(f"Consenso geral dos validadores: {status_aprovacao}.", relogio_atual)
        
    #limpa lista para proxima transacao
    validadores_que_sairam_da_fila.clear()
    tentativas=0
    while True:
        try:
            response = rq.post(f"http://main_banco_container:5000/transacoes/{job['id']}/{status_aprovacao}")
            print("Modificação de transação enviada banco")
            break
        except:
            tentativas+=1
            print(f"Erro ao tentar enviar o status da translação para o banco. Timeout em {tentativas}/3")
            if tentativas>=3:
                print("Erro ao enviar o status da translação para o banco.")
                return#se nao for possivel atualizar o banco, job retorna 0
            sleep(2)

    if status_aprovacao == 1: #Se for aprovado, seletor e validadores sao pagos
        taxas = job["valor"] * 0.015
        quantia_rem = job["saldo"] - (taxas + job["valor"])
        tentativas = 0
        while True:
            try:
                response = rq.get(f"http://main_banco_container:5000/cliente/{job['recebedor']}")
                cliente_data = response.json()
                quantia_dest = cliente_data.get("qtdMoeda")
                break
            except:
                tentativas+=1
                print(f"Erro ao tentar enviar o status da transação para o banco. Timeout em {tentativas}/3")
                if tentativas>=3:#se nao for possivel mandar os dados, validadores marcados para expulsao sao expulsos mesmo que a transacao tenha dado erro
                    print("Erro ao enviar o status da transação para o banco.")
                    for validador in validadores_escolhidos:
                        if (validador.foi_expulso_ultima_vez == False):#Se for True, significa que o validador tomou uma flag e passou do limite, portato está marcado-
                            Fila_de_espera.append(validador)           #para ser expulso e não será adicionado na fila novamente
                        else:
                            try:
                                url = 'http://' + validador.ip + '/validador/avisos'
                                data = {'aviso':'Voce foi expulso por ma conduta.'}
                                response = rq.post(url,json=data)
                            except:
                                print(f"Falha ao avisar ~{validador.id}~ que ele foi expulso...")
                            
                    validadores_offlines.clear()
                    return#se nao for possivel atualizar o banco, job retorna 0
                sleep(2)
                
        #recompensa seletor
        temp = seletor_atual.qtdMoeda # temp para caso o envio da transacao falhe
        seletor_atual.qtdMoeda += job["valor"] * 0.005
        
        quantia_dest =  quantia_dest + (job["valor"])
        dict_resposta_trabalho = { #dict que contem a maioria das informacoes que serao enviadas para atualizacao no banco
            "id_remetente": job['remetente'],
            "id_destinatario": job['recebedor'],
            "id_seletor": seletor_atual.id,
            "quantia_rem": quantia_rem,
            "quantia_dest": quantia_dest,
            "quantia_seletor": seletor_atual.qtdMoeda
        }
        tentativas = 0
        while True:
            try:
                response = rq.post(f"http://main_banco_container:5000/transacoes/receberDadosAtualizados", json=dict_resposta_trabalho)
                print("Dados enviados para o banco")
                break
            except:
                tentativas+=1
                print(f"Erro ao tentar enviar dados atualizados remetente/destinatario para o banco. Timeout em {tentativas}/3")
                if tentativas>=3:
                    print("Erro ao enviar o status dados para o banco.")
                    seletor_atual.qtdMoeda = temp
                    return#se nao for possivel atualizar o banco, job retorna 0
                sleep(2)
            
        #recompensas validadores
        
        
        n_validador_expulsos = 0
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez:
                    try:
                        url = 'http://' + validador.ip + '/validador/avisos'
                        data = {'aviso':'Voce foi expulso por ma conduta.'}
                        response = rq.post(url,json=data)
                    except:
                        print(f"Falha ao avisar ~{validador.id}~ que ele foi expulso...")
                    n_validador_expulsos+=1#soma mais 1 nessa variavel para um calculo futuro de distribuição de recompensa

        #decrementa em hold para todos que estao no banco de dados (os que foram escolhidos para essa transacao sao exceção)
        for validador in validadores_cadastrados:
            if validador.id not in validadores_escolhidos: # decrementa o contador em hold apenas dos usuarios que não foram escolhidos
                validador.contatadorHold()

        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez == False: #paga apenas quem n foi expulso
                    if validador.id not in validadores_offlines:#se durante enviar_request() um validador caiu, ele é adicionado a essa lista. Se ele estiver na lista-
                        validador.saldo += job["valor"] * (0.01/(3-(n_validador_expulsos+len(validadores_offlines)))) #desconta da divisao qnt de validadores expulsos e offilines
                        Fila_de_espera.append(validador)        #ele não será adicionado na fila de espera novamente
                    if validador not in ultimos_escolhidos:
                        validador.zerarContador() #se o validador não estiver na lista de validadores escolhidos na ultima transacao, o contador dele é zerado
                        validador.escolhidoCincoVezes()#nessa etapa ele adiciona mais 1 no contador por conta dessa transacao
                    elif not ultimos_escolhidos:
                        validador.escolhidoCincoVezes() #se ultimos_escolhidos estiver vazio iremos simplesmente adicionar mais 1 ao contador dos validadores
                    elif validador in ultimos_escolhidos:
                        validador.escolhidoCincoVezes()#se o validador existir nos ultimos_escolhidos, o contador dele é incrementado, e se for >=5, bool hold dele é ativada
        #limpamos para a proxima transacao
        ultimos_escolhidos.clear()
        validadores_offlines.clear()
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                ultimos_escolhidos.append(validador)#adiciona validadores escolhidos para a proxima transacao
    else:#se a job falhar, punicoes serao aplicadas do mesmo jeito, se necessario
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                if validador.foi_expulso_ultima_vez:
                    try:
                        url = 'http://' + validador.ip + '/validador/avisos'
                        data = {'aviso':'Voce foi expulso por ma conduta.'}
                        response = rq.post(url,json=data)
                    except:
                        print(f"Falha ao avisar ~{validador.id}~ que ele foi expulso...")

        #decrementa em hold para todos que estao no banco de dados (os que foram escolhidos para essa transacao sao exceção)
        for validador in validadores_cadastrados:
            if validador.id not in validadores_escolhidos: # decrementa o contador em hold apenas dos usuarios que não foram escolhidos
                validador.contatadorHold()
        #mesma logica se repete
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

def selecionar_validadores(validadores_fila):
    validadores_disponiveis = validadores_fila.copy()

    #Calcula os pesos com base no saldo e nas flags
    pesos_validadores = []
    for v in validadores_disponiveis:
        if v.flag == 0:
            peso = 1.0  #Sem redução
        elif v.flag == 1:
            peso = 0.5  #Redução de 50%
        else:
            peso = 0.25  #Redução de 75%
        pesos_validadores.append(peso * v.saldo)

    #Limita os pesos a no máximo 20% e redistribui o excesso
    total_pesos = sum(pesos_validadores)
    pesos_validadores = [peso / total_pesos * 100 for peso in pesos_validadores]
    
    #Enquanto algum peso for maior que 20%, redistribui o excesso
    while any(peso > 20 for peso in pesos_validadores):
        #Calcula o excesso de peso acima de 20%
        excess = sum(peso - 20 for peso in pesos_validadores if peso > 20)
        #Limita cada peso ao máximo de 20%
        pesos_validadores = [min(peso, 20) for peso in pesos_validadores]
        #Conta quantos pesos estão abaixo de 20% para redistribuir o excesso
        distribuicao = sum(1 for peso in pesos_validadores if peso < 20)
        if distribuicao > 0:
            #Redistribui o excesso igualmente entre os pesos abaixo de 20%
            redistribute_amount = excess / distribuicao
            pesos_validadores = [peso + redistribute_amount if peso < 20 else peso for peso in pesos_validadores]

    #Escolhe 3 validadores aleatoriamente com base nos pesos
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
    tempo1 = time()
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
                tempo2 = time()
                relogio_atual += timedelta(seconds=tempo2-tempo1)
                enviar_log_banco(f"Não foi possivel enviar trabalho para o validador ~{validador.id}~, definindo status para 0.", relogio_atual)
                validadores_offlines.append(validador.id)
                break
            print(f"Validador ~{validador.id}~ Não responde, timeout em {tentativas}/3")
            sleep(2)
    
    return consenso_dict        


def enviar_job_validador(id_validadores, job, relogio_atual):
    lista_consenso = []
    
    with ThreadPoolExecutor() as executor:#Utiliza threadpool para enviar trabalhos de forma independente um do outro
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
        print(verificacao['id_validador'])
        print(verificacao['status'])
        print(verificacao["token"])
        
        for validador in validadores_cadastrados:
            print(validador.id)
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
                    verificacao['status'] = 0 #se o token do validador não for igual, invalidamos a palavra dele
                    invalido += 1

    print("Sucessos:",sucessos)
    print("Falhas:",falhas)
    print("Invalidos:",invalido)
    #Sistema para seletor identificar validador falho
    if sucessos>falhas:
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id  == verificacao['id_validador']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==1:
                            validador.incrementarTransacao()#incrementa qtd de transacoes coerentes se ele tiver alguma flag
                        elif verificacao['status']==2:
                            validador.incrementarFlag()#incrementa flag e reseta qtd de transacoes coerentes para 0
        print("Job validada com sucesso (sucessos>falhas and sucessos>invalido) ")
        return 1
    elif ((falhas>sucessos) or sucessos==falhas) and falhas !=0: #Não pode existir empate, então se tiver empate a resposta padrão será FALHO
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id  == verificacao['id_validador']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==1:
                            validador.incrementarFlag()#incrementa flag e reseta qtd de transacoes coerentes para 0
                        elif verificacao['status']==2:
                            validador.incrementarTransacao()#incrementa qtd de transacoes coerentes se ele tiver alguma flag
        print("Job NAO validada com sucesso POR CAUSA DE EMPATE ou FALHA")
        return 2
    elif invalido > sucessos and invalido > falhas and sucessos == 0 and falhas == 0:
        print("Job invalidada POR CAUSA DE MUITAS RESPOSTAS INVALIDAS")
        return 0

def verificar_fila(validadores_validos):

    print("Fila de espera validadores possui o minimo de validadores para validar!")
    x = len(validadores_validos)
    max = 0
    while(x > 0 and max < 6):#tira min 3 e max 6 validadores da fila
        validadores_que_sairam_da_fila.append(validadores_validos[0])
        validadores_validos.pop(0)
        x -=1
        max +=1
    print("Validadores que sairam da fila", validadores_que_sairam_da_fila)
    
    #apaga validadores escolhidos da fila de espera
    for validador in validadores_que_sairam_da_fila:
        if validador in Fila_de_espera:
            Fila_de_espera.remove(validador)
    
    #if len(validadores_que_sairam_da_fila) >= 3:
    #    for validador in validadores_que_sairam_da_fila:
            #guarda ids para verificar se o id existe no banco ao receber a resposta da validacao 
    #        ids_validadores_selecionados.append(validador.id)
        
def enviarRelogio(validador_atual,relogio_final):
    tentativas_a = 0
    tempo_3_start = time()
    while True:
        try:
            tempo_1 = time()
            response = rq.post(f"http://{validador_atual.ip}/validador/receberRelogio",json={'relogio': str(relogio_final)}) #enviar relogio para validador 
            if response.status_code == 200:
                tempo_2 = time()
                correcao_cristian = (tempo_2 - tempo_1)/2
                tentativas_b = 0
                while True:
                    try:
                        response = rq.post(f"http://{validador_atual.ip}/validador/receberAtraso",json={'atraso': correcao_cristian})
                        return
                    except:
                        tentativas_b+=1
                        print(f"Erro ao tentar enviar atraso de relogio ao validador ~{validador_atual.id}~. Timeout em {tentativas_b}/3")
                        if tentativas_b >= 3:
                            validadores_que_sairam_da_fila.remove(validador_atual)
                            tempo_3_stop = time()
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
                tempo_3_stop = time()
                relogio_final += timedelta(seconds=tempo_3_stop-tempo_3_start)
                enviar_log_banco(f"Validador {validador_atual.id} foi removido da eleição por perda de conexão", relogio_final)
                print(f"Sincronizo não realizado com validador {validador_atual.id}")
                return False
            sleep(2)

def pegarRelogioBanco():
    tentativas = 0
    while True:
        try:
            tempo_1 = time()
            response = rq.get("http://main_banco_container:5000/hora")
            tempo_2 = time()
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
   
def enviar_log_banco(log, horario):
    #envia logs para banco porem caso o banco nao consiga receber, o programa ira continuar funcionando normalmente
    tentativas = 0
    horario_str = horario.strftime('%Y-%m-%d %H:%M:%S')
    while True:
        try:
            rq.post(f"http://main_banco_container:5000/transacoes/log", json={"log": log, "horario":horario_str})
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
            response = rq.post(f"http://main_banco_container:5000/seletor/{seletor_atual.nome}/{float(seletor_atual.qtdMoeda)}/{seletor_atual.ip}")
            if response.status_code == 200:
                print(f"Seletor cadastrado no banco")
                resposta = response.json()
                seletor_atual.id = int(resposta.get('id'))
                with open("session.txt", 'w') as arquivo:
                    arquivo.write(str(seletor_atual.id))
                break
        except rq.exceptions.RequestException as e:
            sleep(2)
            print(f"Erro ao se cadastrar Seletor no banco... tentando novamente: {e}")


def conectar_seletor_banco(seletor_atual):
    while True: 
        try:
            response = rq.post(f"http://main_banco_container:5000/seletor/{seletor_atual.id}/{seletor_atual.ip}")
            if response.status_code == 200:
                print(f"Seletor cadastrado no banco")
                resposta = response.json()
                seletor_atual.qtdMoeda = float(resposta.get("qtdMoeda"))
                seletor_atual.nome = resposta.get("nome")
                break
        except rq.exceptions.RequestException as e:
            sleep(2)
            print(f"Erro ao se cadastrar Seletor no banco... tentando novamente: {e}")

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
            #criando o objeto validador, garante que nao exista tokens iguais
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
            resposta = make_response(validador.token+" "+str(validador.id)) #envia token e id para o validador
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
    else:#se validador digitou algum id, verificar se existe... e se existir.. verificar se tem flags ou foi banido perma
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
    nome = os.getenv('NOME_SELETOR', 'seletor_default')
    
    ip = f"seletor_container:{5001}"
    seletor_atual = Seletor(nome=nome, ip=ip)
    if os.path.exists("session.txt"):
        with open('session.txt','r') as arquivo:
            seletor_atual.id = int(arquivo.readline())
            conectar_seletor_banco(seletor_atual)
    else:
        cadastrar_seletor_banco(seletor_atual)
    print(f"ID SELETOR ---> {seletor_atual.id}")
    
    pegarRelogioBanco()#sync simbolico, apenas para mostrar que o seletor conseguiu se sincronizar


if __name__ == "__main__":
    
    processing_thread = threading.Thread(target=process_jobs)
    processing_thread.daemon = True
    processing_thread.start()
    
    app.run(host='0.0.0.0', port=5001)