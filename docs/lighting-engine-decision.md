---
type: architecture-decision
status: proposed
scope: drosobot-virtual-photon-field
reviewed_on: 2026-11-15
---

# Decisão: transporte de luz para o experimento de fótons virtuais

## Pergunta

Qual tecnologia de simulação de iluminação deve fornecer os fótons virtuais que
serão transmitidos em eventos ao receptor pela rede doméstica Tenda Mesh?

**Escolha:** Mitsuba 3 como *oráculo físico offline* e protótipo de trajetória,
Rust como motor de eventos e transmissão; wgpu/WebGPU apenas para visualização
avançada quando houver dispositivo e contexto seguro adequados. O laboratório
atual `rust/drosobot-sim/src/photons.rs` continua como controle determinístico
2-D, não como simulador físico de luz.

## Bases e tecnologias verificadas (novembro de 2026)

| Motor | Pontos fortes | Por que não é o transporte inicial |
| --- | --- | --- |
| **Mitsuba 3** | Renderização espectral, modos CPU/GPU, luz direta/indireta, renderer diferenciável; `ptracer` parte do emissor | Exporta normalmente imagens, não um fluxo de eventos. Precisamos instrumentar amostras ou um integrador próprio para obter trajetórias. `ptracer` não é automaticamente o melhor para gerar imagens, por causa da variância. |
| **pbrt-v4** | Referência independente, espectral, path/volpath/bidirectional PT, CPU e GPU | Excelente comparador de correção, mas não substitui o nosso codec nem receptor. |
| **NVIDIA RTXPT / RTXDI ReSTIR PT (2026)** | Reuso temporal/espacial de trajetórias, amostragem, caching e denoising para FPS alto | Foco em qualidade de imagem e GPUs fortes; exige verificar licença, backend e hardware. Não instalar no IFRO de 4 GB nem pressupor RTX nas TVs/celulares. |
| **3D Gaussian Splatting / NeRF** | Reconstrução e exibição de cenas a partir de imagens | Uma representação de aparências não é, por si, simulador de energia, reflexos e tempos de percurso. Métodos *relightable* são área de pesquisa e não o oráculo escolhido. |
| **Rust + wgpu** | Transporte de dados portátil; visualização GPU browser nativo/WASM com opção WebGL2 | Não há ganho em implementar de início um renderizador físico completo no front-end. WebGPU no navegador exige contexto seguro (HTTPS ou localhost), além de disponibilidade do dispositivo. |

Fontes de especificações, técnicas e suas limitações:

- Mitsuba 3: https://mitsuba-renderer.org/ e https://mitsuba.readthedocs.io/en/stable/src/generated/plugins_integrators.html
- pbrt-v4: https://pbrt.org/users-guide-v4
- NVIDIA RTXPT: https://github.com/NVIDIA-RTX/RTXPT e artigo ReSTIR PT Enhanced (maio/2026) https://research.nvidia.com/labs/rtr/publication/lin2026restirptenhanced/
- WebGPU/wgpu: https://wgpu.rs/doc/wgpu/documentation/platforms/web/index.html

## Camadas e execução

1. **Cena canônica mínima**: geometria, materiais, fontes, coordenadas e relógio
   lógico declarados num contrato próprio versionado; converter para cenas
   Mitsuba XML nos experimentos que pedem referência física. Evitar manter duas
   definições divergentes de geometria. Cenário inicial: duas caixas e uma sala.
2. **Oráculo físico offline**: executar Mitsuba 3 `scalar_rgb` inicialmente no
   GitHub Actions de repositório público ou outro executor externo apropriado,
   nunca no Jatobá. Testar `path`/`volpath` como referência de irradiância da
   cena, e `ptracer`/integrador instrumentado para trajetórias iniciadas na
   fonte. Posteriormente comparar `scalar_spectral` e `bdpt` onde fizer sentido.
3. **Emissor em Rust**: consumir amostras validadas ou executar um integrador
   incremental simples em Rust para emissão, reflexão especular/difusa,
   absorção, energia/amplitude, comprimento óptico e interações. Fonte real de
   geometria é privada ao emissor/avaliador, não ao receptor.
4. **Eventos binários**: usar a especificação DPH1 como controle v1 e criar uma
   versão explícita para campos físicos adicionais: `wavelength_nm`,
   `path_length_mm`, `time_scene_ns` ou tempo lógico escalado, `power_weight`,
   `material_interaction` e IDs/correlação quando apropriados. Nunca alterar
   silenciosamente o layout DPH1 já testado; manter compatibilidade versionada.
5. **Transporte LAN**: IFRO servidor de leitura, sessão autenticada e limitada,
   navegador celular receptor. Medir RTT, jitter, perdas e bytes; **não**
   interpretar diferença entre relógios não calibrados como tempo de voo
   eletromagnético ou distância. Começar com visualização Canvas2D para
   acessibilidade em HTTP local; habilitar WebGPU/wgpu quando tivermos HTTPS e
   confirmação de recursos do navegador.
6. **Receptor**: reconstruir campo temporal a partir de eventos e histórico,
   lidar com atrasos, duplicação, omissões e entrada tardia. Avaliar dois modos:
   `com_object_id` (limite superior com informação privilegiada declarada) e
   `sem_object_id` (agrupamento geométrico sem rótulo).

## Precisão e interpretação do tempo

O *tempo físico* de deslocamento da luz em 10 metros é aproximadamente
33,4 nanossegundos no vácuo; Wi-Fi doméstico e relógios de aplicativos têm
jitter muito maior. Portanto:

- Um timestamp absoluto de evento descreve **tempo da simulação**.
- Comprimento de percurso pode ser convertido em tempo **interno** do evento
  (por exemplo, ns) no renderizador, mesmo quando o pacote é recebido depois.
- A latência de transmissão mede a frescura da reconstrução, não posição física
  do receptor. Localização precisa requer âncoras/sensores apropriados.

## Critérios de validação e decisões de escopo

- O benchmark da malha deve reproduzir em **dois processos/dispositivos
  independentes** uma sequência com perda, replay e timestamps, separando
  envio/recepção de simulação física. Não declarar experimento Wi-Fi real com
  um receptor na mesma máquina.
- O oráculo Mitsuba deve produzir resultado quantitativo (energia, imagem,
  amostras de impacto ou mapa de radiância) comparável ao Rust na mesma cena,
  com semente aleatória, convenções de unidades, materiais e tolerâncias
  registrados. Não afirmar correlação de eventos individuais estocásticos de
  integradores distintos por coincidência de semente.
- Comparar contra **transmissão de estado completo** e **deltas**; medir erro
  do campo, bytes/evento, taxa de eventos, CPU e memória no IFRO/receptor.
- O maior risco epistemológico da versão atual é entregar o `object_id` no
  evento de colisão, tornando mais fácil a segmentação; manter isso como
  controle positivo, não como prova de percepção não supervisionada.
- O circuito com MaleCNS permanece **shadow mode**, sem comandos motores.

## Corte de implementação imediato

Não substituir todo o Rust por Mitsuba, não exigir RTX e não interromper a
Tenda para configurar a experiência. Próxima PR deve incluir (a) cliente de
recepção web independente e teste ponta a ponta; (b) medida sem objeto rotulado;
(c) amostra física de referência Mitsuba 3 executada em CI externo, como
componente opcional isolado do servidor de eventos. Só depois medir em telefones
ou ESP32 reais e decidir se iluminação GPU/RTX acrescenta informação suficiente.
