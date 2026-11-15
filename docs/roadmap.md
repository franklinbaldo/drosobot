# Roadmap verificável

- [ ] P0. Confirmar hardware/firmware exato e inventário de periféricos do ESP-Hi, sem alterar firmware. A família ESP-Hi foi identificada, mas revisão de firmware instalado continua pendente.
- [x] P1a. Identificar e implementar cliente de leitura do protocolo HTTP da distribuição ESP-Hi com testes isolados.
- [ ] P1b. Validar leitura HTTP com o robô real e confirmar identidade da WebUI.
- [x] P1c. Implementar pedido restrito de `DOG_STATE_IDLE` com confirmação presencial, sem executar no hardware.
- [ ] P2. Validar fisicamente `request-idle` e implementar watchdog no firmware com robô erguido/supervisionado; somente depois micro-movimento autorizado.
- [ ] P3. Medir latência, perda de pacotes, estados comandados versus observados, repetibilidade da marcha.
- [ ] P4. Caracterizar Wi-Fi disponível (RSSI/APs; CSI somente se suportado), com tratamento local dos dados.
- [ ] P5. Construir posicionamento probabilístico por fingerprinting com pontos de referência reais e baseline simples.
- [ ] P6. Montar simulação fechada do ESP-Hi com sensores admissíveis e comparadores pareados.
- [ ] P7. Adaptar núcleo MaleCNS/FlyDoom, com portas anatômicas, proveniência, testes e curvas de aprendizado.
- [ ] P8. Realizar teste físico progressivo e supervisionado; autonomia somente após obstáculos, quedas e paradas controladas.

- [x] P1d. Implementar gateway Rust sem dependências para inspeção HTTP e pedido de postura ociosa supervisionado.
- [x] P1e-a. Compilar e testar gateway Rust no CI; publicar binário e instalar no IFRO com SHA-256 validado.
- [ ] P1e-b. Verificar inspeção real no ESP-Hi quando a conexão HTTP local estiver disponível, sem mover robô.
- [ ] P1f. Inventariar firmware e criar experimento Rust para ESP32-C3 em hardware de testes, sem flashing no robô principal.

- [x] P6a. Criar simulação Rust determinística de malha fechada, sem conexões com hardware e sem informações privilegiadas ao controlador.
- [ ] P6b. Implementar sensores físicos admissíveis e controladores comparadores com orçamento pareado antes dos experimentos MaleCNS.
- [ ] P6c. Substituir a observação hipotética de obstáculo frontal por evidência de sensor real ou por uma modalidade explicitamente documentada.

- [x] P7a. Carregar o artefato público MaleCNS com hashes e executar um observador neural real em paralelo a um baseline convencional, sem influenciar ações.
- [ ] P7b. Pré-registrar um decodificador de saída motora e testar sua contribuição em ação fechada com baselines e nulos pareados.

- [x] P4a. Contrato de varredura Wi-Fi em Rust, comparação de fingerprints e abstinência em cenário totalmente sintético.
- [ ] P4b. Verificar API de medições reais no ESP-Hi; estudo de amostras privadas, holdout temporal e precisão por cômodo.

- [x] P4a. Descobrir serviços UPnP/SOAP reais do gateway Tenda MW3 e medir latência de consulta de estado, sem modificar rede.
- [ ] P4b. Descobrir, por método autenticado e somente leitura, se a API Tenda WiFi expõe nó associado e/ou RSSI por cliente.

- [x] P4c. Documentar os 18 métodos SOAP, parâmetros esperados, classificação de risco e auditor read-only offline com testes.
- [ ] P4d. Revalidar assinaturas reais de argumentos de cada método no gateway, executar apenas as consultas permitidas e registrar latência.

- [x] P4d. Preservar SCPDs originais e WSDL derivado no workspace e no IFRO; confrontar todos os 18 contratos reais e executar 10 consultas SOAP sem parâmetros somente de leitura.

- [x] P9a. Implementar laboratório Rust sem hardware de fótons virtuais, clock lógico, contatos/reflexões, reconstrução limitada, perdas, duplicatas e replay, mantendo a verdade no emissor/avaliador.
- [ ] P9b. Retirar rótulos semânticos privilegiados dos contatos, introduzir clustering e snapshots compactados com testes de observabilidade.
- [ ] P9c. Transportar eventos de forma autenticada sobre LAN/mesh real com medidas de atraso, incerteza de relógio e perdas, isolado de controle motor.
- [ ] P9d. Validar como transduzir evidência geométrica/espacial real em sinais egocêntricos MaleCNS, com baselines e nulls.

- [x] P9e. Selecionar renderer físico de referência para fótons virtuais: Mitsuba 3 offline; manter Rust como codec/transporte e wgpu opcional para visualização, sem exigir RTX ou mudar a rede. Ver `docs/lighting-engine-decision.md`.
- [ ] P9f. Integrar cena física de referência com Mitsuba 3 em executor externo e comparar emissões/contatos/energia por distribuição, não por identidade de amostra Monte Carlo.

- [x] P9g. Medir compatibilidade real do IFRO: Mitsuba 3.9.1 SIGILL; Embree 4.3.3 CPU SSE4.2 aprovado, benchmark primário e difuso com cinco repetições e código reproduzível.
- [ ] P9h. Expor Embree via ABI C/Rust segura para geração de eventos de fótons e medir consumo de banda antes da transmissão pela mesh.

- [x] P9i. Gerar eventos DPH1 a partir de interseções reais Embree 4 no IFRO e construir receptor/evaluador Rust com corpus sintético, sem I/O de rede ou motor.
- [ ] P9j. Integrar transporte local IFRO → receptor independente em celular/Tenda Mesh com limite de taxa, medição de latência, segurança e replay.

- [x] P9j-a. Implementar receptor web read-only do registro Embree/DPH1 com SSE, replay, injeção de perdas sintéticas, Canvas2D e medição RTT HTTP no navegador, sem acessar Tenda ou motores.
- [ ] P9j-b. Publicar sessão no IFRO em porta privada com isolamento systemd; verificar conectividade e latência a partir de um **segundo dispositivo real na Tenda**, sem usar o próprio IFRO como substituto.
