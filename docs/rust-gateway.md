# Gateway Rust no IFRO

O pacote [`rust/drosobot-gateway`](../rust/drosobot-gateway) é a implementação Rust do primeiro protocolo ESP-Hi. Ele é **sem dependências externas**, executa em Linux e possui apenas dois subcomandos:

```sh
export DROSOBOT_URL=http://HOST_LOCAL_DO_ESP_HI
./drosobot inspect
# Só com a unidade à vista, em área segura, por decisão do operador:
./drosobot request-idle --supervised
```

O `inspect` solicita apenas `GET /` e `GET /main.js`, sem sensores fictícios. Ele verifica a identidade da WebUI e as rotas presentes no frontend. `request-idle` exige `--supervised`, verifica identidade/protocolo e só então chama `GET /exit_calibration` para solicitar a postura neutra. **Não** oferece marcha, salto, calibração ou acesso a comandos arbitrários. `request-idle` não é parada de emergência nem confirma execução física.

## Construção

```sh
cd rust/drosobot-gateway
cargo test
cargo build --release
```

A automação do GitHub Actions executa testes Python (referência) e Rust no repositório público e produz o binário Linux de referência em artefato de CI. O Jatobá atua apenas como orquestrador; o IFRO recebe o binário já compilado, sem instalação obrigatória de compiladores.

## Situação e limitações

- O protocolo foi extraído do componente de referência `espfriends/servo_dog_ctrl` (Espressif Component Registry); o firmware real do exemplar ainda não foi inventariado bit a bit.
- A disponibilidade do ESP-Hi por Wi-Fi oscila. Erro de conexão produz falha explícita; não se presume êxito.
- RSSI, posição de servos, bateria e obstáculos não são expostos pelas rotas HTTP de referência e são sinalizados como **não medidos**.
- O futuro watchdog e a parada física por perda de rede terão de residir no ESP-Hi, não apenas no IFRO.

## Initial IFRO deployment, 2026-11-14

The Rust release executable was built on the public GitHub Actions runner (Ubuntu 24.04), verified by SHA-256, and installed to `/opt/drosobot/bin/drosobot` on the IFRO. `/usr/local/bin/drosobot` loads the private local endpoint configuration and runs this Rust binary. The earlier Python launcher is retained locally for rollback; no private values are published. In the first read-only live probe, the robot did not respond to the TCP connection. This is an **unresolved connectivity/instrumentation gap**, not a successful hardware test. The existing Xiaozhi MCP voice bridge remains running independently.
