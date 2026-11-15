# Simulação cronometrada de comportamento: 10 minutos no IFRO

## Objetivo

Testar **estabilidade e comportamento relativo** de duas políticas virtuais durante **600 segundos reais**, com sensores geométricos gerados pelo Intel Embree 4 e condições progressivamente difíceis. Não afirmar que a simulação reproduz fielmente o ESP-Hi: **gaita, atrito, servo, escorregamento, massa, momento, sensores ópticos e resistência do solo reais permanecem sem calibração.**

Este teste é um **primeiro laboratório de comportamento**, não um gêmeo digital integral. O MaleCNS real continua em *shadow mode* em um experimento separado; ele **não seleciona movimentos** nesta execução. O protocolo DPH1 de fótons virtuais está implementado e funcionando, mas **ainda não participa do loop do controlador móvel**, portanto não atribuir às trajetórias virtuais a navegação observada.

## Ambiente

- Sala sintética **10 × 8 metros**, com dois obstáculos retangulares fixos: [2,2]-[4,4] e [6,4]-[8,6], ambos com altura de 2 m.
- `embree_sensor.cpp`: processo C++ permanente com Embree 4, recebendo `x y heading` do avaliador e devolvendo distâncias para frente e ±45° (até 4 m) e um valor **arbitrário de iluminação** calculado por visibilidade de duas luzes mais uma atenuação inversamente proporcional à distância. Não é sensor físico ou ray/path tracing global completo.
- `run.py`: integra um corpo circular virtual de raio **0,16 m**, velocidade máxima **0,22 m/s**, aceleração máxima **0,55 m/s²**, taxa máxima de rotação **1,4 rad/s**, com passo de **100 ms**. São **valores escolhidos para o laboratório**, não identificados no hardware ESP-Hi. Movimento bloqueado por colisão geometrizada, sem penetrar em obstáculos.
- Política cautelosa: velocidade 0,19 m/s quando livre, limiar de desvio 0,65 m, parada diante de leituras ausentes/antigas, desvio baseado nos sensores laterais. Política agressiva: avanço mais rápido, limiar 0,28 m, sem desvio lateral preventivo. Ambas são comparadores convencionais sintéticos, não redes neurais treinadas.
- Pseudossinais de Wi-Fi RSSI de três âncoras **fictícias** com ruído e ausência de leitura. A localização baseada em região é deliberadamente limitada/abstém-se em casos ambíguos e **não é telemetria da Tenda**.

## Protocolo pré-registrado (seed 20261115)

| Intervalo | Cenário | Dropout sintético | Ruído de alcance (desvio-padrão) | Atraso máximo |
| --- | --- | ---: | ---: | ---: |
| 0–200 s | Iluminação alta | 2% | 2,5 cm | 100 ms |
| 200–400 s | Luz reduzida | 8% | 5,5 cm | 300 ms |
| 400–600 s | Escuro, leituras degradadas | 18% | 10 cm | 500 ms |

O controle recebe **apenas observações com carimbo de tempo**. O avaliador, separado do controlador, conhece a posição verdadeira e verifica colisões. A saída de movimento não é encaminhada a dispositivo físico. O ruído do alcance foi deliberadamente correlacionado à fase de iluminação como hipótese de sensor óptico dependente de luz, mas **essa correlação não foi medida no DrosoBot real**. Testes futuros podem usar um sensor que não depende da luz e eliminar esse acoplamento fictício.

O teste mede distância virtual percorrida, cobertura da sala em células de 50 cm, **tentativas de movimento bloqueadas** (não colisões reais com dano), ticks com observações antigas, fração de sensor útil, abstenção/classificação incorreta de regiões Wi-Fi sintéticas, além do jitter do passo real. As observações são sintetizadas com sementes fixas. Os dois comparadores partem do mesmo ponto, mas percorrem trajetórias divergentes, então suas observações não são pareadas após o desvio.

## Como executar no IFRO, sem comprometer serviços domésticos

No IFRO, com Embree 4 extraído de pacotes oficiais em `/var/lib/drosobot/lighting-lab/embree-root/usr/`:

```sh
LAB=/var/lib/drosobot/behavior-lab
LIBS=/var/lib/drosobot/lighting-lab/embree-root/usr
mkdir -p "$LAB"
g++ -O2 -std=c++17 -march=x86-64 \
  -I"$LIBS/include" experiments/behavior_lab/embree_sensor.cpp \
  -L"$LIBS/lib/x86_64-linux-gnu" -Wl,-rpath,"$LIBS/lib/x86_64-linux-gnu" \
  -lembree4 -o "$LAB/embree_sensor"
export LD_LIBRARY_PATH="$LIBS/lib/x86_64-linux-gnu"
python3 -m unittest discover -s experiments/behavior_lab -p 'test_model.py' -v
# Smoke test rápido: 10 segundos SIMULADOS, sem aguardar 10 s de relógio
python3 experiments/behavior_lab/run.py --sensor "$LAB/embree_sensor" \
  --output "$LAB/fast-control.json" --duration 10 --fast
# Execução de 600 segundos de RELÓGIO, com 6000 passos de 100 ms
python3 -u experiments/behavior_lab/run.py --sensor "$LAB/embree_sensor" \
  --output "$LAB/ten-minute-test.json" --duration 600
```

Em produção de laboratório, use uma unidade **transitória** do systemd com `CPUQuota=20%`, `MemoryMax=160M`, `TasksMax=16`, `RuntimeMaxSec=630`, isolamento de sistema e sem acesso à rede. O teste encerra sozinho e **não instala uma rotina recorrente**. Saídas com modo `0600`: arquivo JSON de resultados agregados, outro JSONL com trajetória e sensores a cada segundo. Nenhum SSID, MAC, conta ou dado da casa é registrado.

## Interpretação científica e próximos passos

1. Uma execução de 10 minutos mostra se o algoritmo trava, entra em ciclo, fica sem observações, colide *no modelo* ou consome muitos recursos.
2. **Não permite concluir realismo físico** sem calibração dos parâmetros com sensores/medidas do ESP-Hi. Os resultados devem ser chamados *coerência interna* ou *plausibilidade dentro das hipóteses*.
3. Um robô preso que tenta avançar milhares de vezes mostra falha de política dentro deste ambiente; não significa milhares de colisões físicas.
4. Antes de acionar o robô real: medir dimensões e velocidades permitidas, latência e disponibilidade de sensores, consumo energético e falhas de servo; comparar uma sequência real supervisionada com previsão simulada.
5. Próximo passo de alto valor: adicionar ruído e dinâmica medidos, confrontar previsões com testes físicos seguros e integrar percepção espacial DPH2/MaleCNS somente com resultados independentes.

## Reproduzir o comportamento visualmente

O script `report.py` lê o resumo JSON final e as posições avaliadas de segundo em
segundo (`.jsonl`) e gera um arquivo HTML *offline* autocontido com trajetória de
ambos os controladores, os dois obstáculos e um controle deslizante de tempo:

```sh
python3 experiments/behavior_lab/report.py \
  --summary /CAMINHO_PRIVADO/ten-minute-test.json \
  --log /CAMINHO_PRIVADO/ten-minute-test.jsonl \
  --output /CAMINHO_PRIVADO/ten-minute-test.html
```

O relatório mostra trajetórias **do avaliador**, não percepção interna nem
localização observada por sensores. Os valores são inteiramente sintéticos e
não precisam de Internet; não injetar código HTML ou dados externos no relatório.
