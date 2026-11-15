# CSI de rádio no ESP32-C3, sem alterar a Tenda Mesh

**Projeto experimental apenas para uma placa ESP32-C3 independente. NÃO instalar no ESP-Hi que executa Xiaozhi/controle de motores.** O firmware existente do DrosoBot não foi lido, modificado ou substituído.

## Hipótese

O Wi-Fi de casa continua transmitindo os seus próprios símbolos OFDM normalmente. O ESP32-C3 se associa **como estação cliente comum** a um AP Tenda autorizado, faz no máximo **um ping ICMP por segundo ao seu gateway padrão** e coleta a estimativa de estado do canal (CSI) dos quadros recebidos **do BSSID ao qual está associado**. Não injeta quadros 802.11, não muda canal/AP, não roda AP, não habilita promiscuous/sniffer, não altera senha/SSID nem configura o roteador.

Nos pacotes CSI, os dados IQ são **parte da estimativa do canal físico, não uma captura do conteúdo de aplicativos**. Este firmware usa somente magnitudes ao quadrado em oito faixas e RSSI para observar mudanças temporais. Não envia IQ bruto, fase, conteúdo de pacote, MAC/BSSID, IP, SSID ou senha para o computador receptor.

**O que isso mede:** uma assinatura grosseira de alterações na propagação; variações podem decorrer de movimento, interferência, taxas de transmissão, ganho automático, temperatura ou roaming. **Não mede diretamente** distância em metros, posição de pessoa/objeto, número de objetos ou sua identidade. Não transforma “ruído do Wi-Fi” em localização arbitrária. Os fótons virtuais do Embree podem comparar hipóteses espaciais, mas não criam novas observações do mundo físico sem medições.

## Confirmado por documentação do fabricante

- ESP32-C3 e API CSI: `esp_wifi_set_csi_rx_cb()`, `esp_wifi_set_csi_config()`, `esp_wifi_set_csi()`, `CONFIG_ESP_WIFI_CSI_ENABLED`. O callback recebe dados na tarefa Wi-Fi, por isso **apenas coloca dados em uma fila limitada**.
- O campo `wifi_csi_info_t.buf` contém pares `int8` imaginário/real; `first_word_invalid` exige ignorar os primeiros 4 bytes quando indicado. Este protótipo habilita **somente LLTF**, sem alterar a configuração física do roteador.
- Projeto oficial similar: [`espressif/esp-csi/examples/get-started/csi_recv_router`](https://github.com/espressif/esp-csi/tree/master/examples/get-started/csi_recv_router), que faz ping ao gateway e coleta CSI das respostas.

Documentação: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32c3/api-guides/wifi.html

## Critérios de segurança

1. Configuração padrão do firmware **não usa rádio**: `DROSOBOT_UNCONFIGURED` bloqueia inicialização. O CI usa somente esse padrão inerte.
2. A configuração do Wi-Fi deve ser feita localmente no **ESP32-C3 de bancada separado**, nunca no firmware Xiaozhi do robô. O arquivo `sdkconfig` tem SSID/senha e é excluído do Git; não publicar firmware já configurado com credenciais.
3. Associar normalmente (STA) e pingar somente o gateway recebido por DHCP, a cada 1–5 segundos. **Sem captura promíscua, sem mudança de configuração da Tenda e sem manipulação da modulação.**
4. Capturar no máximo 600 janelas de 1 segundo; desligar CSI, ping e rádio automaticamente. A fila Wi-Fi é limitada a 24 quadros com proteção contra bloqueio do callback. Quando cheia, registrar contagem de perdas.
5. UART imprime somente `CSI1` agregado de cada segundo, nunca IQ bruto ou identificadores. O decoder do IFRO aceita apenas esse contrato; não grava o log bruto de boot.
6. Não interpretar canais de outro AP como “mesmo ruído” da Tenda. Um BSSID diferente, roaming ou mudança de canal exige uma nova sessão declarada.

## Compilar no runner externo, não no IFRO/Jatobá

O projeto é ESP-IDF e usa componentes oficiais `esp_wifi`, `esp_netif`, `esp_event`, `nvs_flash`, `lwip`. O job `esp32c3-csi-observer` em GitHub Actions faz apenas `idf.py build` em executor Linux com Docker ESP-IDF. **Não** aciona flash; no CI não há credenciais.

Para compilar localmente em máquina com ESP-IDF 5.5, tendo **placa de bancada independente**:

```sh
cd firmware/csi-observer
idf.py set-target esp32c3
idf.py menuconfig   # selecionar DrosoBot CSI observer: SSID e senha locais, até 600 janelas
idf.py build
# Somente após validar placa, porta USB e backup/recovery:
# idf.py -p /dev/ttyACM_X flash monitor
```

Não executar `flash` sobre nenhuma porta desconhecida ou placa responsável por motores. A gravação de um firmware inteiro **substitui** a aplicação anterior daquele dispositivo; este projeto não modifica o Xiaozhi existente.

## Telemetria

Linha UART por segundo:

```text
CSI1,uptime_ms,frames_csi,dropped_queue,mean_rssi_dbm,power_0,power_1,power_2,power_3,power_4,power_5,power_6,power_7
```

Cada `power_N` é uma média inteira da energia `I²+Q²` no oitavo do vetor LLTF correspondente. Não há fase, payload ou endereços. O contrato, os exemplos sintéticos, o decoder e os testes estão em [`experiments/csi_lab`](../../experiments/csi_lab).

O próximo gate físico exige *uma placa ESP32-C3 independente com USB* conectada a um computador autorizado. O IFRO não apresentava nenhuma porta `/dev/ttyUSB*` ou `/dev/ttyACM*` quando inspecionado em 15/11/2026. Sem essa placa, qualquer gráfico de CSI gerado pelo simulador deve ser marcado como **sintético**.
