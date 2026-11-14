# Wi-Fi no DrosoBot: localização aproximada e abstinência

**Status:** simulador de sinais **totalmente sintéticos**. Não houve coleta de Wi-Fi em casa, nem acesso ao rádio ESP-Hi, nem triangulação física. Este algoritmo não detecta obstáculos e não permite navegação autônoma segura.

## Modelo de medição

- `Scan`: instante, origem declarada (`Synthetic`, `EspHi` ou receptor auxiliar), *namespace* dos identificadores pseudonimizados e lista de `(pseudonym: u64, RSSI: i16 dBm)`.
- `Anchor`: amostra de referência rotulada com número de região, não posição x/y. Referências reais de cômodos ficarão somente no IFRO.
- `Estimate`: índice aproximado de região + **distância heurística entre sinais**, ou `Unknown(motivo)`. O resultado **não é coordenada em metros** nem probabilidade calibrada.

O ID de ponto de acesso deve ser obtido por pseudonimização estável e protegida, com sal local; **o crate não executa hashing, não oferece anonimato automático e nunca recebe SSID/BSSID bruto**. Evitar publicar tabelas de regiões, intensidade do sinal e identificadores correlacionáveis. Mudanças de sal produzem namespaces incompatíveis e exigem novo fingerprinting.

## Baseline simples

Compara cada varredura à referência usando a média do desvio absoluto de RSSI entre APs compartilhados e penalização de pontos ausentes. Exige pelo menos dois APs comuns, leitura não obsoleta, RSSI fisicamente plausível para a interface, identificação sem duplicatas e separação suficiente do segundo melhor candidato. Caso contrário, abstém-se.

A fórmula, o limiar de aceitação e a penalidade por AP ausente são **arbitrários e exploratórios**, não treinamento/validação com sinais do ESP-Hi. O teste usa apenas APs e regiões fictícios.

```sh
cargo test --manifest-path rust/drosobot-sim/Cargo.toml --all-targets
cargo run --release --manifest-path rust/drosobot-sim/Cargo.toml --bin wifi_demo
```

O desenho das medições aproveita o contrato RF descrito em [`papers/experiments/malecns_car_interface/README.md`](https://github.com/franklinbaldo/papers/blob/main/experiments/malecns_car_interface/README.md). Os experimentos `malecns_wifi` ligados a texto e embeddings não são evidência de posicionamento doméstico.

## Antes de qualquer uso real

1. Identificar se o firmware efetivamente instalado expõe lista de APs/RSSI e a periodicidade das medições. O HTTP de referência ainda não apresenta essas funções.
2. Escolher procedimento de coleta voluntária, armazenamento privado, retenção e pseudonimização de identificadores, sem log de SSID/BSSID no GitHub ou no shell.
3. Coletar pontos rotulados por região em diferentes dias, posições e orientações. Separar dados de treino e avaliação por período/condição para evitar vazamento.
4. Medir acurácia por cômodo **incluindo a taxa de abstinência**, erro por confusão, impacto de APs que somem e envelhecimento do ambiente. Não promover como sensor de obstáculos.
5. Somente alimentar o MaleCNS com regiões estimadas após validar a qualidade e declarar a incerteza. O controle físico exigirá sensores adicionais de obstáculo, queda e watchdog no ESP32-C3.

## O que a rede mesh Tenda pode acrescentar

Em 14/11/2026, o IFRO inspecionou o endpoint UPnP/SOAP do gateway Tenda Nova MW3. Os métodos disponíveis descrevem estado do gateway e mapeamento de portas, **não** RSSI/associação de clientes. A latência da consulta SOAP `GetStatusInfo` foi pequena (mediana de 6,55 ms em 12 tentativas), mas isso não estabelece latência do sensor de localização. O protocolo da aplicação Tenda ainda precisa de investigação autorizada e somente leitura. Consulte [inventário SOAP e limites](tenda-mw3-soap.md).
