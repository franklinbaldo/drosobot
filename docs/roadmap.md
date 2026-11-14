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
