from time import perf_counter, sleep
from flask import Flask,jsonify, make_response,request
from datetime import time,datetime
import requests as rq
import uuid
import threading

app = Flask(__name__)
relogio_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
validadores_cadastrados = []

class Seletor():
    nome:str
    ip:str
    def __init__(self,nome,ip):
        self.nome=nome
        self.ip=ip

class Validador():
    id:str
    saldo:str
    ip:str
    token:str
    vezes_expulso:int
    qnt_flag:int
    vezes_escolhido:int
    em_hold:bool
    def __init__(self,id,saldo,ip,token):
        self.id = id
        self.saldo = saldo
        self.ip = ip
        self.token = token
        self.vezes_expulso = 0
        self.qnt_flag = 0

    def escolhidoCincoVezes(self):
        if self.vezes_escolhido==5 or self.em_hold:
            self.em_hold=True
            return True
        else:
            self.vezes_escolhido+=1
            return False

    def contatadorHold(self):
        if self.em_hold:
            self.vezes_escolhido-=1
        if self.vezes_escolhido==0:
            self.em_hold=False

    def zerarContador(self):
        if self.em_hold == False:
            self.vezes_escolhido=0
        
    #"saldo": saldo,
    #"flag": 0,
    #"transacoesCoerentes": 0,
    #"vezes_escolhido_seguido": 0, 
    #"emHold": 0, 
    #"quantasVezesExpulso": 0,


def cadastrar_seletor_banco(seletor_atual):
    while True: 
        try:
            response = rq.post(f"http://127.0.0.1:5000/seletor/{seletor_atual.nome}/{seletor_atual.ip}")
            if response.status_code == 200:
                print(f"Seletor cadastrado no banco")
                break
        except rq.exceptions.RequestException as e:
            print(f"Erro ao se cadastrar Seletor no banco: {e}")

with app.app_context():
    
    response = rq.get("http://127.0.0.1:5000/hora")
    relogio_atual = response.json()
    print(relogio_atual)
    #################
    #2024-06-11 00:19:45.906937
    ################
    nome = input("Digite o seu nome para cadastrar no banco: ")
    ip = f"127.0.0.1:{5001}"
    seletor_atual = Seletor(nome=nome, ip=ip)
    cadastrar_seletor_banco(seletor_atual)


def enviarRelogio(validador_atual):
    tempo_1 = perf_counter()
    response = rq.post(f"http://{validador_atual.ip}/validador/receberRelogio",json={'relogio': relogio_atual})
    if response.status_code == 200:
        tempo_2 = perf_counter()
        atraso_resposta = tempo_2 - tempo_1
        print(tempo_1)
        print(tempo_2)
        print(atraso_resposta)
        response = rq.post(f"http://{validador_atual.ip}/validador/receberAtraso",json={'atraso': atraso_resposta})
    

    
    

@app.route('/seletor/cadastrarValidador', methods=["POST"])
def cadastrarValidador():
    dados_receber = request.json
    id = dados_receber.get('id')
    saldo = dados_receber.get('saldo')
    ip = dados_receber.get('ip')

    if id == "":
        if saldo < 50:
            resposta = make_response("Saldo insuficiente")
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
        else:
            #criando o objeto validador
            id  = len(validadores_cadastrados) + 1
            if len(validadores_cadastrados) > 0:
                token_igual = False
                while token_igual:
                    token = str(uuid.uuid1())
                    for validador in validadores_cadastrados:
                        if validador.token == token:
                            token_igual = True
                print(token)
            else:
                token = str(uuid.uuid1())
            validador = Validador(id=id, saldo=saldo, ip=ip, token=token)
            validadores_cadastrados.append(validador)
    else:
        #verifica se validador existe no banco, caso contrario, avisar validador que id nao existe no banco
        pass

    validador = validadores_cadastrados[0]
    thread_test = threading.Thread(target=enviarRelogio, args=(validador,))
    thread_test.start()
    #enviarRelogio(validadores_cadastrados[0])
    return "Done"


if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5001)