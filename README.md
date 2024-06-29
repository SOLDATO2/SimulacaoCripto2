# SimulacaoCripto2

## Integrantes
- Felipe Porto Caldeira do Nascimento
- Alexandre Henning Wahl

## Instruções

O projeto possui duas versões nos arquivos disponíveis:
1. **Versão para Docker**
2. **Versão sem Docker**

### Utilização sem Docker

Para utilizar o projeto fora de um ambiente Docker:

1. Navegue até a pasta `SimulacaoCripto-PreDockerizacao`.
2. Você encontrará os arquivos Python necessários para execução sem Docker, basta iniciar nessa ordem: "main.py" para iniciar o banco, "seletor.py" para iniciar o seletor (ao iniciar, digite um nome qualquer para o seletor) e por fim "validador.py" para iniciar validadores (caso o validador esteja sendo cadastrado, digite o id, caso o contrario não digite nada e insira o saldo.

### Utilização com Docker

Para utilizar o projeto em um ambiente Docker:

1. Navegue até a pasta `SimulacaoCripto2`.
2. Inicie o script PowerShell `ativadorPS.ps1`. Esse script irá montar as imagens e iniciar todos os containers necessários automaticamente.

#### Atenção

1. Caso você encontre o erro "Execução de scripts foi desabilitada neste sistema" ao executar o script, isso significa que seu sistema não está habilitado para execução de scripts PowerShell. Por favor, habilite a execução de scripts PowerShell.
2. Após as imagens serem criadas, algumas abas do cmd serão abertas. Essas abas representam os terminais dos validadores que são iniciados automaticamente para cadastro.
3. São necessários no mínimo 3 validadores cadastrados no seletor para validar uma transação
