# Firmware DrosoBot em Rust: trilha isolada (sem gravação)

## Situação

O firmware que está no ESP-Hi ainda não foi extraído e sua versão exata é desconhecida. O firmware de referência [Xiaozhi ESP-Hi](https://github.com/78/xiaozhi-esp32/tree/main/main/boards/espressif/esp-hi) é C/C++ e integra voz, display e quatro servos. Não substituir ou gravar firmware apenas para unificar a linguagem.

## Rotas tecnológicas a comparar

1. **Rust com ESP-IDF**: [esp-rs/esp-idf](https://github.com/esp-rs/esp-idf) disponibiliza wrappers Rust para Wi-Fi, rede, servidores HTTP, timers e ESP32-C3. Maior compatibilidade com serviços ESP-IDF, mas há custos de toolchain e integração com componentes C existentes.
2. **Rust `no_std` com `esp-hal` + Embassy**: [esp-rs/esp-hal](https://github.com/esp-rs/esp-hal) suporta ESP32-C3 e o runtime `esp-rtos` oferece integração Embassy. Caminho potencialmente mais compacto, mas exigiria reimplementar e comprovar áudio, tela, conectividade, servo e gestão de energia.

A escolha deve resultar de medições em um hardware de desenvolvimento, **não** de reflashing precipitado do robô de uso diário.

## Inventário e verificações prévias

- [ ] Identificar revisão de placa, chips, pinos e firmware original instalado.
- [ ] Extrair backup completo e registrar hashes/partições, instruções e testes de restauração.
- [ ] Identificar modo de recuperação e confirmar acesso USB sem conflito com os servos.
- [ ] Documentar memória livre, alimentação e identificação dos quatro canais de servo.
- [ ] Levantar presença/ausência de IMU, feedback de servo, sensores de contato e Wi-Fi CSI/RSSI no firmware real.
- [ ] Compilar e executar o equivalente mínimo em **hardware separado**, sem perder voz/tela.
- [ ] Validar watchdog de movimento no próprio ESP32-C3, com limites e parada segura em perda de comunicação.
- [ ] Documentar licença/proveniência do firmware e suas dependências.

## Estratégia

Continuar a usar o firmware original enquanto o gateway no IFRO é migrado para Rust. Manter testes de contrato independentes, comparando comportamento do cliente Python legado e do novo executável Rust. Toda operação física precisa de autorização e supervisão; `DOG_STATE_IDLE` não equivale a parada de emergência certificada.
