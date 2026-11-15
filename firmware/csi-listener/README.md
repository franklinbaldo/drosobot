# DrosoBot: receptor independente de CSI Wi-Fi (ESP32-C3)

Este **firmware experimental independente** escuta passivamente os sinais Wi-Fi de 2,4 GHz num canal fixo e calcula estatísticas de CSI, enviadas pela serial USB. Foi projetado para **outra placa ESP32-C3 de desenvolvimento**, não para substituir ou alterar o firmware Xiaozhi do ESP-Hi que controla motores.

**Segurança e escopo:** não transmite tramas 802.11 por conta própria, não se associa à Tenda, não pede senha, não efetua troca de canal, não acessa roteadores, não altera suas configurações e não contém comandos de movimento. Recebe sinais de gerenciamento no canal selecionado, e o conteúdo dos quadros, seus endereços MAC/BSSID e o CSI bruto **não saem do chip**, nem são guardados no log. Só médias agregadas por segundo chegam ao computador. O monitor permanece ligado durante no máximo 600 segundos por padrão, depois desativa CSI e a recepção promíscua e interrompe o rádio. Reiniciar a placa é necessário para repetir a coleta.

## O que mede e o que não mede

Cada quadra CSI contém pares complexos imaginário/real das subportadoras de uma transmissão que o ESP32-C3 recebeu. Calculamos potência média dos pares, média de RSSI, ruído reportado pelo rádio e variação de perfil espectral normalizada entre quadros comparáveis. A configuração usa L-LTF e HT-LTF e descarta quatro bytes iniciais quando `first_word_invalid` é sinalizado, conforme a documentação Espressif. A fila FreeRTOS impede cálculos pesados no callback Wi-Fi; descarte e limitação de amostras são contabilizados.

Essas características podem variar por multipercurso e movimento, **mas também** por controle automático de ganho, mudança de transmissor, tráfego, interferência ou posição da antena. Captar sinais no canal Tenda **não prova** que todos são originários da Tenda, e não fornece posição, direção, alcance, velocidade nem identidade de pessoas. Ausência de quadros CSI em um canal é um resultado possível. A calibração de detecção precisará de experimentos controlados com rótulos, um receptor estável e, possivelmente, filtragem de fonte autorizada sem registrar identidades.

## Requisitos para testar em hardware

1. **Placa ESP32-C3 independente**, identificada e fisicamente disponível. Não usar o ESP-Hi já em serviço, que tem firmware de robótica e Xiaozhi.
2. Cabo USB de dados conectado a um computador de laboratório autorizado; acesso ao dispositivo `/dev/ttyACM*` ou `/dev/ttyUSB*` comprovado.
3. Identificar previamente o **canal 2,4 GHz** do AP que se quer investigar, por meios legítimos. A Tenda pode usar canais diferentes entre nós e pode mudar automaticamente de canal. Não existe descoberta de canal via IFRO cabeado.
4. ESP-IDF **v5.5.6**, alvo `esp32c3`. A compilação deve ocorrer no GitHub Actions ou outro executor apropriado, não sobrecarregar IFRO/Jatobá. O projeto contém `CONFIG_ESP_WIFI_CSI_ENABLED=y` em `sdkconfig.defaults` e canal `1` apenas como valor inicial de compilação, **não** como afirmação sobre o canal da Tenda.

### Compilação isolada, sem instalar no IFRO

O GitHub Actions pode usar imagem oficial `espressif/idf:v5.5.6` no runner Linux, sem usar recursos pagos do Google Cloud:

```bash
cd firmware/csi-listener
idf.py set-target esp32c3 build
```

A configuração de canal é `CONFIG_DROSOBOT_CSI_CHANNEL` (1..11) e a duração é `CONFIG_DROSOBOT_CSI_MAX_WINDOWS` (10..1200). Antes de gravar num **ESP32-C3 de testes**, configurar o canal desejado no `menuconfig` e compilar novamente. Não compartilhar `sdkconfig` de firmware de produção nem credenciais; o projeto não exige SSID/password.

**Não efetuar flash automaticamente.** A gravação reprograma o chip conectado e destruiria o firmware anterior. Conferir fisicamente identidade da placa, preservar backup quando apropriado e somente executar `idf.py -p PORT flash monitor` em placa de testes aprovada. A ausência de porta serial no IFRO significa que não há como confirmar CSI real só com os testes do CI.

### Linha de dados serial

```text
CSI_SESSION_V1,origin=esp32c3_live_passive,channel=6,windows=600
CSI_AGG_V1,0,1000,6,30,0,0,12,-55.200,-96.000,1900.100,0.089120
...
CSI_COMPLETE_V1,windows=600,radio=stopped
```

Os valores do exemplo são **fictícios**. Os campos agregados são: número da janela, tempo desde boot em ms, canal, número de quadros analisados, descartes por fila/tamanho, limitados por taxa, RSSI médio, ruído médio, potência de CSI média e diferença média de perfis normalizados entre quadros. Não há MAC, conteúdo de pacote, CSI bruto, SSID ou coordenadas.

## Análise no IFRO

Ver `../../experiments/csi_signal/README.md`. O receptor serial só aceita portas USB explícitas, captura linhas `CSI_*` e descarta logs de boot ou quaisquer outras linhas. Os dados físicos ficam privados no IFRO, nunca no repositório público. Os testes com `origin=synthetic_csi_fixture` têm procedência distinta, e o analisador se recusa a tratá-los como dados físicos.

## Referências oficiais

- [Espressif: Wi-Fi Vendor Features / ESP32-C3 / CSI](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c3/api-guides/wifi-driver/wifi-vendor-features.html)
- [Espressif: `esp_wifi_set_csi_*` API](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32c3/api-reference/network/esp_wifi.html)
- [Espressif esp-csi: exemplo de receptor](https://github.com/espressif/esp-csi/blob/master/examples/get-started/csi_recv/main/app_main.c)
- [Imagem oficial Docker do ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32c3/api-guides/tools/idf-docker-image.html)
