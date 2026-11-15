---
type: experimental-methodology
status: validated-synthetic-truth-with-real-icmp-context
observed_on: 2026-11-15
---

# Nomos/DrosoBot: mapa fixo, emissores móveis e raios de investigação

## O que realmente é conhecido

É um **teste de localização probabilística sobre um mapa sintético conhecido**, não um mapa da residência. O *avaliador* possui a trajetória sintética de 600 segundos previamente executada em tempo real no IFRO, enquanto os estimadores recebem apenas odometria sintética, observações de alcance virtual emitidas por um **sensor Embree 4** e, nos braços C/D, transmissões fictícias de dois emissores móveis cooperativos.

O componente **real da rede** é uma coleta ICMP *somente leitura* feita no IFRO Ethernet para até quatro nós locais já conhecidos, com períodos de medição restritos. O coletor remove IPs/MACs do JSON, conserva apenas alias e distribuições de RTT e respostas. Nenhuma medição de **RSSI de cliente, Wi-Fi RTT/FTM, geometria dos nós, distância física ou movimento** foi obtida. Portanto, **a rede real contribui até agora com telemetria de conectividade e contexto temporal, nunca como fator espacial da localização**. O motor não converte RTT ICMP em metros. Os emissores móveis abaixo são **inteiramente virtuais** e compartilham posições aproximadas inventadas.

## O mapa estrutural

- Sala **virtual de 10 × 8 metros**, quatro paredes e duas caixas fixas [2,2]–[4,4] e [6,4]–[8,6]. Obstáculos e paredes também estão no oráculo 3D do Embree usado no experimento de comportamento anterior.
- Uma **porta conceitual fechada** é identificada no mapa como segmento da parede oeste. Ainda é a mesma parede fechada do modelo geométrico Embree. Abrir/fechar uma porta será um estado dinâmico posterior. Nenhuma geometria residencial real é afirmada.
- Referências reais de rádio são **nós conhecidos por sua presença na rede**, mas suas coordenadas dentro da casa não foram fornecidas. A geometria da casa não é inferida desses IPs.

## Comparação A–D em condições pareadas

| Braço | Informação da estimativa |
| --- | --- |
| A | Odometria sintética relativa, sem mapa absoluto. Sem fator de raio, porque medir obstáculo sem mapa não produz coordenada global sozinho |
| B | A + mapa estrutural fixo e **3 observações de alcance** uniformes do Embree por segundo |
| C | B + duas transmissões fictícias de emissores móveis **cooperativos** com coordenadas anunciadas ruidosas e RSSI **sintético** |
| D | C + **3 observações de alcance selecionadas ativamente** por maior dispersão prevista dos raios entre partículas; mesmas 3 observações físicas virtuais por segundo |

Todos os braços utilizam a **mesma trajetória verdadeira sintética**, a mesma leitura de odometria relativa ruidosa, o mesmo conjunto inicial de partículas, o mesmo mapa disponível quando aplicável e o mesmo número de observações reais virtuais B/C/D. O braço D executa **simulações internas adicionais** para selecionar as melhores direções, o que custa CPU, mas essas simulações **não contam como nova informação empírica**. C e D recebem as mesmas observações fictícias de rádio.

Uma **observação de alcance** vem de três raios reais computados em Embree no cenário fictício, com ruído simulado de 7 cm. O `compare.py` usa um traçador geométrico 2D analítico exclusivamente na etapa de **previsão das partículas**, e a verdade vem de `embree_angles.cpp` via IPC. O alinhamento geométrico foi verificado com 450 raycasts randomizados no IFRO (erro máximo de distância de aproximadamente 0,000012 m).

O filtro usa 128 partículas por braço, validação geométrica, ponderação robusta por distância, reamostragem sistemática e incerteza heurística de raio 90%. Trata-se de modelo estatístico simplificado, **não** SLAM completo nem calibração probabilística assegurada. A identificação da posição inicial é uma *prior* artificial razoavelmente próxima da verdade, o que também favorece as estimativas.

## Resultados e interpretação científica

Na primeira execução (seed 20261115) o erro espacial médio da localização **sintética** foi:

- A: 1,659 m; B: 0,0672 m; C: 0,0665 m; D: 0,0507 m.
- B/C/D receberam 1.800 observações de alcance por braço, em 600 segundos de trajetória. C/D receberam 1.200 emissões móveis fictícias por braço.
- A estratégia ativa D gastou também raios de **simulação de hipóteses** para escolher as direções; são cálculos sobre crenças, não novas observações.

Quatro sementes adicionais (1701–1704) reproduziram o padrão: a **mediana entre cinco execuções** foi A 1,8905 m; B 0,0610 m; C 0,0603 m; D 0,0499 m. D reduziu o erro médio de 16,4% a 23,8% em relação a C nesses cinco testes, **sob condições muito favoráveis de mapa e sensores**. Os emissores móveis não acrescentaram benefício consistente além de B neste caso, porque o mapa e os raios ópticos já restringem bastante a posição. Não escolher parâmetros apenas para fabricar uma melhoria artificial em C.

Essas precisões centimétricas **não devem ser anunciadas como alcançáveis pela Tenda ou pelo DrosoBot físico**. O oráculo Embree fornece medições sintéticas de distância que **não comprovamos que o ESP-Hi possa realizar**; a geometria do ambiente é perfeita por construção; os emissores móveis transmitem coordenadas fictícias; paredes reais, interferência Wi-Fi, não linha-de-visada, deriva e sensores ópticos de verdade podem gerar erros muito maiores.

## Reproduzir com dados fictícios no CI

```sh
python3 -m unittest discover -s experiments/spatial_inference -p 'test_*.py' -v
# Requer também Embree 4 e o laboratório de comportamento compilados no executor.
g++ -std=c++17 -O2 -march=x86-64 \
  experiments/spatial_inference/embree_angles.cpp -lembree4 -o /tmp/embree_angles
python3 experiments/behavior_lab/run.py --sensor /tmp/embree_sensor \
  --duration 600 --fast --output /tmp/behavior-truth.json
python3 experiments/spatial_inference/compare.py \
  --truth /tmp/behavior-truth.jsonl \
  --network experiments/spatial_inference/test-network-fixture.json \
  --test-fixture-network --embree-oracle /tmp/embree_angles \
  --particles 64 --output /tmp/inference.json
```

O alvo `/tmp/embree_sensor` é criado no job CI compilando `experiments/behavior_lab/embree_sensor.cpp`, não está incluso no repositório como binário. A flag `--test-fixture-network` **é indispensável** para não confundir dados fictícios com dados reais. Nunca commitar a telemetria residencial bruta no repositório público.

## Executar com telemetria real no IFRO

O coletor somente opera sobre nós previamente conhecidos, fornecidos na linha de comando, sem varredura de endereços ou alterações administrativas:

```sh
python3 experiments/spatial_inference/collect_network.py \
  --node gateway=ENDERECO_PRIVADO_CONHECIDO \
  --node mesh_peer=OUTRO_ENDERECO_PRIVADO_CONHECIDO \
  --count 16 --output /DIRETORIO_PRIVADO/medicao-rede.json
```

O laboratório de localização, por sua vez, lê o log fictício anterior de 600 segundos, o snapshot real de rede sem endereços e o oráculo Embree:

```sh
python3 experiments/spatial_inference/compare.py \
  --truth /DIRETORIO_PRIVADO/ten-minute-real.jsonl \
  --network /DIRETORIO_PRIVADO/medicao-rede.json \
  --embree-oracle /DIRETORIO_PRIVADO/embree_angles \
  --output /DIRETORIO_PRIVADO/resultados.json
```

O tempo real entre ICMPs aparece **separado nas métricas**, como evidência de rede e capacidade de fornecer dados oportunamente. **Não influencia as coordenadas estimadas**, porque isso exigiria um modelo de sensor de localização que não temos. O experimento A–D é reproduzido em segundos de processamento usando a gravação de uma simulação de 10 minutos, não executa outra caminhada de 600 segundos de relógio. Não controla robôs.

## Próximo ganho de informação

1. Desenhar ou importar um mapa da casa **medido**, inclusive posições reais das Tendas; armazenar apenas em diretório privado, com origem e incerteza geométrica.
2. Acessar legitimamente dados de cliente/associação/RSSI, ou obter sensores reais do robô e medir posições verdadeiras de referência. Não presumir que antenas comuns fornecem alcances simultâneos.
3. Repetir curvas de precisão no tempo, com holdout espacial/temporal e teste do que ocorre se o mapa estrutural estiver errado ou a porta mudar de estado.
4. Retirar IDs semânticos do transporte de fótons e medir contribuição real de observações novas, distinguindo planejamento interno de nova informação externa.
