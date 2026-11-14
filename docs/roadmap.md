# Roadmap verificável

- [ ] P0. Confirmar hardware/firmware exato e inventário de periféricos do ESP-Hi, sem alterar firmware.
- [ ] P1. Identificar canal bidirecional local permitido; teste de leitura sem acionar motores.
- [ ] P2. Validar comando `stop` e watchdog com robô erguido/supervisionado; depois micro-movimento autorizado.
- [ ] P3. Medir latência, perda de pacotes, estados comandados versus observados, repetibilidade da marcha.
- [ ] P4. Caracterizar Wi-Fi disponível (RSSI/APs; CSI somente se suportado), com tratamento local dos dados.
- [ ] P5. Construir posicionamento probabilístico por fingerprinting com pontos de referência reais e baseline simples.
- [ ] P6. Montar simulação fechada do ESP-Hi com sensores admissíveis e comparadores pareados.
- [ ] P7. Adaptar núcleo MaleCNS/FlyDoom, com portas anatômicas, proveniência, testes e curvas de aprendizado.
- [ ] P8. Realizar teste físico progressivo e supervisionado; autonomia somente após obstáculos, quedas e paradas controladas.
