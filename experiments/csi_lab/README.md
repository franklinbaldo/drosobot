# Análise local de CSI agregado, com origem explicitamente declarada

Os scripts `analyze.py` e `generate_fixture.py` funcionam **sem hardware** e dependem apenas do Python 3.13. A fixture NÃO é CSI real: produz 600 janelas falsas para verificar regressões e um detector simples de mudanças na distribuição de energia das oito subportadoras/faixas agregadas.

```bash
python3 -m unittest discover -s experiments/csi_lab -p 'test_*.py' -v
python3 experiments/csi_lab/generate_fixture.py --output /CAMINHO_PRIVADO/csi_synthetic.log --seconds 600
python3 experiments/csi_lab/analyze.py \
  --input /CAMINHO_PRIVADO/csi_synthetic.log \
  --source synthetic_fixture \
  --limit-seconds 600 \
  --output /CAMINHO_PRIVADO/csi_synthetic_summary.json
```

A coleta **real** exige que o usuário escolha uma porta serial USB de **uma placa ESP32-C3 separada** com o firmware de captura instalado e configurado localmente. No IFRO (ou outro Linux com conexão USB), selecionar a porta certa por observação; não tentar dispositivos por varredura e não enviar comandos à porta serial do robô:

```bash
# Somente em uma placa de testes independente, identificada fisicamente.
PORT=/dev/ttyACM_X
stty -F "$PORT" 115200 raw -echo
python3 experiments/csi_lab/analyze.py \
  --input "$PORT" \
  --source unverified_separate_esp32c3_serial \
  --limit-seconds 600 \
  --output /CAMINHO_PRIVADO/real-csi-features-summary.json
```

O decoder descarta todas as linhas que não começam por `CSI1` e valida tamanho, contadores, RSSI e oito potências. Não salva conteúdo de pacotes, textos de boot, MAC, SSID, IP ou IQ. O relatório fica privado (modo 0600). A indicação `unverified_separate_esp32c3_serial` é intencional: uma porta serial por si só não prova procedência do firmware sem inspeção do equipamento.

O detector usa os primeiros 60 segundos para determinar uma referência estatística de magnitude normalizada, depois sinaliza mudanças. **Não é um detector calibrado de pessoas**, não separa automaticamente movimento de interferência e não estima posição. Um teste supervisionado inicial compararia 60 segundos com o ambiente imóvel, movimentação de **um objeto próprio conhecido** e retorno à condição anterior; a hora da intervenção seria registrada separadamente da CSI.

Por enquanto, a evidência real da rede disponível no IFRO é ICMP, não CSI: RTT de ida-e-volta aos pontos conhecidos. **Não converter ping em metros.** O benefício esperado do CSI sobre RSSI é oferecer informação espectral mais detalhada quando uma placa apropriada realmente estiver disponível. A Tenda deve continuar operando com seus clientes comuns, sem reconfiguração.
