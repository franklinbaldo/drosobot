# MaleCNS ESP-Hi

Investigação aberta de robótica incorporada: adaptar um controlador experimental derivado do conectoma **MaleCNS** da mosca para um robô **ESP-Hi**, com computação central no **IFRO**.

> Status: fundação arquitetural; nenhum controle remoto físico, navegação autônoma ou leitura de posição real de servos demonstrados.

## Objetivo

Fechar o ciclo `sensores reais -> transdutores documentados -> MaleCNS -> decisões -> adaptador seguro de movimento -> ESP-Hi -> nova observação`, distinguindo o que o hardware **mede**, o que o firmware **ordena** e o que o controlador **estima**.

## Separação de responsabilidades

- **GitHub público (destino planejado):** código-fonte, documentação, experimentos, testes, proveniência, hashes públicos e protocolos científicos.
- **IFRO:** runtime de integração e experimentos locais; referência ao repositório versionado; serviços com limites de atuação e parada.
- **Jatobá:** orquestração e manutenção, não fonte canônica do projeto.
- **ESP-Hi:** sensores e atuadores; não assumir controle remoto direto até provar protocolo no firmware do aparelho.
- **Segredos, Wi-Fi doméstico e logs com dados pessoais:** apenas no ambiente privado, nunca no GitHub.

## Estado da integração

- Ponte `mcp2xiaozhi` no IFRO conecta-se ao endpoint do serviço Xiaozhi.
- O MCP atual `verificar_ifro` é de **robô para IFRO**; não prova capacidade de **IFRO para robô**.
- Há evidência de um serviço mDNS identificado como `ESP-Hi Web Control` na LAN, mas a disponibilidade HTTP tem oscilado. Sem envio de comandos motores.
- A árvore pública `78/xiaozhi-esp32/main/boards/espressif/esp-hi/esp_hi.cc` declara ferramentas locais `self.dog.basic_control` e `self.dog.advanced_control`; ainda não foram verificadas no firmware instalado.

## Referências

- [Firmware oficial Xiaozhi, placa ESP-Hi](https://github.com/78/xiaozhi-esp32/tree/main/main/boards/espressif/esp-hi)
- [FlyDoom, experimento existente](https://franklinbaldo.github.io/flydoom/)
- [MaleCNS Rover, projeto independente](https://github.com/ChihHsiangChien/maleCNS)
- [MaleCNS car interface, linha de pesquisa](https://github.com/franklinbaldo/papers/tree/main/experiments/malecns_car_interface)

## Primeiros passos

Consulte [arquitetura](docs/architecture.md), [roteiro](docs/roadmap.md) e [segurança](docs/safety.md). Antes de reutilizar código de terceiros, verificar a licença e registrar a proveniência.
