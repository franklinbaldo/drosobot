# Tenda MW3: SCPD original e WSDL derivado

O gateway UPnP da rede Tenda publica **descritores SCPD**, não um WSDL de origem. Em 14/11/2026, o IFRO realizou cópia de leitura dos quatro documentos XML originais anunciados pelo IGD, com hashes SHA-256, e um gerador converteu os serviços para um **WSDL 1.1 derivado (RPC/encoded)**. Não alegamos que o WSDL é oficial da Tenda nem que existe uma API SOAP nativa para RSSI por nó.

## Local privado dos artefatos

No workspace do Jatobá:

```text
/workspace/drosobot/.research/tenda-upnp/
  rootDesc.xml          # descrição UPnP original
  L3F.xml               # SCPD Layer3Forwarding
  WANCfg.xml            # SCPD WANCommonInterfaceConfig
  WANIPCn.xml           # SCPD WANIPConnection
  tenda-igd.wsdl        # WSDL derivado, com endereço local do gateway
  manifest.json         # hashes SHA-256 e contagens
  action-audit.json     # resultado de leitura dos contratos e consultas seguras
```

Cópia adicional no IFRO: `/var/lib/drosobot/tenda-upnp/`, acessível somente a root. Esses diretórios são **privados**; os arquivos originais podem conter identificadores da rede e não devem entrar no GitHub. O código público `scripts/tenda_wsdl_from_scpd.py` gera o WSDL novamente sem acesso à rede, a partir dos XMLs já salvos, e `scripts/tenda_soap_audit.py` faz leitura limitada do dispositivo quando disponível.

Exemplo de reconstrução **offline**, a partir da cópia privada:

```sh
python3 scripts/tenda_wsdl_from_scpd.py \
  --snapshot .research/tenda-upnp \
  --output .research/tenda-upnp/tenda-igd.wsdl \
  --gateway http://IP_PRIVADO_DA_TENDA:5500
```

O parâmetro `--gateway` só informa o endereço a incluir no WSDL. **O gerador não envia solicitações de rede.** Os serviços descritos no WSDL incluem os seis métodos potencialmente mutáveis apenas para documentar o contrato; nenhum deles é executado pelo gerador ou pela auditoria de leitura.

## Auditoria do dispositivo real

Dos 18 métodos anunciados pelo dispositivo, 12 são consultas UPnP. Destas, as 10 **sem parâmetros de entrada** foram testadas pelo IFRO e retornaram HTTP 200. `GetGenericPortMappingEntry` e `GetSpecificPortMappingEntry` também são consultas, mas exigem parâmetros, e foram deixadas sem execução para evitar expor mapeamentos da rede. Os seis métodos restantes alteram configuração/estado e **não foram invocados**.

| Serviço | Consultas sem entrada testadas | Resultado |
| --- | ---: | --- |
| `Layer3Forwarding` | 1 | HTTP 200 |
| `WANCommonInterfaceConfig` | 5 | HTTP 200 |
| `WANIPConnection` | 4 | HTTP 200 |

A auditoria extraiu argumentos, direção e tipos **diretamente dos SCPDs reais** e confirmou os 18 contratos apresentados em [tenda-soap-actions.md](tenda-soap-actions.md). Entre as 10 consultas seguras, a latência observada nesta rodada variou aproximadamente de **5,8 ms a 111 ms**, sem medir qualquer dado de localização. Os retornos brutos (IP externo, dados WAN e informações de portas) não são impressos no relatório gerado.

## O que isso permite

Conseguimos recriar clientes SOAP tipados e chamar os métodos anunciados sem redescobrir a interface. **Isso não resolve a localização do robô**: nenhum serviço IGD descrito possui dados de intensidade de sinal ou associação estação↔nó. O próximo protocolo a investigar é o de inventário de clientes da aplicação Tenda WiFi, mantendo leitura autorizada e dados privados.
