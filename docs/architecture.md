# Arquitetura proposta do DrosoBot

## Fluxo principal

```text
ESP-Hi (observações e comandos locais)
   | medições reais, com timestamp
   v
IFRO: gateway com contratos e validações
   |
   v
Transdutores (Wi-Fi RSSI/CSI, eventual IMU, sinais de servos quando disponíveis)
   |
   v
MaleCNS + adaptadores de entrada e saída
   |
   v
Árbitro de segurança (modo, velocidade, timeout, stop, intervenção humana)
   |
   v
ESP-Hi (movimento autorizado)
```

O MCP do Xiaozhi atualmente habilita a comunicação do dispositivo com ferramentas hospedadas no IFRO. Um canal inverso de comando do IFRO para o ESP-Hi é **hipótese de engenharia pendente de validação**.

## Estados e limites epistemológicos

- `motor_commanded`: movimento/ângulo solicitado, não movimento executado.
- `motor_observed`: somente se existir sensor ou retorno real medido.
- `wifi_observation`: RSSI, identificador de AP anonimizado, canal, horário; CSI apenas onde firmware/driver permitirem.
- `pose_estimate`: estimativa com confiança e fonte, nunca tomada como GPS de interiores.
- `obstacle_observed`: requer modalidade física capaz de observar obstáculo; RSSI isolado não é sensor de distância confiável.
- `controller_action`: saída MaleCNS/controle comparador, sujeita ao árbitro de segurança.

## Avaliação

Separar testes de interface, simulação fechada e demonstração física. Comparar MaleCNS com controlador convencional, rede aleatória e grafo rewired usando o mesmo orçamento e observações. Registrar dependências e incertezas.
