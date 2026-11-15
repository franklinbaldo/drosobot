---
type: architecture-decision
status: validated-ifro-cpu-2026-11-15
scope: drosobot-virtual-photon-field
reviewed_on: 2026-11-15
---

# Decisão: transporte de luz para o experimento de fótons virtuais

## Pergunta

Qual tecnologia de simulação de iluminação deve fornecer os fótons virtuais que
serão transmitidos em eventos ao receptor pela rede doméstica Tenda Mesh?

**Escolha operacional, depois do teste real no IFRO em 15/11/2026:**
**Intel Embree 4.3.3 (CPU) para interseções de raios com um integrador leve em
C++/Rust**, Rust como protocolo/replay/transmissão. Mitsuba 3 permanece apenas
**oráculo físico opcional em executor externo compatível**, não é backend local
aprovado: a versão oficial 3.9.1 em venv do IFRO encerrou com `SIGILL` logo ao
importar `drjit`/`mitsuba`. RTXPT/ReSTIR em GPU não são compatíveis com a placa
NVIDIA GeForce 610M/driver 390.157. wgpu/WebGPU apenas para visualização
avançada em dispositivos realmente compatíveis. O laboratório
atual `rust/drosobot-sim/src/photons.rs` continua como controle determinístico
2-D, não como simulador físico de luz.

## Bases e tecnologias verificadas (novembro de 2026)

| Motor | Pontos fortes | Por que não é o transporte inicial |
| --- | --- | --- |
| **Mitsuba 3** | Renderização espectral, modos CPU/GPU, luz direta/indireta, renderer diferenciável; `ptracer` parte do emissor | **Testado e não funcional no IFRO com wheel 3.9.1:** `SIGILL` até em `import drjit`. Opção de CI externo; recompilação para ISA antiga não foi testada. `ptracer` não é ótimo para qualidade de imagens por sua variância. |
| **Intel Embree 4.3.3** | CPU BVH/ray-triangle de alto desempenho com runtime SSE4.2 disponível no IFRO, sem RTX ou AVX2; bibliotecas pequenas e API C/C++ | **Testado** e aprovada execução local. Apenas interseção, não iluminação física completa. Integrador difuso experimental implementado e medido; falta validação física quantitativa. |
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
2. **Kernel de raios no IFRO**: usar `libembree4.so.4` em runtime isolado,
   invocado por uma fronteira C/C++ com interface tipada e segura a Rust;
   manter limites explícitos de uso de CPU/RAM. O teste real confirmou
   compatibilidade em SSE4.2/AVX1 e latência muito baixa para cenas pequenas.
3. **Oráculo físico externo opcional**: executar Mitsuba 3 em GitHub Actions
   ou outro executor remoto apropriado, jamais supor suporte no IFRO por
   simples `pip install`. Testar `path`/`volpath` e `ptracer` com cenas comuns,
   irradiância/caminhos e comparação estatística, não por identidade de sorteio.
4. **Emissor em Rust**: consumir amostras validadas ou executar um integrador
   incremental simples em Rust para emissão, reflexão especular/difusa,
   absorção, energia/amplitude, comprimento óptico e interações. Fonte real de
   geometria é privada ao emissor/avaliador, não ao receptor.
5. **Eventos binários**: usar a especificação DPH1 como controle v1 e criar uma
   versão explícita para campos físicos adicionais: `wavelength_nm`,
   `path_length_mm`, `time_scene_ns` ou tempo lógico escalado, `power_weight`,
   `material_interaction` e IDs/correlação quando apropriados. Nunca alterar
   silenciosamente o layout DPH1 já testado; manter compatibilidade versionada.
6. **Transporte LAN**: IFRO servidor de leitura, sessão autenticada e limitada,
   navegador celular receptor. Medir RTT, jitter, perdas e bytes; **não**
   interpretar diferença entre relógios não calibrados como tempo de voo
   eletromagnético ou distância. Começar com visualização Canvas2D para
   acessibilidade em HTTP local; habilitar WebGPU/wgpu quando tivermos HTTPS e
   confirmação de recursos do navegador.
7. **Receptor**: reconstruir campo temporal a partir de eventos e histórico,
   lidar com atrasos, duplicação, omissões e entrada tardia. Avaliar dois modos:
   `com_object_id` (limite superior com informação privilegiada declarada) e
   `sem_object_id` (agrupamento geométrico sem rótulo).

## Benchmark executado diretamente no IFRO (15/11/2026)

Hardware confirmado: Intel Core i3-2120, 2C/4T, 3,30 GHz, RAM 4 GB,
**SSE4.2 + AVX, sem AVX2**, NVIDIA GeForce 610M/driver 390.157,
Debian 13. Mitsuba 3.9.1 + Dr.Jit 1.5.0 instalados em venv isolada, mas
`import drjit` e `import mitsuba` encerraram com sinal `SIGILL` (4). Não houve
render bem-sucedido. A causa específica da instrução incompatível não foi
isolada; compilação personalizada poderia alterar esse quadro.

A biblioteca Embree 4.3.3 foi obtida de pacotes oficiais do Debian, extraída
para diretório separado, **sem instalar pacotes no sistema**. Compilação
`g++ -O3 -march=x86-64`, chamada direta de `rtcIntersect1`, BVH de cena
estática. Cinco repetições e mediana por cenário:

| Carga | Mediana Embree | Validação |
| --- | ---: | --- |
| 2 caixas × 12 triângulos, 80.000 raios | **13,39 milhões de raios/s** | 2.000/2.000 mesmos acertos que algoritmo Möller–Trumbore básico |
| 256 caixas, 80.000 raios | **7,25 milhões de raios/s** | 1.500/1.500 concordantes |
| 1.024 caixas, 80.000 raios | **5,57 milhões de raios/s** | 1.500/1.500 concordantes |
| 2 caixas, 50.000 fótons, até 4 reflexões difusas | **5,03 milhões de consultas/s**, 39,73 ms para 50.000 trajetórias | Contatos e energia de trajetória registrados, ainda não validados com renderização física |
| 256 caixas, 50.000 fótons, até 4 reflexões difusas | **3,64 milhões de consultas/s**, 54,94 ms para 50.000 trajetórias | Mesmo limite de interpretação |

A versão simples de Möller–Trumbore **não usa BVH** e não equivale a Mitsuba,
PBRT ou CUDA/RTX; diferenças de velocidade não são rankings universais.
Amostragens são pré-semeadas, cenas sintéticas e principalmente estáticas;
nenhuma métrica indica fidelidade de iluminação, fps de imagem, temperatura
ou tempo de rede. Exemplos reproduzíveis:
`benchmarks/lighting_cpu/README.md`. Dados completos e versões do ambiente
ficam somente no workspace privado do proprietário.

Uma taxa de **3,64 milhões de contatos/s**, se transformada em um evento de
44 bytes por contato, demandaria cerca de **160 MB/s antes de overhead de
transporte**, ultrapassando o limite teórico de uma conexão 1 Gb/s.
Portanto, a engenharia precisa de amostragem/reuso/compressão, em vez de
transmitir cada interação individual. Embree resolve interseções, não o
orçamento de rede.

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
(c) um kernel Embree instrumentado com interface segura no IFRO e, opcionalmente, Mitsuba 3 no CI, como
componente opcional isolado do servidor de eventos. Só depois medir em telefones
ou ESP32 reais e decidir se iluminação GPU/RTX acrescenta informação suficiente.
