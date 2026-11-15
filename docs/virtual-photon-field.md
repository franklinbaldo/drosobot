# Campo de fótons virtuais: reconstrução espaço-temporal no DrosoBot

## Hipótese e limites

Um emissor de uma **simulação 2-D sintética** transmite eventos com posição, vetor e tempo lógico. Um receptor, sem acesso à lista real de objetos, atualiza trajetórias e uma memória de superfícies a partir de eventos de emissão/contato/reflexão. O mundo canônico, inicialmente com uma sala de **10 × 8 metros e dois retângulos**, fica isolado no lado emissor e no avaliador.

O nome *fóton* indica uma **partícula virtual informacional**, não um fóton eletromagnético individual, uma câmera, um sensor real ou propagação no Wi-Fi à velocidade da luz. A velocidade sintética inicial é de **1 metro por tick de 50 ms**, não a velocidade da luz.

A fonte virtual passeia entre oito pontos de observação nas bordas da sala para iluminar as quatro faces dos dois objetos. Isso é um **roteiro de calibração deliberado** e não o comportamento demonstrado do ESP-Hi. Cada evento de contato traz um **rótulo semântico de objeto** para agrupar superfícies; o receptor não recebe o tamanho nem as coordenadas dos retângulos, mas ainda depende desse rótulo, que seria uma informação adicional a justificar em sensores reais. Sem ele, agrupar superfícies desconhecidas é outra tarefa. A fonte da simulação e a identidade dos objetos não podem ser consideradas um substituto da percepção real.

## Contrato de evento, v1

O módulo Rust sem dependências é `rust/drosobot-sim/src/photons.rs` e o demonstrador é `rust/drosobot-sim/src/bin/photon_field_demo.rs`.

| Mensagem | Dados | Consequência |
| --- | --- | --- |
| `Epoch` | ID de simulação, dimensões da sala, origem do relógio lógico, duração do tick | Sincroniza o tempo e permite validar coordenadas, **não contém objetos** |
| `Emitted` | Número de sequência, instante lógico, ID da partícula, origem e vetor de velocidade | Permite prever trajetórias com limite de extrapolação |
| `Contact` | Sequência, instante lógico, ID da partícula, ID semântico de superfície, ponto de contato, normal | Informa a interação e permite inferir limites de superfície; velocidade refletida calculada pela normal |

Codificação binária: prefixo de 4 bytes `DPH1`, versão (1 byte), tipo (1), 2 bytes reservados, ID de cena (`u32` LE), sequência (`u32` LE), tick (`u32` LE). Corpos têm **20 ou 24 bytes**, total de **40 a 44 bytes** por evento. Posições e vetores são inteiros em milímetros, sem floats. A unidade de tempo é o tick lógico da cena, não nanossegundos de propagação de rádio. O protótipo **não contém assinatura, criptografia ou autenticação**; não deve ser conectado a uma LAN não confiável nem alimentar motores/ações.

Para calcular o instante da simulação a partir do relógio do receptor, o `ClockAnchor` recebe uma **estimativa externa de diferença de relógios**, sua incerteza e um limite admissível. Se a incerteza for excessiva, não fornece tick válido. A API não presume que atraso de rede = distância física. O fluxo não realiza Wi-Fi RTT/FTM e não descobre a localização física do robô.

### Reconstrução do lado receptor

1. O receptor recebe eventos em qualquer ordem e descarta duplicatas, rejeitando versões incompatíveis e conflitos de número de sequência.
2. Eventos `Contact` só se tornam amostras de superfície quando existe a respectiva `Emitted` e a posição/tempo da colisão concordam com a trajetória declarada; um contato isolado não cria objeto.
3. As normais das superfícies formam um conjunto de faces observadas por objeto. A envoltória mínima/máxima é **provisória** até encontrar as quatro orientações. No cenário limitado a dois retângulos alinhados aos eixos, quatro faces fornecem os limites completos.
4. A posição atual de uma partícula é extrapolada pelo vetor até o contato; depois da colisão, o vetor reflete. A extrapolação tem horizonte máximo explícito, evitando inventar trajetória infinita.
5. Se faltar evento, o receptor solicita números de sequência ao **log canônico do emissor**. Um ingresso tardio também pode receber todo o histórico a partir da sequência zero. Esse replay restaura observações; não envia o mapa dos objetos. A infraestrutura real para pedidos de retransmissão e snapshots compactados ainda precisa ser construída.

### Experimento de rede determinístico

O demonstrador injeta atrasos lógicos de 1 a 8 ticks, chegada fora de ordem, duplicação de pacotes e perda determinística de parte dos eventos. Depois permite a retransmissão dos eventos ausentes, mede bytes transferidos, conta amostras e compara **somente no avaliador** a envoltória reconstruída com as duas caixas reais. Não usa Wi-Fi nem a Tenda nesta fase, para que atrasos de rádio reais não sejam confundidos com erro de modelo.

Rode no GitHub Actions ou em outro executor externo (o IFRO é pequeno e o Jatobá é apenas o painel de controle):

```sh
cargo test --manifest-path rust/drosobot-sim/Cargo.toml --all-targets
cargo run --release --manifest-path rust/drosobot-sim/Cargo.toml --bin photon_field_demo
```

## Próximos degraus de validação

- Retirar o ID de objeto do pacote e comparar agrupamento geométrico sem labels contra o limite superior supervisionado.
- Implementar snapshots compactos, controle de backpressure e transporte real autenticado/ordenado sobre a LAN, sempre medindo atraso, perda, taxa útil e incerteza de sincronização; não assumir que UDP entregue ou tenha relógios sincronizados.
- Substituir a fonte virtual de contatos pelos sensores reais que o ESP32-C3 efetivamente possui. **RSSI por si só não é sensor de colisão**, e nem Wi-Fi mesh implica triangulação.
- Transformar as amostras validadas em entradas egocêntricas para o **MaleCNS no IFRO**, com controlador convencional e testes nulos pareados. O modelo neural não deve receber a geometria canônica escondida do avaliador nem controlar o robô antes da validação dos sensores e de medidas de segurança.
- Testar a Tenda Mesh e o ESP-Hi depois de confirmar acesso legítimo aos dados dos nós, sincronização e firmware instalado, sem alterar a configuração doméstica nesta implementação.

**Critério para um sucesso inicial:** as duas caixas exatas só devem ser recuperadas quando todas as amostras correspondentes forem recebidas ou recuperadas; com perdas não reparadas, o receptor deve declarar a reconstrução incompleta. Não equiparar esse êxito artificial a mapeamento ou localização real da casa.
