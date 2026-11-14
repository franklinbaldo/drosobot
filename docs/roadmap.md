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
