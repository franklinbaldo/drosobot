# Nomos / DrosoBot: sinais reais do canal Wi-Fi, sem coletar o conteúdo dos pacotes

O módulo `firmware/csi-listener/` implementa um receptor independente ESP32-C3 que resume características de CSI a cada segundo pela serial. **Não altera a modulação da Tenda, nem injeta pacotes ou mexe em firmware do roteador.**

Aproveitar uma transmissão normal da casa como referência de canal é diferente de emitir fótons virtuais. O canal Wi-Fi altera a onda física; o Nomos pode usar uma **medição real desse canal** como evidência e simular hipóteses sobre a geometria com Embree. Gerar mais raios virtuais, porém, não cria medições físicas novas.

## Processamento já testável sem placa

```bash
python3 -m unittest discover -s experiments/csi_signal -p 'test_*.py' -v
python3 experiments/csi_signal/generate_fixture.py \
  --output /CAMINHO_PRIVADO/csi-synthetic-600s.txt --seconds 600
python3 experiments/csi_signal/analyze.py \
  --input /CAMINHO_PRIVADO/csi-synthetic-600s.txt \
  --origin synthetic_csi_fixture \
  --output /CAMINHO_PRIVADO/csi-synthetic-600s.json
```

O gerador cria 600 janelas de 1 segundo **inteiramente fictícias**, com fase estável, fase com maior variação de canal e retorno à fase estável. Os valores não são gerados por um modelo eletromagnético de propagação e servem **somente para validar o pipeline de análise**. A análise usa os primeiros 60 segundos como referência e a mediana + seis vezes o MAD ajustado como *limiar heurístico*. Alertas indicam **mudança de característica do canal**, não presença ou identidade de alguém. A taxa de falsos alarmes é desconhecida sem dados reais rotulados.

## Captura de hardware autorizada

**Pré-requisitos:** uma placa de testes ESP32-C3 com o coletor CSI já gravado e conectada por USB a um host permitido, e seu canal 2,4 GHz configurado. O IFRO **não** possui ESP32-C3 USB conectado no momento da primeira inspeção (15/11/2026). Não tentar gravar o ESP-Hi/Xiaozhi.

```bash
python3 experiments/csi_signal/capture_serial.py \
  --port /dev/ttyACM0 --seconds 610 \
  --output /CAMINHO_PRIVADO/csi-live-raw-aggregates.txt
python3 experiments/csi_signal/analyze.py \
  --input /CAMINHO_PRIVADO/csi-live-raw-aggregates.txt \
  --origin esp32c3_live_passive \
  --output /CAMINHO_PRIVADO/csi-live-summary.json
```

O script `capture_serial.py` **não registra dados Wi-Fi crus**: aceita apenas linhas agregadas serializadas pelo firmware, sem MACs/payload/CSI bruto. O cabeçalho de sessão declara a origem. O analisador exige `--origin` compatível com esse cabeçalho e falha em caso de divergência. A saída não contém posições ou identidades de dispositivos.

## Experimento físico de dez minutos (planejado, não medido)

A sequência cientificamente válida, depois de conectar e testar a placa, deve ser: 2 minutos de ambiente estável com equipamento parado, 2 minutos com deslocamento controlado de **um único refletor conhecido e consentido**, 2 minutos novamente estáveis, repetindo em ordens alternadas e com estado de referência. O coletor termina automaticamente ao completar seu limite de janelas. A anotação de tempo e distância dos movimentos deve ser registrada **separadamente**, sem nomes pessoais ou identificação de clientes da rede.

Comparar mudança de CSI contra referência e controles: RSSI isolado, canal errado/sem amostras, outro dispositivo transmitindo e teste com movimento zero. Medir p50/p95 de taxa de quadros, mudanças detectadas, alarmes na fase estável e efeitos de antena/orientação. Sem distinguir origens ou obter um segundo receptor calibrado, **não estimar distância ou localização em metros**.

A integração futura com a memória do Nomos deve ser probabilística e manter separadas: mundo virtual, observações físicas de CSI, incerteza e custo do processamento. O protocolo de fótons DPH1 permanece independente e o ESP-Hi físico não recebe comandos.
