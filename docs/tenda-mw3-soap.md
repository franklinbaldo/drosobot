# Tenda Nova MW3 / Mesh3f: descoberta SOAP para o DrosoBot

## Escopo e resultado (14/11/2026)

Investigação **somente de leitura**, conduzida pelo IFRO na rede local do usuário. Nenhuma configuração dos roteadores ou clientes foi alterada. Os endereços internos, MACs, SSIDs e outros dados de rede doméstica não são publicados neste repositório.

A rede Tenda MW3/Mesh3f anuncia via SSDP/UPnP um Internet Gateway Device (IGD) com descrição XML em `http://GATEWAY_LAN:5500/rootDesc.xml`. Consultamos a descrição de serviços e os documentos SCPD correspondentes, com os métodos abaixo anunciados:

| Serviço | Métodos SOAP declarados no dispositivo |
| --- | --- |
| `Layer3Forwarding:1` | `SetDefaultConnectionService`, `GetDefaultConnectionService` |
| `WANCommonInterfaceConfig:1` | `GetCommonLinkProperties`, `GetTotalBytesSent`, `GetTotalBytesReceived`, `GetTotalPacketsSent`, `GetTotalPacketsReceived` |
| `WANIPConnection:1` | `AddPortMapping`, `GetExternalIPAddress`, `DeletePortMapping`, `SetConnectionType`, `GetConnectionTypeInfo`, `RequestConnection`, `ForceTermination`, `GetStatusInfo`, `GetNATRSIPStatus`, `GetGenericPortMappingEntry`, `GetSpecificPortMappingEntry` |

**Nenhum desses métodos oferece associação de cliente ao nó mesh, RSSI de estação, varredura de rádio, coordenadas, trilateração ou CSI.** UPnP/SOAP é um serviço real e responde, mas não é, nessa configuração, a API de localização desejada.

O método `GetStatusInfo`, que é somente leitura, respondeu a 12 consultas sequenciais HTTP 200. Tempos observados no IFRO: **mediana 6,55 ms**, média 21,41 ms, máximo 186,02 ms (primeira chamada). A conexão estava no estado `Connected`. São medidas de **latência de consulta IGD**, não de frequência de atualização de RSSI, nem de desempenho de posicionamento.

O SSDP não anunciava serviços `WLANConfiguration` ou equivalentes para medições de cliente. A interface de gerenciamento do aplicativo Tenda WiFi parece distinta do serviço IGD: a documentação do MW3 confirma listagem de clientes e informações dos nós pela aplicação, mas **não documenta leitura simultânea de RSSI do mesmo cliente em todos os nós**.

## Implicações experimentais

1. **Associação a nó**: se a interface do aplicativo expuser a qual nó um dispositivo está conectado, isso dá localização **aproximada por região**, não triangulação.
2. **RSSI por nó**: se vários nós registrarem a intensidade de sinal do *mesmo* cliente no mesmo período, podemos testar fingerprinting/multilateração aproximada. Ainda não demonstrado para MW3.
3. **Roaming**: mudanças de nó podem gerar observações discretas de transição entre regiões; não significam coordenadas estáveis.
4. **Privacidade**: coletar só dados do DrosoBot, armazenar MAC/SSID e identificadores brutos somente no IFRO, expor ao modelo apenas identificadores pseudonimizados e medições temporalmente qualificadas.
5. **Proteção**: não enviar SOAP de configuração (`AddPortMapping`, `ForceTermination`, `SetConnectionType` etc.); manter experimentos de leitura isolados do canal de comandos de movimento.

## Próxima investigação (pendente)

- Identificar versão do firmware MW3 e APIs **autenticadas, somente leitura**, usadas pelo aplicativo oficial Tenda WiFi, sem tentar habilitar root, sondar serviços internos inseguros ou alterar configuração.
- Identificar se existe campo estação→nó, RSSI por estação, banda/canal, timestamp e sua cadência real.
- Comparar utilidade de nó associado contra Wi-Fi fingerprinting coletado pelo ESP-Hi e eventual receptor USB fixo no IFRO, com a mesma validação por cômodo e amostras fora de época.
- Sem telemetria do cliente, usar apenas a função documentada de inventário/conectividade; não inventar posição ou triangulação.

## Referências

- [Tenda MW3 datasheet](https://static.tenda.com.cn/tdeweb/download/MW3/MW3_Datasheet.pdf): UPnP, DHCP client list e Wi-Fi roaming.
- [Tenda WiFi App User Guide, MW3](https://www.tenda.cz/sites/Upload/MW3/MW3_UG.pdf): mapa dos nós e listagem de clientes na aplicação.
- [UPnP WANIPConnection service](https://upnp.org/specs/gw/UPnP-gw-WANIPConnection-v2-Service.pdf): semântica de métodos IGD para ligação à Internet e encaminhamento de portas.

## Contrato método por método

Consulte [auditoria dos 18 métodos e ferramenta de descoberta segura](tenda-soap-actions.md). Os nomes foram lidos do SCPD; os parâmetros documentados ainda precisam ser reconferidos com a unidade.
