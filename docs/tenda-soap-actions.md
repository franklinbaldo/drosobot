# Tenda MW3: auditoria individual dos métodos SOAP

## Proveniência e estado

Em 14/11/2026, o gateway mesh Tenda respondeu ao UPnP/SSDP. A leitura de `/rootDesc.xml`, `/L3F.xml`, `/WANCfg.xml` e `/WANIPCn.xml` demonstrou **três serviços e 18 métodos**. Um ensaio separado de 12 chamadas `GetStatusInfo` resultou em HTTP 200 em todas, mediana 6,55 ms. **Os nomes foram verificados diretamente no dispositivo; os argumentos abaixo são os esperados pelas especificações UPnP IGD v1 e ainda requerem comparação campo a campo com o SCPD dessa unidade.** Nesta rodada, o SSH do IFRO ficou inacessível, impedindo a nova leitura dos XMLs. Não se afirma que os outros 17 métodos foram invocados ou que devolvem dados reais.

A ferramenta [scripts/tenda_soap_audit.py](../scripts/tenda_soap_audit.py) faz esse confronto diretamente no IFRO: lista serviços, métodos, nomes e tipos de argumentos sem qualquer SOAP mutável. Com opção explícita, sonda apenas consultas de leitura sem parâmetros; omite valores retornados e nunca envia comandos que alterem a WAN.

## Layer3Forwarding:1

| Método anunciado | Entrada esperada | Retorno esperado | Efeito / interesse |
| --- | --- | --- | --- |
| `GetDefaultConnectionService` | Nenhuma | `NewDefaultConnectionService` | **Leitura.** Identifica a conexão WAN padrão; sem informação de rádio. |
| `SetDefaultConnectionService` | `NewDefaultConnectionService` | Nenhum | **Mutação.** Muda a conexão escolhida; nunca executar. |

## WANCommonInterfaceConfig:1

| Método anunciado | Entrada esperada | Retorno esperado | Efeito / interesse |
| --- | --- | --- | --- |
| `GetCommonLinkProperties` | Nenhuma | `NewWANAccessType`, `NewLayer1UpstreamMaxBitRate`, `NewLayer1DownstreamMaxBitRate`, `NewPhysicalLinkStatus` | **Leitura.** Caracteriza o enlace WAN, não o Wi-Fi da LAN. |
| `GetTotalBytesSent` | Nenhuma | `NewTotalBytesSent` | **Leitura.** Contador agregado da WAN. |
| `GetTotalBytesReceived` | Nenhuma | `NewTotalBytesReceived` | **Leitura.** Contador agregado da WAN. |
| `GetTotalPacketsSent` | Nenhuma | `NewTotalPacketsSent` | **Leitura.** Contador agregado da WAN. |
| `GetTotalPacketsReceived` | Nenhuma | `NewTotalPacketsReceived` | **Leitura.** Contador agregado da WAN. |

Os contadores são **da interface WAN**, não de um cliente ou nó mesh. Mesmo que subam quando o DrosoBot transmite dados, não fornecem sua posição nem a potência de recepção do rádio.

## WANIPConnection:1

| Método anunciado | Entradas esperadas | Retornos esperados | Efeito / interesse |
| --- | --- | --- | --- |
| `GetExternalIPAddress` | Nenhuma | `NewExternalIPAddress` | **Leitura.** IP da WAN, não localização interna. Não publicar o valor. |
| `GetConnectionTypeInfo` | Nenhuma | `NewConnectionType`, `NewPossibleConnectionTypes` | **Leitura.** Tipo atual e permitido de conexão WAN. |
| `GetStatusInfo` | Nenhuma | `NewConnectionStatus`, `NewLastConnectionError`, `NewUptime` | **Leitura verificada.** Estado, último erro e uptime. Único método efetivamente invocado nesta investigação. |
| `GetNATRSIPStatus` | Nenhuma | `NewRSIPAvailable`, `NewNATEnabled` | **Leitura.** Capacidades do NAT/RSIP. |
| `GetGenericPortMappingEntry` | `NewPortMappingIndex` | `NewRemoteHost`, `NewExternalPort`, `NewProtocol`, `NewInternalPort`, `NewInternalClient`, `NewEnabled`, `NewPortMappingDescription`, `NewLeaseDuration` | **Leitura.** Consulta mapeamento NAT por índice, podendo revelar IPs internos; não é lista de clientes Wi-Fi. Não sondar automaticamente. |
| `GetSpecificPortMappingEntry` | `NewRemoteHost`, `NewExternalPort`, `NewProtocol` | `NewInternalPort`, `NewInternalClient`, `NewEnabled`, `NewPortMappingDescription`, `NewLeaseDuration` | **Leitura.** Consulta mapeamento NAT conhecido; não revela RSSI. Não sondar automaticamente. |
| `AddPortMapping` | `NewRemoteHost`, `NewExternalPort`, `NewProtocol`, `NewInternalPort`, `NewInternalClient`, `NewEnabled`, `NewPortMappingDescription`, `NewLeaseDuration` | Nenhum | **Mutação.** Abre/redireciona porta. Proibido. |
| `DeletePortMapping` | `NewRemoteHost`, `NewExternalPort`, `NewProtocol` | Nenhum | **Mutação.** Remove regra. Proibido. |
| `SetConnectionType` | `NewConnectionType` | Nenhum | **Mutação.** Altera conexão WAN. Proibido. |
| `RequestConnection` | Nenhuma | Nenhum | **Mutação.** Inicia conexão WAN. Proibido. |
| `ForceTermination` | Nenhuma | Nenhum | **Mutação.** Encerra conexão WAN. Proibido. |

## Limites relevantes para o DrosoBot

**O SOAP descoberto não apresenta** `GetAssociatedDevices`, `GetClientRSSI`, `GetMeshNode`, `GetStationStatistics`, `WLANConfiguration` ou equivalentes. Não se deve inventar métodos nem enviar chamadas SOAP não anunciadas. O IGD relata infraestrutura de Internet, não necessariamente o subsistema de rádio. A lista de clientes e a topologia mostradas no aplicativo Tenda WiFi provavelmente dependem de outra interface, mas é necessário identificá-la por documentação e acesso autorizado, sem inferir que RSSI simultâneo por nó esteja disponível.

### Como repetir somente leituras

No IFRO, a partir da cópia sincronizada do DrosoBot:

```sh
export TENDA_GATEWAY_URL='http://IP_LAN_DO_GATEWAY:5500'
python3 scripts/tenda_soap_audit.py > /tmp/tenda-soap-contract.json
python3 scripts/tenda_soap_audit.py --probe-readonly > /tmp/tenda-soap-readonly.json
```

Os relatórios JSON gerados são **locais**, não devem ser colocados no GitHub. O primeiro comando executa somente GET de XML de descrição. O segundo adiciona até 10 consultas SOAP declaradas como leitura e sem argumentos; não tenta consultas de tabelas NAT nem métodos mutáveis. O código não registra valores de IP, portas ou payloads, somente campos e tempo da operação. Examinar o conteúdo antes de eventual compartilhamento.

### Próximos critérios de aceitação

- Confrontar argumentos **reais** de cada ação com os esperados nesta tabela, registrar divergências.
- Verificar sucesso/falhas das até 10 consultas sem parâmetros e medir latência, sem confundir esses tempos com atualização de RSSI.
- Identificar versão/modelo da Tenda e as interfaces documentadas do aplicativo para associação de clientes aos nós, com permissão legítima de leitura.
- Se houver informação de estação, distinguir `nó associado` de `RSSI visto por múltiplos nós`. Só o segundo, após coleta/calibração, permitiria explorar multilateração ou fingerprinting mais detalhado.

## Referências técnicas

- [UPnP IGD Layer3Forwarding v1](https://upnp.org/specs/gw/UPnP-gw-Layer3Forwarding-v1-Service.pdf)
- [UPnP IGD WANCommonInterfaceConfig v1](https://upnp.org/specs/gw/UPnP-gw-WANCommonInterfaceConfig-v1-Service.pdf)
- [UPnP IGD WANIPConnection v1](https://paperzz.com/doc/7149834/wanipconnection-1-service-template-version-1.01)
- [Go UPnP InternetGateway v1 typed methods](https://github.com/huin/goupnp/blob/main/dcps/internetgateway1/internetgateway1.go)
