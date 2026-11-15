# DrosoBot: experimento de recepção por navegador na Tenda Mesh

## O que foi construído

Este servidor Python 3, **somente de leitura**, distribui a um segundo processo independente uma sequência de eventos DPH1 gerada **previamente por Embree 4** no IFRO. A interface Canvas 2D no navegador reconstrói os pontos de contato (sem receber o mapa das caixas). O controle permite injetar perda artificial de 2 eventos em 17, solicitar o registro integral para recuperação e medir RTT HTTP real navegador↔IFRO.

**Não é simulação de fótons físicos ou localização por tempo de voo do Wi-Fi**: são trajetórias de raios *virtuais* numa sala 3D sintética, projetadas no plano z=1 metro. A escala de tempo é **50 ms por tick lógico**, sem relação com a velocidade eletromagnética da luz. Os eventos DPH1 ainda contêm rótulos `object_id`, portanto o teste é de reconstrução **supervisionada por semântica dos contatos**, não segmentação não supervisionada. A Tenda é somente meio de transporte: o serviço não acessa suas configurações, SOAP, ucloud nem credenciais.

## Endpoints (somente GET)

- `/`: página web do receptor
- `/app.js`, `/style.css`: arquivos estáticos públicos do laboratório
- `/health`: diagnóstico com contagens e **sem identificadores domésticos**
- `/events`: streaming **SSE**, 17 eventos temporizados, ao máximo 4 clientes simultâneos
- `/journal`: replay **binário completo e imutável** dos eventos, máximo 8192 bytes
- `/ping`: resposta HTTP 204 para medir **RTT de aplicação**, não distância

Qualquer rota diferente recebe 404; POST/alterações recebem 405. O servidor valida Host, só aceita bind em 127.0.0.1 ou endereço IPv4 RFC1918 explícito, não expõe rotas arbitrárias do disco, não fornece CORS e usa CSP restrita. O dado de laboratório é inteiramente sintético, não inclui SSID, IPs de clientes, credenciais, posição real, câmeras ou dados MaleCNS. Há limite de threads de streaming, tamanho de journal e quantidade de quadros.

## Procedimento experimental no IFRO

As dependências são **somente Python stdlib** e um arquivo DPH1 criado pelo produtor Embree já testado:

```bash
# Teste loopback, sem acesso de outros equipamentos
python3 -m unittest discover -s experiments/photon_mesh_web -p 'test_*.py' -v
python3 experiments/photon_mesh_web/server.py \
  --journal /CAMINHO_PRIVADO/source_journal.dph1 --host 127.0.0.1 --port 8765
# Abrir http://127.0.0.1:8765 em navegador do próprio IFRO
```

Para o experimento real, com celular na rede Tenda, o servidor precisa ouvir o endereço privado **atual** da interface cabeada do IFRO, configurado explicitamente com `--host`, não `0.0.0.0`. Por padrão ele não inicia em background nem expõe a LAN. A instalação opcional com systemd deve usar usuário sem privilégios, dados sintéticos acessíveis em modo leitura, limites de memória/CPU e sem permissão para comandos de motor. Uma possível porta de teste é 8765, se disponível.

Depois de abrir no celular a URL privada mostrada pelo operador: selecione perda sintética de 2 eventos, clique **Iniciar transmissão**, aguarde 17 mensagens, observe a reconstrução incompleta e clique **Recuperar eventos**. Clique **Medir RTT** para 12 solicitações HTTP independentes; p50/p95 são medidas do **navegador usado**, não valores que o IFRO pode inventar sem uma conexão real do celular.

## Controles e hipóteses

- Controle positivo: todos os eventos recebidos, duas caixas identificadas e limites espaciais recuperados.
- Controle de perda: faltam sequências 7 e 14; pelo menos uma face deixa de ser observada, objetos ficam incompletos.
- Replay: `GET /journal` restitui os eventos faltantes; as caixas voltam a 4 faces e o registro converge ao controle positivo.
- RTT: comparar navegador do celular (Wi-Fi) versus outro computador/cabo em horários diferentes. O valor inclui tráfego, processamento HTTP e navegador; não inferir física do canal nem localização.
- O sistema ainda precisa de **DPH2 sem ID de objeto**, compressão e transdução real de sensores para afirmar reconstrução não supervisionada ou mapeamento da casa.

**Não é um produto público de rede.** O HTTP é simples e não criptografado por se tratar de uma cena sintética sem segredos. Não encaminhar porta para a Internet, não habilitar DMZ/UPnP mapping, não transportar sessões privadas por esse canal. Desligar o serviço de teste quando não for necessário.
