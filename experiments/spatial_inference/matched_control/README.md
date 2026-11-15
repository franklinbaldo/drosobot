---
type: experiment-methodology
status: matched-budget-control-measured-on-ifro
observed_on: 2026-11-15
---

# Nomos: controle do orçamento de observações para raios virtuais ativos

## Por que existe um quinto braço?

O experimento A/B/C/D principal, em `../compare.py`, usa três observações de alcance por segundo em B/C/D. A escolha ativa de direções D superou as direções convencionais C em cinco sementes daquela cena. Entretanto, **isso não prova que escolher a direção seja melhor que receber qualquer outra observação adicional**, especialmente quando a estratégia ativa faz mais previsões internas.

Este segundo experimento adiciona um **controle explícito para a quantidade de novas observações**: `C_uniform_extra` recebe uma leitura física virtual extra em uma direção cíclica não otimizada; `D_active_virtual_rays` recebe **exatamente uma leitura extra**, mas sua direção é escolhida pelo desacordo entre previsões dos 192 agentes-partícula. Os candidatos são somente cálculos de previsão; **não fornecem informação nova sobre o mundo externo**. A leitura adicional de ambos sai de um oráculo Embree independente, nunca de um raio simulado pelo próprio estimador.

## Hipóteses e fatos, separados

O mapa físico sintético é uma sala de 10 × 8 m com duas caixas e uma trajetória elíptica de 600 segundos; o avaliador conhece a pose verdadeira. A configuração e a trajetória são distintas das usadas na primeira comparação A/B/C/D, portanto **não misture números das duas experiências como se fossem uma única série**. Um sensor virtual de alcance mede 3 raios Embree/s, com ruído e perda sintetizados. Dois emissores cooperativos fictícios anunciam posições globais inventadas e medidas de alcance fictícias, com erro. A odometria também é sintetizada.

A fonte **real da rede** foi um instantâneo ICMP obtido pelo IFRO Ethernet de dois endereços Tenda conhecidos (e um terceiro endereço histórico sem resposta). O modelo importa apenas a distribuição observada de **RTT como referência de pontualidade**, sem transformá-la em distância, sem inferir coordenadas e **sem usar RTT como informação espacial**. Não há suporte verificado a RSSI simultâneo de cliente, Wi-Fi FTM, distância a cada nó ou posição dos emissores reais. Não fazemos acompanhamento de pessoas ou dispositivos da casa.

O script padrão exige uma medição real assinada pelo campo `source=real_ifro_readonly_icmp`. Uma fixture inteiramente sintética só é aceita com `--test-fixture-network`, e o relatório mantém esse marcador, evitando atribuir amostras inventadas à casa.

## Comparadores

| Braço | Conhecimento/novas observações por segundo |
| --- | --- |
| A | Apenas odometria relativa, sem mapa absoluto |
| B | A + mapa e até três leituras Embree sintéticas |
| C | B + dois emissores móveis cooperativos **simulados** |
| C + uniforme | C + **uma** leitura Embree adicional, direção escolhida ciclicamente |
| D + ativa | C + **uma** leitura Embree adicional, ângulo escolhido a partir de previsões virtuais |

A quinta linha é um controle negativo para permitir separar “um raio a mais” de “um raio escolhido inteligentemente”. A decisão ativa pode consumir muitos milhares de raycasts internos. Seu custo computacional precisa entrar na avaliação custo-benefício, mesmo que o orçamento de observações seja igual.

## Execução verificada no IFRO, 15/11/2026

Cinco rodadas de **600 segundos simulados por seed**, executadas aceleradamente no IFRO Core i3-2120 com Embree 4.3.3 e 192 partículas por braço. Não foram cinco execuções cronometradas de 10 minutos de relógio; o trabalho usa trajetória e parâmetros reproduzíveis.

| Seed | C (RMSE) | C + direção uniforme (RMSE) | D + direção ativa (RMSE) | Melhor, uniforme vs ativa |
| --- | ---: | ---: | ---: | --- |
| 20261115 | 16,86 cm | **13,38 cm** | 13,88 cm | Uniforme |
| 101 | 14,70 cm | **11,30 cm** | 12,08 cm | Uniforme |
| 202 | 13,05 cm | **12,23 cm** | 12,30 cm | Uniforme |
| 303 | 13,51 cm | 11,96 cm | **11,45 cm** | Ativa |
| 404 | 12,67 cm | 12,16 cm | **10,95 cm** | Ativa |

**Conclusão científica:** o raio adicional em geral ajudou em relação a C, mas a política ativa **não superou consistentemente** a seleção uniforme com o mesmo orçamento de observações, vencendo 2 de 5 sementes. A utilidade de raios virtuais como ferramenta para escolher uma observação continua uma hipótese, não um resultado robustamente demonstrado.

A comparação mede **RMSE espacial** na mesma cena sintética e com as mesmas duas classes de informações adicionais. Não é precisão da casa e não comprova percepção nem localização real do DrosoBot. A variabilidade amostral do pequeno conjunto de seeds ainda não permite conclusão estatística ampla.

## Reproduzir

Os arquivos `experiment.py` e `inference.py` são Python 3 sem dependências externas. O backend de verdade das observações é o binário `embree_angles` compilado em CPU, como no benchmark A-D. No runner GitHub Actions, o job `embree-bridge` já prepara esse binário. O modo fixture roda sem equipamentos:

```sh
python3 -m unittest discover -s experiments/spatial_inference/matched_control -p 'test_*.py' -v
python3 experiments/spatial_inference/matched_control/experiment.py \
  --network-snapshot experiments/spatial_inference/matched_control/test-latency-fixture.json \
  --test-fixture-network --embree-oracle dist-embree/embree_angles \
  --seconds 30 --particles 48 --output /tmp/nomos-matched-fixture.json
```

No IFRO, execute sem `--test-fixture-network` e com um caminho **privado** para uma coleta real anonimizada, nunca com IPs/MACs embutidos no código público. Exemplos de resultados e seus hashes estão arquivados no `franklinbaldo/workspace` privado em `infrastructure/home/drosobot/spatial-inference/2026-11-15/`.

## O que falta

- Posições medidas das Tenda no mapa da casa e medições legítimas de rádio do **mesmo cliente** em múltiplos pontos, ou outro sensor real com alcance validado.
- Comparar com plantas erradas, portas abertas e fenômenos de não linha de visada; usar holdout espacial e temporal.
- Calibrar o raio de confiança com dados reais e avaliar ganho de informação por observação *real*, não apenas por raio da própria hipótese.
- Integrar a memória de fótons e MaleCNS em modo observador antes de qualquer comando de movimento.
