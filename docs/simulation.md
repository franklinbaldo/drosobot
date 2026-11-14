# DrosoBot: primeira simulação de controle em malha fechada

**Status: exclusivamente sintético.** Nenhuma comunicação com o ESP-Hi, nenhum motor, nenhum sensor físico e nenhum núcleo MaleCNS foram utilizados neste experimento.

## Escopo

`rust/drosobot-sim` é um crate Rust sem dependências externas, separado do gateway de comunicação. Ele possui um mundo discreto retangular com obstáculos estáticos, orientação cardinal e uma observação sintética `ahead.blocked` atualizada em cada passo. A escolha de agir é feita por uma interface `Controller` que **não recebe** posição real da simulação, geometria completa, objetivo nem mapa de obstáculos. Esses dados permanecem exclusivamente no simulador/avaliador.

O modelo é uma abstração de navegação para testar contratos e impedir acesso privilegiado ao mundo, não uma simulação física das quatro pernas do ESP-Hi. Uma célula não representa distância percorrida ou duração de passos reais. `ahead.blocked` é uma **modalidade hipotética que nosso robô ainda não demonstrou possuir**. Não há justificativa para convertê-la silenciosamente em observação física.

## Contrato

- `Observation`: número do passo e eventual medição egocêntrica de obstáculo à frente, explicitamente `ObservationSource::Synthetic`.
- `Controller`: transforma somente a observação em uma proposta `Action::{Idle,Forward,TurnLeft,TurnRight}`.
- `SimulationGate`: rejeita a proposta se não houver medição, se ela vier do futuro, se estiver velha ou se movimento à frente encontrar obstáculo. Rejeição implica `Idle` **somente na simulação**.
- `GridWorld`: executa a ação aprovada de maneira determinística, sem atravessar obstáculos.
- `Episode`: registra passos, ações, recusas, colisões e pose real **para avaliação apenas**, jamais enviada ao controlador.
- `ReactiveBaseline`: comparador convencional reativo que avança se o caminho à frente estiver livre, senão gira à direita. **Não** usa MaleCNS e **não** representa capacidade biológica da mosca.

## Executar

```sh
cd rust/drosobot-sim
cargo test
cargo run --release
```

Tudo compila em GitHub Actions, e os testes são independentes do dispositivo ou da rede doméstica.

## Trabalho científico posterior

O próximo adaptador pode ligar os canais anatômicos declarados do MaleCNS a `Observation` e à enumeração de ações, mas não deve atribuir aprendizado, agência ou vantagem da topologia por mera presença de uma matriz de conectividade. A avaliação futura exige controladores de mesma capacidade orçamentária, reserva de sementes/cenários, controles de grafo religado/aleatório, medidas de segurança e ablações das modalidades. O controlador convencional atual é apenas a primeira comparação, não um baseline conclusivo. A [classificação de papéis MaleCNS](https://github.com/franklinbaldo/papers/blob/main/research/malecns-role-registry.md) diferencia observador, operador e controlador.

Não conectar o crate de simulação ao gateway físico sem protocolo separado de segurança, identificação de sensores realmente disponíveis e watchdog embarcado. `Idle` na simulação não certifica parada das pernas do robô.
