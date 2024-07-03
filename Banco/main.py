import os
from queue import Queue
import threading
from time import time
from flask import Flask, request, redirect, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dataclasses import dataclass
from datetime import date, datetime
import requests

#Rota adicional "/transacoes/receberDadosAtualizados" criada
#Rota adicional "/transacoes/log" criada
#Rota adicional "'/logs'" criada (para mostrar no html javascript)
#rota adicional "ConectarSeletor" criada
#rota CriaTransacao modificada
#classe transacao e seletor modificadas

app = Flask(__name__)

log_queue = Queue()
processing_thread = None

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

@dataclass
class Cliente(db.Model):
    id: int
    nome: str
    senha: int
    qtdMoeda: float

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), unique=False, nullable=False)
    senha = db.Column(db.String(20), unique=False, nullable=False)
    qtdMoeda = db.Column(db.Integer, unique=False, nullable=False)

@dataclass
class Seletor(db.Model):
    id: int
    nome: str
    ip: str
    qtdMoeda: float
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), unique=False, nullable=False)
    ip = db.Column(db.String(15), unique=False, nullable=False)
    qtdMoeda = db.Column(db.Integer, unique=False, nullable=False)

@dataclass
class Transacao(db.Model):
    id: int
    remetente: int
    recebedor: int
    valor: int
    horario : datetime
    status: int
    
    id = db.Column(db.Integer, primary_key=True)
    remetente = db.Column(db.Integer, unique=False, nullable=False)
    recebedor = db.Column(db.Integer, unique=False, nullable=False)
    valor = db.Column(db.Integer, unique=False, nullable=False)
    horario = db.Column(db.DateTime, unique=False, nullable=False)
    status = db.Column(db.Integer, unique=False, nullable=False)
    def to_dict(self):
        return {
            'id': self.id,
            'remetente': self.remetente,
            'recebedor': self.recebedor,
            'valor': self.valor,
            'horario': self.horario.isoformat(),
            'status': self.status
        }

def process_logs():
    while True:
        log = log_queue.get()
        if log is None:
            break
        process_log(log)
        log_queue.task_done()

def process_log(log):
    log_mensagem = log.get('log')
    horario = log.get('horario')
    if os.path.exists("logs.txt"):
        with open("logs.txt", 'r+') as arquivo:
            linhas = arquivo.readlines()
            encontrou_linha_vazia = False
        
            for i, linha in enumerate(linhas):
                if linha.strip() == '':
                    linhas[i] = f"[{horario}]: {log_mensagem}\n"
                    encontrou_linha_vazia = True
                    break
            
            if encontrou_linha_vazia:
                arquivo.seek(0)
                arquivo.writelines(linhas)
            else:
                arquivo.write(f"[{horario}]: {log_mensagem}\n")
    else:
        with open("logs.txt", 'w') as arquivo:
            arquivo.write(f"[{horario}]: {log_mensagem}\n")

with app.app_context():
    db.create_all()

@app.route("/")
def index():
    #return jsonify(['API sem interface do banco!'])
    return render_template('index.html')

@app.route('/cliente', methods = ['GET'])
def ListarCliente():
    if(request.method == 'GET'):
        clientes = Cliente.query.all()
        return jsonify(clientes)  

@app.route('/cliente/<string:nome>/<string:senha>/<int:qtdMoeda>', methods = ['POST'])
def InserirCliente(nome, senha, qtdMoeda):
    if request.method=='POST' and nome != '' and senha != '' and qtdMoeda != '':
        objeto = Cliente(nome=nome, senha=senha, qtdMoeda=qtdMoeda)
        db.session.add(objeto)
        db.session.commit()
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>', methods = ['GET'])
def UmCliente(id):
    if(request.method == 'GET'):
        objeto = Cliente.query.get(id)
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>/<float:qtdMoedas>', methods=["POST"])
def EditarCliente(id, qtdMoedas):
    if request.method=='POST':
        try:
            cliente = Cliente.query.filter_by(id=id).first()
            cliente.qtdMoeda = qtdMoedas
            db.session.commit()
            return jsonify(['Alteração feita com sucesso'])
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)

    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>', methods = ['DELETE'])
def ApagarCliente(id):
    if(request.method == 'DELETE'):
        objeto = Cliente.query.get(id)
        db.session.delete(objeto)
        db.session.commit()

        data={
            "message": "Cliente Deletado com Sucesso"
        }

        return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor', methods = ['GET'])
def ListarSeletor():
    if(request.method == 'GET'):
        produtos = Seletor.query.all()
        return jsonify(produtos)  
    
#"POST /seletor/seletor_default/seletor_container:5001/0
@app.route('/seletor/<string:nome>/<float:qtdMoeda>/<string:ip>', methods = ['POST'])
def InserirSeletor(nome,qtdMoeda , ip):
    if request.method=='POST' and nome != '' and ip != '' and qtdMoeda != '':
        objeto = Seletor(nome=nome, ip=ip,qtdMoeda=qtdMoeda)
        db.session.add(objeto)
        db.session.commit()
        return jsonify({'id':objeto.id})
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>', methods = ['GET'])
def UmSeletor(id):
    if(request.method == 'GET'):
        produto = Seletor.query.get(id)
        return jsonify(produto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>/<string:nome>/<float:qtdMoeda>/<string:ip>', methods=["POST"])
def EditarSeletor(id, nome,qtdMoeda,ip):
    if request.method=='POST':
        try:
            seletor = Seletor.query.filter_by(id=id).first()
            seletor.nome = nome
            seletor.ip = ip
            seletor.qtdMoeda = qtdMoeda
            db.session.commit()
            return jsonify(seletor)
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>/<string:ip>', methods=["POST"])
def ConectarSeletor(id,ip):
    if request.method=='POST':
        try:
            seletor = Seletor.query.filter_by(id=id).first()
            seletor.ip = ip
            db.session.commit()
            return jsonify(seletor)
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>', methods = ['DELETE'])
def ApagarSeletor(id):
    if(request.method == 'DELETE'):
        objeto = Seletor.query.get(id)
        db.session.delete(objeto)
        db.session.commit()

        data={
            "message": "Validador Deletado com Sucesso"
        }

        return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/hora', methods = ['GET'])
def horario():
    if(request.method == 'GET'):
        #objeto = datetime.now()
        objeto = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        return jsonify(objeto)
		
@app.route('/transacoes', methods = ['GET'])
def ListarTransacoes():
    if(request.method == 'GET'):
        transacoes = Transacao.query.all()
        return jsonify(transacoes)
    
    
@app.route('/transacoes/<int:rem>/<int:reb>/<int:valor>', methods = ['POST'])
def CriaTransacao(rem, reb, valor):
    if request.method=='POST':
        objeto = Transacao(remetente=rem, recebedor=reb,valor=valor,status=0,horario=datetime.now())
        db.session.add(objeto)
        db.session.commit()
		
        seletores = Seletor.query.all()
        for seletor in seletores:
            #Implementar a rota /localhost/<ipSeletor>/transacoes
            url = "http://"+ seletor.ip + '/seletor/transacoes'
            
            
            ultima_transacao = Transacao.query.get(objeto.id - 1)
            if ultima_transacao:
                ultima_transacao_hora = ultima_transacao.horario
                ultima_transacao_hora = ultima_transacao_hora.isoformat()  
            else:
                ultima_transacao_hora = ""
            
            data = objeto.to_dict()
            if ultima_transacao_hora != "":
                split_horario = ultima_transacao_hora.split(sep='T')
                horario_normalizado = split_horario[0]+" "+split_horario[1]
                data["horario_ultima_transacao"] = horario_normalizado
            else:
                data["horario_ultima_transacao"] = ultima_transacao_hora
            ##########
            print(data)
            
            # Envia a requisição com o dicionário
            requests.post(url, json=data)

        return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/transacoes/<int:id>', methods = ['GET'])
def UmaTransacao(id):
    if(request.method == 'GET'):
        objeto = Transacao.query.get(id)
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/transacoes/<int:id>/<int:status>', methods=["POST"])
def EditarTransacao(id, status):
    if request.method=='POST':
        try:
            objeto = Transacao.query.filter_by(id=id).first()
            db.session.commit()
            objeto.id = id
            objeto.status = status
            db.session.commit()
            return jsonify(objeto)
        except Exception as e:
            data={
                "message": "transação não atualizada"
            }
            return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])
    
@app.route('/transacoes/receberDadosAtualizados', methods=["POST"]) #ROTA NOVA
def receberDadosAtualizados():
    if request.method=='POST':
        dados = request.json
        print(dados)
        id_remetente = dados.get('id_remetente')
        id_destinatario = dados.get('id_destinatario')
        id_seletor = dados.get('id_seletor')
        quantia_rem = dados.get('quantia_rem')
        quantia_dest = dados.get('quantia_dest')
        quantia_seletor = float(dados.get('quantia_seletor'))
        
        try:
            cliente = Cliente.query.filter_by(id=id_destinatario).first()
            cliente.qtdMoeda = quantia_dest
            db.session.commit()
            
            remetente = Cliente.query.filter_by(id=id_remetente).first()
            remetente.qtdMoeda = quantia_rem
            db.session.commit()
            
            seletor = Seletor.query.filter_by(id=id_seletor).first()
            seletor.qtdMoeda = quantia_seletor
            db.session.commit()
            
            return jsonify(['Alteração feita com sucesso'])
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)

    else:
        return jsonify(['Method Not Allowed'])
    
@app.route('/logs', methods=['GET']) #ROTA NOVA
def get_logs():

    log_file_path = "logs.txt"
    
    if not os.path.exists(log_file_path):
        #Cria o arquivo se ele não existir
        with open(log_file_path, 'w') as arquivo:
            pass  # apenas cria o arquivo vazio

    with open("logs.txt", 'r') as arquivo:
        logs = arquivo.readlines()
    formatted_logs = [log.strip() for log in logs]
    return "\n".join(formatted_logs)


@app.route('/transacoes/log', methods=["POST"]) #ROTA NOVA
def log():
    if request.method=='POST':
            log = request.json
            log_queue.put(log)
            
            return "Recebi um log"
    else:
        return jsonify(['Method Not Allowed'])
    
    
@app.errorhandler(404)
def page_not_found(error):
    if request.path == '/favicon.ico':
        return '', 204
    return render_template('page_not_found.html'), 404

if __name__ == "__main__":
	with app.app_context():
		db.create_all()
  
processing_thread = threading.Thread(target=process_logs)
processing_thread.daemon = True
processing_thread.start()
        
    
app.run(host='0.0.0.0', port=5000)