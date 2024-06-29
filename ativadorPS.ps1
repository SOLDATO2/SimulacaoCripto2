$answer = Read-Host "Voce quer gerar as imagens Docker? (s/n)"

if ($answer -eq "s") {
    docker build -t main_banco -f Banco\dockerfile .
    docker build -t seletor -f Seletor\dockerfile .
    docker build -t validador -f Validador\dockerfile .
}

docker network create minha_rede
docker run -d --name main_banco_container --network minha_rede -p 5000:5000 main_banco
docker run -d --name seletor_container --network minha_rede -p 5001:5001 seletor

for ($i = 1; $i -le 6; $i++) {
    $port = 5001 + $i
    $name = "validador_container$i"
    Start-Process cmd.exe "/c docker run --name $name --network minha_rede -it -e NOME_VALIDADOR=$name -e PORTA_VALIDADOR=$port -p ${port}:${port} validador"
}


